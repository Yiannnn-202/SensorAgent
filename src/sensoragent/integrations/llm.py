"""OpenAI-compatible LLM client used by planners."""

from __future__ import annotations

import json
import os
from base64 import b64encode
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

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


def load_vlm_config_from_env() -> LlmConfig:
  """Load the separately configured OpenAI-compatible vision model."""

  load_dotenv()
  api_key = os.environ.get("SENSORAGENT_VLM_API_KEY", "")
  model = os.environ.get("SENSORAGENT_VLM_MODEL", "")
  if not api_key or not model:
    raise LlmError("SENSORAGENT_VLM_API_KEY and SENSORAGENT_VLM_MODEL are required")
  return LlmConfig(
    provider=os.environ.get("SENSORAGENT_VLM_PROVIDER", "kimi"),
    base_url=os.environ.get("SENSORAGENT_VLM_BASE_URL", "https://api.moonshot.cn/v1"),
    api_key=api_key,
    model=model,
    timeout_seconds=float(os.environ.get("SENSORAGENT_VLM_TIMEOUT_SECONDS", "90")),
  )


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
          "Authorization": f"Bearer {self._config.api_key}",
          "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
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

  def complete_vision_json(self, system_prompt: str, user_prompt: str, image_path: str) -> dict:
    """Send one local image to an OpenAI-compatible VLM and parse JSON output."""

    image = Path(image_path)
    if not image.is_file():
      raise LlmError(f"VLM image does not exist: {image}")
    image_bytes = image.read_bytes()
    mime_type = "image/png" if image.suffix.casefold() == ".png" else "image/jpeg"
    try:
      from PIL import Image
      with Image.open(image) as source:
        source.thumbnail((1280, 1280))
        compressed = BytesIO()
        source.convert("RGB").save(compressed, format="JPEG", quality=85, optimize=True)
        image_bytes = compressed.getvalue()
        mime_type = "image/jpeg"
    except ImportError:
      pass
    data_url = f"data:{mime_type};base64,{b64encode(image_bytes).decode('ascii')}"
    payload = {
      "model": self._config.model,
      "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
          {"type": "text", "text": user_prompt},
          {"type": "image_url", "image_url": {"url": data_url}},
        ]},
      ],
      # Kimi vision models currently accept only temperature=1.
      "temperature": 1,
      "response_format": {"type": "json_object"},
    }
    try:
      import requests
      response = requests.post(
        self._config.base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {self._config.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=self._config.timeout_seconds,
      )
      if response.status_code >= 400:
        raise LlmError(f"VLM HTTP error {response.status_code}: {response.text}")
      body = response.json()
      return json.loads(body["choices"][0]["message"]["content"])
    except Exception as exc:
      if isinstance(exc, LlmError):
        raise
      raise LlmError(f"VLM request failed: {exc}") from exc
