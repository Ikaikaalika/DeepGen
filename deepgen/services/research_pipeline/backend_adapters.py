from __future__ import annotations

from dataclasses import dataclass

from deepgen.services.llm import LLMClient, LLMConfig, build_llm_client


@dataclass
class LLMRuntime:
    backend: str
    model: str
    client: LLMClient | None


def resolve_runtime(configs: dict[str, dict[str, str]]) -> LLMRuntime:
    llm_cfg = configs.get("llm", {})
    openai_cfg = configs.get("openai", {})
    anthropic_cfg = configs.get("anthropic", {})
    mlx_cfg = configs.get("mlx", {})

    backend = (llm_cfg.get("backend") or "none").lower()
    model = ""
    if backend == "openai":
        model = openai_cfg.get("model", "gpt-4.1-mini")
    elif backend == "anthropic":
        model = anthropic_cfg.get("model", "claude-3-5-sonnet-latest")
    elif backend == "mlx":
        model = mlx_cfg.get("model", "mlx-community/Llama-3.2-3B-Instruct-4bit")

    client = build_llm_client(
        LLMConfig(
            backend=backend,
            openai_api_key=openai_cfg.get("api_key", ""),
            openai_model=openai_cfg.get("model", "gpt-4.1-mini"),
            anthropic_api_key=anthropic_cfg.get("api_key", ""),
            anthropic_model=anthropic_cfg.get("model", "claude-3-5-sonnet-latest"),
            mlx_model=mlx_cfg.get("model", "mlx-community/Llama-3.2-3B-Instruct-4bit"),
        )
    )

    return LLMRuntime(backend=backend, model=model, client=client)
