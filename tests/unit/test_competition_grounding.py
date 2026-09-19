"""Tests for competition command grounding and configured-scene instance selection."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from sensoragent.config import load_config
from sensoragent.grounding import (
  GroundingStatus,
  IntentAction,
  LlmAssistedSortingCommandGrounder,
  ObjectOntology,
  OracleInstanceResolver,
  SortingCommandGrounder,
)


ROOT = Path(__file__).resolve().parents[2]


class _FakeGroundingClient:
  def __init__(self, response: dict | Exception) -> None:
    self.response = response
    self.calls: list[tuple[str, str]] = []

  def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
    self.calls.append((system_prompt, user_prompt))
    if isinstance(self.response, Exception):
      raise self.response
    return dict(self.response)


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
    self.assertEqual(selected.instance_id, "metal_roller_03")

  def test_object_ordinal_is_separate_from_target_ordinal(self) -> None:
    intent = self.grounder.ground("把最前面第二个六角螺母放到第六号格")

    self.assertEqual(intent.selector.relation, "front")
    self.assertEqual(intent.selector.ordinal, 2)
    self.assertEqual(intent.target, "bin_cell_6")
    selected, error = self.resolver.resolve(intent)
    self.assertIsNone(error)
    self.assertEqual(selected.instance_id, "metal_hex_nut_01")

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

  def test_all_objects_with_target_grounds_as_batch_intent(self) -> None:
    intent = self.grounder.ground("把所有滚轮放到三号格")

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertEqual(intent.quantity, "all")
    self.assertEqual(intent.object_class, "roller")
    self.assertEqual(intent.target, "bin_cell_3")

  def test_all_objects_without_target_requires_clarification(self) -> None:
    intent = self.grounder.ground("把所有滚轮都拿起来")

    self.assertEqual(intent.status, GroundingStatus.NEEDS_CLARIFICATION)
    self.assertEqual(intent.reason, "TARGET_REQUIRED")

  def test_invalid_target_requests_clarification(self) -> None:
    intent = self.grounder.ground("把最近的滚轮放到十号格")

    self.assertEqual(intent.status, GroundingStatus.NEEDS_CLARIFICATION)
    self.assertEqual(intent.reason, "TARGET_MISSING_OR_INVALID")

  def test_multi_digit_invalid_target_is_not_partially_matched(self) -> None:
    for command in (
      "把最近的滚轮放到十二号格",
      "put the nearest roller into bin_cell_10",
      "put the nearest roller into cell10",
    ):
      with self.subTest(command=command):
        intent = self.grounder.ground(command)

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

  def test_llm_assisted_grounder_maps_supported_synonym_when_rules_fail(self) -> None:
    client = _FakeGroundingClient(
      {
        "status": "ready",
        "action": "pick_place",
        "object_class": "hex_nut",
        "selector": {"relation": "left", "ordinal": 1, "reference_frame": "camera"},
        "quantity": 1,
        "target": "bin_cell_1",
        "verify": True,
        "confidence": 0.87,
        "reason": "六边形小零件 maps to hex_nut",
      }
    )
    grounder = LlmAssistedSortingCommandGrounder(
      self.grounder,
      self.ontology,
      self.config.scene.place_targets,
      client,
    )

    intent = grounder.ground("把左边那个六边形小零件放到一号格")

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertEqual(intent.action, IntentAction.PICK_PLACE)
    self.assertEqual(intent.object_class, "hex_nut")
    self.assertEqual(intent.selector.relation, "left")
    self.assertEqual(intent.target, "bin_cell_1")
    self.assertEqual(intent.grounding_source, "llm_assisted")
    self.assertEqual(intent.grounding_confidence, 0.87)
    self.assertEqual(len(client.calls), 1)

  def test_llm_assisted_grounder_keeps_rule_result_when_rules_succeed(self) -> None:
    client = _FakeGroundingClient(RuntimeError("should not be called"))
    grounder = LlmAssistedSortingCommandGrounder(
      self.grounder,
      self.ontology,
      self.config.scene.place_targets,
      client,
    )

    intent = grounder.ground("把最近的滚轮放到二号格")

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertEqual(intent.object_class, "roller")
    self.assertEqual(intent.grounding_source, "rules")
    self.assertEqual(client.calls, [])

  def test_llm_assist_mode_can_refine_rule_ready_intent(self) -> None:
    client = _FakeGroundingClient(
      {
        "status": "ready",
        "action": "pick_place",
        "object_class": "short_bolt",
        "selector": {"relation": "left", "ordinal": 1, "reference_frame": "camera"},
        "quantity": 1,
        "target": "bin_cell_1",
        "verify": True,
        "confidence": 0.82,
        "reason": "operator likely means the left visible short bolt",
      }
    )
    grounder = LlmAssistedSortingCommandGrounder(
      self.grounder,
      self.ontology,
      self.config.scene.place_targets,
      client,
      mode="assist",
    )

    intent = grounder.ground("把短螺栓放到一号格")

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertEqual(intent.object_class, "short_bolt")
    self.assertEqual(intent.target, "bin_cell_1")
    self.assertEqual(intent.selector.relation, "left")
    self.assertEqual(intent.grounding_source, "llm_assisted")
    self.assertEqual(intent.grounding_confidence, 0.82)
    self.assertEqual(len(client.calls), 1)

  def test_llm_assist_mode_keeps_rule_ready_intent_when_model_output_is_invalid(self) -> None:
    client = _FakeGroundingClient(
      {
        "status": "ready",
        "action": "pick_place",
        "object_class": "dangerous_tool",
        "target": "bin_cell_1",
      }
    )
    grounder = LlmAssistedSortingCommandGrounder(
      self.grounder,
      self.ontology,
      self.config.scene.place_targets,
      client,
      mode="assist",
    )

    intent = grounder.ground("把最近的滚轮放到一号格")

    self.assertEqual(intent.status, GroundingStatus.READY)
    self.assertEqual(intent.object_class, "roller")
    self.assertEqual(intent.selector.relation, "nearest")
    self.assertEqual(intent.grounding_source, "rules")

  def test_llm_grounding_rejects_unknown_mode(self) -> None:
    with self.assertRaises(ValueError):
      LlmAssistedSortingCommandGrounder(
        self.grounder,
        self.ontology,
        self.config.scene.place_targets,
        _FakeGroundingClient({}),
        mode="freeform",
      )

  def test_llm_assisted_grounder_rejects_invalid_class_and_returns_rule_failure(self) -> None:
    client = _FakeGroundingClient(
      {
        "status": "ready",
        "action": "pick_place",
        "object_class": "unlisted_part",
        "target": "bin_cell_1",
      }
    )
    grounder = LlmAssistedSortingCommandGrounder(
      self.grounder,
      self.ontology,
      self.config.scene.place_targets,
      client,
    )

    intent = grounder.ground("把左边那个六边形小零件放到一号格")

    self.assertEqual(intent.status, GroundingStatus.UNSUPPORTED)
    self.assertEqual(intent.reason, "UNKNOWN_OBJECT_CLASS")
    self.assertEqual(intent.grounding_source, "rules")
