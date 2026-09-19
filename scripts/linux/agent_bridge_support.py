#!/usr/bin/env python3
"""Shared bridge readiness helpers for submission agent launch scripts."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.config import load_config  # noqa: E402


def json_dump(value: Any) -> str:
  return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def print_section(title: str, value: Any | None = None) -> None:
  print(f"\n=== {title} ===")
  if value is not None:
    print(json_dump(value))


def http_get(endpoint: str, path: str, timeout: float = 4.0) -> dict:
  response = requests.get(f"{endpoint.rstrip('/')}{path}", timeout=timeout)
  response.raise_for_status()
  body = response.json()
  if not isinstance(body, dict):
    raise RuntimeError(f"{path} returned non-object JSON")
  return body


def wait_for_bridge(endpoint: str, wait_seconds: float) -> None:
  deadline = time.monotonic() + wait_seconds
  last_error: Exception | None = None
  while time.monotonic() <= deadline:
    try:
      health = http_get(endpoint, "/health", timeout=2.0)
      if health.get("success") is True:
        print_section("bridge health", health)
        return
    except (requests.RequestException, ValueError, RuntimeError) as exc:
      last_error = exc
    time.sleep(1.0)
  raise RuntimeError(f"Bridge did not become healthy at {endpoint}: {last_error}")


def wait_for_ready(
  endpoint: str,
  wait_seconds: float,
  required_interfaces: tuple[str, ...],
) -> None:
  deadline = time.monotonic() + wait_seconds
  last_ready: dict | None = None
  while time.monotonic() <= deadline:
    try:
      ready = http_get(endpoint, "/ready", timeout=2.0)
      last_ready = ready
      state = ready.get("state", {})
      if not isinstance(state, dict):
        state = {}
      if all(state.get(name) is True for name in required_interfaces):
        print_section("ros interface readiness", ready)
        return
    except requests.HTTPError as exc:
      if exc.response is not None and exc.response.status_code == 404:
        print_section(
          "ros interface readiness",
          {
            "checked": False,
            "reason": "Bridge does not expose /ready.",
          },
        )
        return
    except (requests.RequestException, ValueError, RuntimeError):
      pass
    time.sleep(1.0)
  raise RuntimeError(
    "Required ROS interfaces did not become ready "
    f"{list(required_interfaces)}: {last_ready}"
  )


def check_bridge(endpoint: str) -> dict:
  health = http_get(endpoint, "/health")
  state = http_get(endpoint, "/state")
  gripper = http_get(endpoint, "/gripper/state")
  print_section("bridge health", health)
  print_section("initial robot state", state)
  print_section("initial gripper state", gripper)
  if health.get("success") is not True:
    raise RuntimeError(f"Bridge health failed: {health}")
  if state.get("success") is not True:
    raise RuntimeError(f"Bridge state failed: {state}")
  return state


def load_agent_config(config_path: Path, endpoint: str | None):
  config = load_config(config_path)
  if endpoint is None:
    return config
  robot = dict(config.integrations.robot)
  robot["endpoint"] = endpoint
  return replace(
    config,
    integrations=replace(config.integrations, robot=robot),
  )
