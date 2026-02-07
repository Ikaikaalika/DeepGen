from dataclasses import dataclass


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    backend: str
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    mlx_model: str = "mlx-community/Llama-3.2-3B-Instruct-4bit"


class LLMClient:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError("openai package not installed") from exc
        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": "You are a genealogy research assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.output_text.strip()


class MLXClient(LLMClient):
    def __init__(self, model: str):
        self.model_name = model
        self._loaded = False
        self._model = None
        self._tokenizer = None

    def _load(self) -> None:
        if self._loaded:
            return
        try:
            from mlx_lm import load
        except ImportError as exc:
            raise LLMError("mlx-lm package not installed. Install with: pip install .[mlx]") from exc
        self._model, self._tokenizer = load(self.model_name)
        self._loaded = True

    def generate(self, prompt: str) -> str:
        self._load()
        try:
            from mlx_lm import generate
        except ImportError as exc:
            raise LLMError("mlx-lm package not installed") from exc
        result = generate(self._model, self._tokenizer, prompt=prompt, max_tokens=450)
        return result.strip()


def build_llm_client(config: LLMConfig) -> LLMClient | None:
    backend = config.backend.lower()
    if backend == "none":
        return None
    if backend == "openai":
        if not config.openai_api_key:
            return None
        return OpenAIClient(api_key=config.openai_api_key, model=config.openai_model)
    if backend == "mlx":
        return MLXClient(model=config.mlx_model)
    raise LLMError(f"Unsupported LLM backend: {config.backend}")
