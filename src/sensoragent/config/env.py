"""Environment-based configuration path resolution."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_CONFIG_DIR = Path("configs")
DEFAULT_ENV = "mock"


def load_dotenv(path: str | Path = ".env", *, environ: dict[str, str] | None = None) -> None:
  """Load simple KEY=VALUE pairs from a .env file into the environment."""

  env = environ if environ is not None else os.environ
  env_path = Path(path)
  if not env_path.exists():
    return
  for raw_line in env_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
      continue
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if key and key not in env:
      env[key] = value


def resolve_config_path(
  explicit_path: str | Path | None = None,
  *,
  config_dir: str | Path = DEFAULT_CONFIG_DIR,
  environ: dict[str, str] | None = None,
) -> Path:
  """Resolve which configuration file should be loaded.

  Priority:
    1. Explicit path argument.
    2. SENSORAGENT_CONFIG environment variable.
    3. SENSORAGENT_ENV environment variable mapped to configs/<env>.yaml.
    4. configs/mock.yaml.
  """

  env = environ if environ is not None else os.environ
  if explicit_path is not None:
    return Path(explicit_path)

  config_value = env.get("SENSORAGENT_CONFIG")
  if config_value:
    return Path(config_value)

  env_name = env.get("SENSORAGENT_ENV", DEFAULT_ENV)
  return Path(config_dir) / f"{env_name}.yaml"
