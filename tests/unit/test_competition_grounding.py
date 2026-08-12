"""Tests for competition command grounding and oracle instance selection."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from sensoragent.config import load_config
from sensoragent.grounding import (
  GroundingStatus,
  ObjectOntology,
  OracleInstanceResolver,
  SortingCommandGrounder,
)


ROOT = Path(__file__).resolve().parents[2]


class CompetitionGroundingTest(TestCase):
  @classmethod
  def setUpClass(cls) -> None:
    cls.config = load_config(ROOT / "configs" / "robot_sorting_sim.yaml")
    cls.ontology = ObjectOntology.from_mapping(cls.config.scene.object_ontology)
    cls.grounder = SortingCommandGrounder(
      cls.ontology,
      cls.config.scene.place_targets,
    )
    cls.resolver = OracleInstanceResolver(
      cls.ontology,
      cls.config.scene.objects,
    )

  def test_alias_target_and_nearest_selector_are_grounded(self) -> None:
    intent = self.grounder.ground("把离机械臂最近的滚柱放到三号格")

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertEqual(intent.object_class, "roller")
    self.assertEqual(intent.target, "bin_cell_3")
    self.assertEqual(intent.selector.relation, "nearest")
    self.assertEqual(intent.selector.ordinal, 1)
    selected, error = self.resolver.resolve(intent)
    self.assertIsNone(error)
    self.assertEqual(selected.instance_id, "metal_roller_01")

  def test_object_ordinal_is_separate_from_target_ordinal(self) -> None:
    intent = self.grounder.ground("把最前面第二个六角螺母放到第六号格")

    self.assertEqual(intent.selector.relation, "front")
    self.assertEqual(intent.selector.ordinal, 2)
    self.assertEqual(intent.target, "bin_cell_6")
    selected, error = self.resolver.resolve(intent)
    self.assertIsNone(error)
    self.assertEqual(selected.instance_id, "metal_hex_nut_02")

  def test_multiple_instances_without_selector_require_clarification(self) -> None:
    intent = self.grounder.ground("把短螺栓放到一号格")
    selected, error = self.resolver.resolve(intent)

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertIsNone(selected)
    self.assertIn("检测到 3 个", error)

  def test_unknown_class_is_not_mapped_to_a_supported_object(self) -> None:
    intent = self.grounder.ground("把扳手放到二号格")

    self.assertEqual(intent.status, GroundingStatus.UNSUPPORTED)
    self.assertEqual(intent.reason, "UNKNOWN_OBJECT_CLASS")

  def test_all_objects_is_explicitly_rejected_until_batch_loop_exists(self) -> None:
    intent = self.grounder.ground("把所有滚轮放到三号格")

    self.assertEqual(intent.status, GroundingStatus.UNSUPPORTED)
    self.assertEqual(intent.reason, "BATCH_TASK_NOT_ENABLED")

  def test_invalid_target_requests_clarification(self) -> None:
    intent = self.grounder.ground("把最近的滚轮放到十号格")

    self.assertEqual(intent.status, GroundingStatus.NEEDS_CLARIFICATION)
    self.assertEqual(intent.reason, "TARGET_MISSING_OR_INVALID")

  def test_english_alias_and_target_are_grounded(self) -> None:
    intent = self.grounder.ground(
      "put the nearest short bolt into bin_cell_4"
    )

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertEqual(intent.object_class, "short_bolt")
    self.assertEqual(intent.selector.relation, "nearest")
    self.assertEqual(intent.selector.ordinal, 1)
    self.assertEqual(intent.target, "bin_cell_4")
