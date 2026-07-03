"""
Pluggable LLM Provider Abstraction for Resume Kit

Inspired by unseal/engine/backend/llm_providers.py but using synchronous
requests (we already depend on requests) and focused on chat completion +
model listing.

Supported providers:
  ollama      - Ollama local/remote (/api/chat and /api/tags)
  openai      - OpenAI API
  anthropic   - Anthropic Claude API
  azure       - Azure OpenAI
  vllm        - vLLM OpenAI-compatible
  lmstudio    - LM Studio OpenAI-compatible
  custom      - Any OpenAI-compatible endpoint

Settings can come from environment variables or a per-request settings dict.
"""
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    model: Optional[str] = None


class LLMProvider(ABC):
    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 120,
        temperature: float = 0.4,
        **kwargs,
    ):
        self.model = model
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature

    @abstractmethod
    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        pass

    @abstractmethod
    def list_models(self) -> List[Dict[str, Any]]:
        pass


class OllamaProvider(LLMProvider):
    """Ollama local/remote provider."""

    def __init__(self, **kwargs):
        base_url = kwargs.pop("base_url", None) or os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
        super().__init__(base_url=base_url, **kwargs)

    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": kwargs.get("temperature", self.temperature)},
            "format": kwargs.get("format"),
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", {})
        return LLMResponse(
            content=msg.get("content", ""),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            model=self.model,
        )

    def list_models(self) -> List[Dict[str, Any]]:
        resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [
            {"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 2)}
            for m in data.get("models", [])
        ]


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI API and OpenAI-compatible endpoints (vLLM, LM Studio, custom)."""

    def __init__(self, **kwargs):
        base_url = kwargs.pop("base_url", None) or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        api_key = kwargs.pop("api_key", None) or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        super().__init__(base_url=base_url, api_key=api_key, **kwargs)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": False,
        }
        # Some local endpoints support response_format, but many do not.
        # Only send it when explicitly requested by the caller.
        if "response_format" in kwargs:
            payload["response_format"] = kwargs["response_format"]

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        usage = data.get("usage", {})
        return LLMResponse(
            content=msg.get("content", ""),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            model=data.get("model", self.model),
        )

    def list_models(self) -> List[Dict[str, Any]]:
        resp = requests.get(f"{self.base_url}/models", headers=self._headers(), timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [
            {"name": m.get("id", m.get("name", "")), "size_gb": None}
            for m in data.get("data", [])
        ]


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, **kwargs):
        base_url = kwargs.pop("base_url", None) or "https://api.anthropic.com/v1"
        api_key = kwargs.pop("api_key", None) or os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        super().__init__(base_url=base_url, api_key=api_key, **kwargs)

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        system = None
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": False,
        }
        if system:
            payload["system"] = system

        resp = requests.post(
            f"{self.base_url}/messages",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            model=data.get("model", self.model),
        )

    def list_models(self) -> List[Dict[str, Any]]:
        # Anthropic does not publish a public models endpoint.
        return [{"name": self.model, "size_gb": None}]


class AzureOpenAIProvider(OpenAICompatibleProvider):
    """Azure OpenAI provider."""

    def __init__(self, **kwargs):
        base_url = kwargs.pop("base_url", None) or os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = kwargs.pop("api_key", None) or os.getenv("AZURE_OPENAI_API_KEY")
        api_version = kwargs.pop("api_version", None) or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        deployment = kwargs.pop("deployment", None) or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        super().__init__(base_url=base_url, api_key=api_key, **kwargs)
        self.api_version = api_version
        self.deployment = deployment or self.model

    def _headers(self) -> Dict[str, str]:
        return {
            "api-key": self.api_key or "",
            "Content-Type": "application/json",
        }

    def chat(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": False,
        }
        resp = requests.post(
            f"{self.base_url}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        usage = data.get("usage", {})
        return LLMResponse(
            content=msg.get("content", ""),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            model=self.deployment,
        )

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"name": self.deployment, "size_gb": None}]


PROVIDER_REGISTRY: Dict[str, type] = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "azure": AzureOpenAIProvider,
    "vllm": OpenAICompatibleProvider,
    "lmstudio": OpenAICompatibleProvider,
    "custom": OpenAICompatibleProvider,
}


def provider_label(key: str) -> str:
    labels = {
        "ollama": "Ollama",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "azure": "Azure OpenAI",
        "vllm": "vLLM",
        "lmstudio": "LM Studio",
        "custom": "Custom OpenAI-compatible",
    }
    return labels.get(key, key)


def get_provider(settings: Optional[Dict[str, Any]] = None) -> LLMProvider:
    """Factory: create a provider from env vars or an explicit settings dict."""
    s = settings or {}
    provider_name = (s.get("provider") or os.getenv("LLM_PROVIDER", "ollama")).lower()
    model = s.get("model") or os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL", "llama3.2")

    provider_class = PROVIDER_REGISTRY.get(provider_name)
    if not provider_class:
        raise ValueError(f"Unknown LLM provider: {provider_name}. Options: {list(PROVIDER_REGISTRY.keys())}")

    kwargs = {
        "model": model,
        "timeout": int(s.get("timeout") or os.getenv("LLM_TIMEOUT", "120")),
        "temperature": float(s.get("temperature") or os.getenv("LLM_TEMPERATURE", "0.4")),
    }

    if provider_name in ("openai", "vllm", "lmstudio", "custom"):
        kwargs["base_url"] = s.get("base_url") or os.getenv("LLM_BASE_URL")
        kwargs["api_key"] = s.get("api_key") or os.getenv("LLM_API_KEY")
    elif provider_name == "anthropic":
        kwargs["api_key"] = s.get("api_key") or os.getenv("LLM_API_KEY")
    elif provider_name == "azure":
        kwargs["base_url"] = s.get("base_url") or os.getenv("AZURE_OPENAI_ENDPOINT")
        kwargs["api_key"] = s.get("api_key") or os.getenv("AZURE_OPENAI_API_KEY")
        kwargs["deployment"] = s.get("deployment") or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        kwargs["api_version"] = s.get("api_version") or os.getenv("AZURE_OPENAI_API_VERSION")
    elif provider_name == "ollama":
        kwargs["base_url"] = s.get("base_url") or os.getenv("OLLAMA_URL")

    return provider_class(**kwargs)


def llm_chat(messages: List[Dict[str, str]], settings: Optional[Dict[str, Any]] = None, **kwargs) -> LLMResponse:
    """Simple one-off chat call."""
    provider = get_provider(settings)
    llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]
    return provider.chat(llm_messages, **kwargs)


def llm_list_models(settings: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """List available models from the configured provider."""
    provider = get_provider(settings)
    return provider.list_models()
