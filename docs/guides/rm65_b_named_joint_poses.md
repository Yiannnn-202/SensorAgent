# RM65-B Named Joint Pose Tuning

This guide records reusable RM65-B joint-space poses for the Gazebo/MoveIt2
industrial setup. Store tuned values in `configs/robot_sim.yaml` under
`scene.joint_poses`, not in workflow Python constants.

## Named poses

Use radians in this exact order:

```text
[joint1, joint2, joint3, joint4, joint5, joint6]
```

Recommended names:

| Name | Purpose |
| --- | --- |
| `home_joints` | Safe start/end posture. |
| `observe_joints` | Arm outside the top RGB-D camera view so table objects are visible. |
| `pick_staging_joints` | Safe pre-pick posture near the workbench. |
| `carry_joints` | Stable posture after grasp/lift before the next action. |
| `place_staging_joints` | Safe pre-place posture near the target grid/bin area. |

The existing workflow fallback is:

```yaml
place_staging_joints: [-0.17, -0.57, -0.61, 0.0, -1.96, 0.0]
```

## Start Gazebo, MoveIt2, and RViz

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

Wait until Gazebo, MoveIt2, RViz, and the HTTP bridge are ready:

```bash
curl http://127.0.0.1:8765/ready
ros2 control list_controllers
ros2 topic echo /joint_states --once
```

## Tune one pose in RViz

1. In RViz, open the **MotionPlanning** panel.
2. Select planning group `rm_group`.
3. Use the **Joints** controls or interactive marker to move the arm.
4. Keep **Avoid Collisions** enabled.
5. Click **Plan** first. Only click **Execute** after the planned path is valid.
6. Inspect Gazebo and RViz for clearance from the workbench, target grid/bin,
   camera rig, robot base, and the gripper fingers.
7. For `observe_joints`, capture a camera frame and verify the arm/gripper does
   not cover the objects or target grid:

```bash
cd ~/SensorAgent
python3 scripts/linux/capture_gazebo_rgbd_frame.py --out-dir logs/vision/observe_check
```

Open `logs/vision/observe_check/rgb.ppm` and confirm the table/object region is
clear.

## Record the current joint pose

Run this in a terminal with the ROS 2 workspace sourced:

```bash
cd ~/SensorAgent
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash

python3 scripts/linux/record_rm65_joint_pose.py observe_joints
```

The script reads one `/joint_states` sample, extracts `joint1` to `joint6`, and
prints a YAML snippet. Repeat for each pose:

```bash
python3 scripts/linux/record_rm65_joint_pose.py home_joints
python3 scripts/linux/record_rm65_joint_pose.py pick_staging_joints
python3 scripts/linux/record_rm65_joint_pose.py carry_joints
python3 scripts/linux/record_rm65_joint_pose.py place_staging_joints
```

Paste the six-value lists into:

```text
configs/robot_sim.yaml
configs/robot_mock.yaml
```

under:

```yaml
scene:
  robot_joint_order: [joint1, joint2, joint3, joint4, joint5, joint6]
  joint_poses:
    home_joints: [...]
    observe_joints: [...]
    pick_staging_joints: [...]
    carry_joints: [...]
    place_staging_joints: [...]
```

## Verify recorded poses through the bridge

After editing config, test each pose by sending it through the same HTTP-backed
`robot.move_joints` path used by SensorAgent. For example:

```bash
PYTHONPATH=src .venv312/bin/python - observe_joints <<'PY'
import sys

from sensoragent.agent import build_agent_from_config
from sensoragent.config import load_config
from sensoragent.schemas import TraceContext

pose_name = sys.argv[1]
config = load_config("configs/robot_sim.yaml")
joints = config.scene.joint_poses.get(pose_name)
if not isinstance(joints, list) or len(joints) != 6:
    raise SystemExit(f"{pose_name} is not recorded in configs/robot_sim.yaml")

bundle = build_agent_from_config("configs/robot_sim.yaml")
result = bundle.tool_runtime.invoke(
    "robot.move_joints",
    {"joints": joints, "speed": 0.5, "wait": True},
    TraceContext(),
)
print({"success": result.success, "error": result.error})
raise SystemExit(0 if result.success else 1)
PY
```

Or use the bridge endpoint directly with the recorded list:

```bash
curl -X POST http://127.0.0.1:8765/move-joints \
  -H 'Content-Type: application/json' \
  -d '{"joints":[J1,J2,J3,J4,J5,J6],"speed":0.5,"wait":true}'
```

Then confirm the measured joints:

```bash
python3 scripts/linux/record_rm65_joint_pose.py measured_check --format json
```

The measured values should be close to the command target. If MoveIt reports a
collision, unreachable target, excessive wrist rotation, or the camera image is
blocked, retune the pose in RViz and overwrite the config value.

## Current code usage

`home_joints` is used by Gazebo demo reset scripts. `place_staging_joints` is
used by the industrial pick/place ActionList, vision ActionList, place-only
ActionList, and recovery DecisionTree. `observe_joints`, `pick_staging_joints`,
and `carry_joints` are reserved config slots for the next workflow optimization
step.
