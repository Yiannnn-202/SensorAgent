"""Unit tests for skill runtime error behavior."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from sensoragent.logger import TaskLogger
from sensoragent.schemas import SkillCall, SkillResult, SkillSpec, TraceContext
from sensoragent.skills import SkillContext, SkillRegistry, SkillRuntime
from sensoragent.tools import ToolRegistry, ToolRuntime


class SkillErrorTest(TestCase):
  def test_skill_runtime_wraps_unexpected_skill_failure(self) -> None:
    class BrokenSkill:
      spec = SkillSpec(name="broken.skill", description="Broken skill")

      def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
        raise RuntimeError("boom")

    logger = TaskLogger()
    tool_runtime = ToolRuntime(ToolRegistry(), logger)
    registry = SkillRegistry()
    registry.register(BrokenSkill())
    runtime = SkillRuntime(registry, tool_runtime, logger)

    result = runtime.invoke("broken.skill", {}, TraceContext())

    self.assertFalse(result.success)
    self.assertIn("Skill execution failed for broken.skill", result.error or "")
    self.assertIn("skill_call_finished", list(logger.events()))
