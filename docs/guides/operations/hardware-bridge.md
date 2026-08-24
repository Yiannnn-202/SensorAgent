# Physical Hardware Bridge

`sensoragent_hardware_bridge` is a safety-gated adapter from SensorAgent's
existing HTTP robot protocol to external ROS 2 hardware services. It is not a
driver and does not replace vendor arm, gripper, camera, emergency-stop, or
cell-safety systems.

## Safety Default

The bridge ships with `allow_motion: false`. Its health, readiness, and gripper
state endpoints may be queried, but every arm and gripper motion endpoint returns
`MOTION_DISABLED`. Do not set `allow_motion:=true` until the live ROS service
types, pose frame, hand-eye calibration, TCP, workspace, speed limit, and stop
procedure have been verified at the physical cell.

## Prerequisites

The active ROS environment must contain the hardware driver's interface packages:

```bash
ros2 pkg prefix arm_control_interfaces
ros2 pkg prefix op_control_interfaces
```

It must also expose the configured hardware services and state topic. The default
bridge parameters are only examples and must be verified against the live graph:

```text
/task/arm/movej
/task/arm/movel
/task/arm/move_to_pose
/task/arm/get_current_pose
/task/op/open
/task/op/close
/omnipicker_state
```

## Build And Start

Source the external hardware workspace first so `colcon` can resolve its custom
interface packages, then build this bridge in SensorAgent's workspace:

```bash
source /opt/ros/humble/setup.bash
source /path/to/hardware/install/setup.bash
cd ~/workspace/SensorAgent/ros2_ws
colcon build --packages-select sensoragent_hardware_bridge
source install/setup.bash
ros2 run sensoragent_hardware_bridge hardware_bridge
```

The default listener is `http://127.0.0.1:8766`. Verify only non-motion endpoints:

```bash
curl http://127.0.0.1:8766/health
curl http://127.0.0.1:8766/ready
curl http://127.0.0.1:8766/state
curl http://127.0.0.1:8766/gripper/state
```

## Motion Gate

The bridge implements the existing SensorAgent robot-control HTTP contract:

```text
POST /move-joints
POST /move-pose
POST /move-linear
POST /gripper/open
POST /gripper/close
POST /stop
GET  /state
GET  /gripper/state
```

Every motion endpoint remains disabled until `allow_motion: true` is set. Arm
poses are constrained to the configured workspace and speed limit; the bridge
converts SensorAgent joint radians to the physical degree service and gripper
opening metres to OmniPicker's normalized position. `POST /dry-run/approach`
remains available as an additional exact-pose approval gate for first approach
experiments.

Copy `hardware_bridge_approach.example.yaml` to an ignored local file and fill
it from a fresh reviewed dry-run report. Never reuse an approach pose after the
object, camera, hand-eye calibration, TCP, or workspace changes.

Copy `configs/robot_hardware.example.yaml` to an ignored local configuration after
the bridge reports the expected services as ready. It references the local original
Grounding DINO checkpoint and does not enable motion by itself.
