"""OpenAI-compatible LLM client used by planners."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from sensoragent.config import load_dotenv


class LlmError(Exception):
  """Base class for LLM integration errors."""


@dataclass(frozen=True)
class LlmConfig:
  """Configuration for an OpenAI-compatible chat completion endpoint."""

  provider: str
  base_url: str
  api_key: str
  model: str
  timeout_seconds: float = 30.0


def load_llm_config_from_env() -> LlmConfig:
  """Load LLM configuration from .env and process environment."""

  load_dotenv()
  provider = os.environ.get("SENSORAGENT_LLM_PROVIDER", "deepseek")
  base_url = os.environ.get("SENSORAGENT_LLM_BASE_URL", "https://api.deepseek.com")
  api_key = os.environ.get("SENSORAGENT_LLM_API_KEY", "")
  model = os.environ.get("SENSORAGENT_LLM_MODEL", "deepseek-v4-flash")
  if not api_key:
    raise LlmError("SENSORAGENT_LLM_API_KEY is required")
  return LlmConfig(provider=provider, base_url=base_url, api_key=api_key, model=model)


class OpenAICompatibleClient:
  """Minimal OpenAI-compatible chat-completions client."""

  def __init__(self, config: LlmConfig) -> None:
    self._config = config

  def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
    """Call the chat completions API and parse the response as JSON."""

    endpoint = self._config.base_url.rstrip("/") + "/chat/completions"
    payload = {
      "model": self._config.model,
      "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
      ],
      "temperature": 0,
      "response_format": {"type": "json_object"},
    }
    try:
      import requests
    except Exception as exc:
      raise LlmError("requests is required for LLM HTTP calls") from exc

    try:
      response = requests.post(
        endpoint,
        headers={
          "Authorization": f"******",
          "Content-Type": "application/json",
        },
        json=payload,
        timeout=self._config.timeout_seconds,
      )
      if response.status_code >= 400:
        raise LlmError(f"LLM HTTP error {response.status_code}: {response.text}")
      body = response.json()
    except Exception as exc:
      if isinstance(exc, LlmError):
        raise
      raise LlmError(f"LLM request failed: {exc}") from exc

    try:
      content = body["choices"][0]["message"]["content"]
      return json.loads(content)
    except Exception as exc:
      raise LlmError(f"LLM returned invalid JSON content: {body}") from exc
