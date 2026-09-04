"""Tests for runtime compatibility helpers."""

from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class PythonCompatTest(TestCase):
  def test_str_enum_fallback_matches_value_string_behavior(self) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
      if name == "enum" and "StrEnum" in fromlist:
        raise ImportError("simulate Python 3.10 enum module")
      return real_import(name, globals, locals, fromlist, level)

    builtins.__import__ = fake_import
    try:
      spec = importlib.util.spec_from_file_location(
        "sensoragent_compat_py310_test",
        ROOT / "src" / "sensoragent" / "_compat.py",
      )
      module = importlib.util.module_from_spec(spec)
      assert spec is not None and spec.loader is not None
      spec.loader.exec_module(module)
    finally:
      builtins.__import__ = real_import

    class Example(module.StrEnum):
      VALUE = "value"

    self.assertEqual(Example.VALUE, "value")
    self.assertEqual(str(Example.VALUE), "value")
    self.assertIs(Example("value"), Example.VALUE)
