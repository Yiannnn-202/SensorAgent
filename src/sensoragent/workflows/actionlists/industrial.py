"""Industrial pick-and-place ActionList definitions."""

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind


def build_industrial_pick_place_actionlist() -> ActionList:
  """Build the industrial pick → verify_grasp → place → verify_place workflow."""

  return ActionList(
    name="industrial.pick_place_actionlist",
    description="Industrial pick-and-place with grasp and place verification.",
    inputs={"object_query": "string", "target": "string"},
    tags=("industrial", "pick-place", "verify"),
    steps=[
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target="vision.mock_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
      ),
      ActionStep(
        name="plan_pick",
        kind=ActionStepKind.TOOL,
        target="robot.plan_top_down_pick",
        input={"pose_3d": "{{ object.pose_3d }}"},
        save_as="pick_plan",
      ),
      ActionStep(
        name="pick",
        kind=ActionStepKind.SKILL,
        target="robot.pick",
        input={
          "plan": "{{ pick_plan.plan }}",
          "object_id": "{{ object.object_id }}",
        },
        save_as="pick_result",
      ),
      ActionStep(
        name="verify_grasp",
        kind=ActionStepKind.SKILL,
        target="robot.verify_grasp",
        input={},
        save_as="grasp_check",
      ),
      ActionStep(
        name="resolve_place_target",
        kind=ActionStepKind.TOOL,
        target="robot.resolve_place_target",
        input={"target": "{{ target }}"},
        save_as="place_target",
      ),
      ActionStep(
        name="plan_place",
        kind=ActionStepKind.TOOL,
        target="robot.plan_place",
        input={"place_pose": "{{ place_target.place_pose }}"},
        save_as="place_plan",
      ),
      ActionStep(
        name="place",
        kind=ActionStepKind.SKILL,
        target="robot.place",
        input={
          "plan": "{{ place_plan.plan }}",
          "object_id": "{{ object.object_id }}",
          "target": "{{ target }}",
        },
        save_as="place_result",
      ),
      ActionStep(
        name="verify_place",
        kind=ActionStepKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
      ),
    ],
  )
