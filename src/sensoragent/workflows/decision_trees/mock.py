"""Mock DecisionTree definitions."""

from sensoragent.schemas import (
  ConditionOperator,
  DecisionCondition,
  DecisionNode,
  DecisionNodeKind,
  DecisionTree,
)


def build_mock_retry_pick_tree() -> DecisionTree:
  """Build a tree that retries a failed pick once."""

  return DecisionTree(
    name="mock.retry_pick_tree",
    start="detect",
    nodes=[
      DecisionNode(
        name="detect",
        kind=DecisionNodeKind.TOOL,
        target="vision.mock_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
        on_success="pick",
      ),
      DecisionNode(
        name="pick",
        kind=DecisionNodeKind.TOOL,
        target="robot.mock_fail_once_pick",
        input={
          "object_id": "{{ object.object_id }}",
          "pose_3d": "{{ object.pose_3d }}",
        },
        save_as="pick",
        max_retries=1,
        on_success="success",
        on_failure="failure",
      ),
      DecisionNode(name="success", kind=DecisionNodeKind.TERMINAL, terminal_success=True),
      DecisionNode(name="failure", kind=DecisionNodeKind.TERMINAL, terminal_success=False),
    ],
  )


def build_mock_not_found_branch_tree() -> DecisionTree:
  """Build a tree that branches when object detection finds nothing."""

  return DecisionTree(
    name="mock.not_found_branch_tree",
    start="detect",
    nodes=[
      DecisionNode(
        name="detect",
        kind=DecisionNodeKind.TOOL,
        target="vision.mock_not_found",
        input={"query": "{{ object_query }}"},
        save_as="object",
        on_success="found_check",
      ),
      DecisionNode(
        name="found_check",
        kind=DecisionNodeKind.CONDITION,
        condition=DecisionCondition(
          path="object.found",
          operator=ConditionOperator.EQUALS,
          value=True,
        ),
        on_success="success",
        on_failure="not_found",
      ),
      DecisionNode(name="success", kind=DecisionNodeKind.TERMINAL, terminal_success=True),
      DecisionNode(name="not_found", kind=DecisionNodeKind.TERMINAL, terminal_success=False),
    ],
  )
