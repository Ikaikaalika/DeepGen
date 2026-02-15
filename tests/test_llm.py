import pytest

from deepgen.services.llm import AnthropicClient, LLMConfig, LLMError, OpenAIClient, build_llm_client


def test_build_llm_client_openai_and_anthropic_selection():
    openai_client = build_llm_client(
        LLMConfig(
            backend="openai",
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
        )
    )
    assert isinstance(openai_client, OpenAIClient)

    anthropic_client = build_llm_client(
        LLMConfig(
            backend="anthropic",
            anthropic_api_key="test-ant-key",
            anthropic_model="claude-3-5-sonnet-latest",
        )
    )
    assert isinstance(anthropic_client, AnthropicClient)


def test_build_llm_client_returns_none_when_missing_required_keys():
    assert build_llm_client(LLMConfig(backend="openai", openai_api_key="")) is None
    assert build_llm_client(LLMConfig(backend="anthropic", anthropic_api_key="")) is None


def test_build_llm_client_rejects_unknown_backend():
    with pytest.raises(LLMError):
        build_llm_client(LLMConfig(backend="unknown-provider"))
