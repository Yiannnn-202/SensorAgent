"""Mock ActionList definitions."""

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind


def build_mock_pick_place_actionlist() -> ActionList:
  """Build a deterministic mock pick-and-place ActionList."""

  return ActionList(
    name="mock.pick_place_actionlist",
    description="Mock pick-and-place action list using mock vision and robot tools.",
    inputs={"object_query": "string", "target": "string"},
    tags=("mock", "pick-place"),
    steps=[
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target="vision.mock_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
      ),
      ActionStep(
        name="pick_object",
        kind=ActionStepKind.TOOL,
        target="robot.mock_pick",
        input={
          "object_id": "{{ object.object_id }}",
          "pose_3d": "{{ object.pose_3d }}",
        },
        save_as="pick",
      ),
      ActionStep(
        name="place_object",
        kind=ActionStepKind.TOOL,
        target="robot.mock_place",
        input={
          "object_id": "{{ object.object_id }}",
          "target": "{{ target }}",
        },
        save_as="place",
      ),
    ],
  )
