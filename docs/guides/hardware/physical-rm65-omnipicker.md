# Physical RM65 and OmniPicker

This guide describes the physical-hardware adapter currently included in
SensorAgent. It is for supervised laboratory integration, not a replacement for
vendor safety documentation, emergency-stop procedures, calibration, or site
approval.

## Scope

The current physical workflow is `hardware.pick_object_actionlist`:

```text
observe
→ capture synchronized RGB and point cloud
→ Grounded DINO + SAM2 detection
→ choose a configured pick profile
→ plan
→ open, approach, grasp, close, lift
→ verify grasp
→ return to observe
```

It does not yet implement physical place, bin sorting, post-place visual
verification, or recovery branches.

## Required external ROS packages

The repository does not vendor the physical drivers. Before starting the stack,
the host must provide a sourced ROS 2 Humble installation and the external
Island-Arm workspace containing:

```text
rm_driver
arm_control
arm_control_interfaces
op_control
op_control_interfaces
vision_dep
```

The included launch file also uses `rm_description`, `robot_state_publisher`,
and `tf2_ros`.

## Configuration and startup

Use `configs/robot_hardware_sensoragent_v1i_baseline.yaml` as the checked-in
baseline. Create machine-specific overrides in
`configs/robot_hardware.local.yaml`; that filename is ignored by Git.

The agent talks to the physical bridge on port `8766`:

```text
HttpRobotControlClient
→ http://127.0.0.1:8766
→ sensoragent_hardware_bridge
→ RM65 and OmniPicker ROS services
```

Start the ROS stack on Ubuntu:

```bash
bash scripts/linux/start_hardware_stack.sh
curl http://127.0.0.1:8766/health
curl http://127.0.0.1:8766/ready
```

The script sources ROS 2, the external Island-Arm installation, and this
repository's built ROS workspace before launching
`sensoragent_hardware_bridge hardware_stack.launch.py`.

## Motion safety gate

`ros2_ws/src/sensoragent_hardware_bridge/config/hardware_bridge.yaml` defaults
to:

```yaml
allow_motion: false
```

With that value, all arm and gripper motion routes return `MOTION_DISABLED`.
Do not enable motion until the cell, coordinate transform, workspace, speed
limit, stop path, and supervised dry run have been reviewed.

The bridge is localhost-only and applies these checks:

- pose frame and normalized quaternion;
- configured workspace bounds;
- speed cap and service/response timeouts;
- current pose and OmniPicker state queries;
- `/rm_driver/move_stop_cmd` on `POST /stop`.

`POST /dry-run/approach` adds a stricter gate: it requires
`approval: EXECUTE_APPROACH_ONLY` and a locally registered approach pose within
the configured position and orientation tolerances. It is intentionally more
restrictive than normal motion routes; it does not certify arbitrary motion.

## RGB-D capture and planning

`vision.capture_frame` runs
`scripts/linux/capture_hardware_rgb_cloud.py`, which synchronizes:

```text
/vision/raw    bgr8 RGB image
/vision/cloud  PointCloud2 with x, y, z, u, v float32 fields
```

It writes `rgb.png`, `rgb.npy`, `cloud_xyzuv.npy`, and `manifest.json` under
`logs/vision/hardware_latest/`. The manifest contains the timestamped
`T_base_camera` transform used by the hardware ActionList.

The checked-in `short_bolt` profile uses
`robot.plan_short_bolt_pick`: SAM2 mask-selected point cloud, PCA orientation,
shaft/head-aware grasp point selection, TCP compensation, and workspace checks.
`robot.plan_mask_pointcloud_pick` is an experimental generic alternative; it is
not enabled by default and is not referenced by any shipped ActionList.

## HTTP routes

| Route | Physical ROS operation |
| --- | --- |
| `POST /move-joints` | `MoveJDeg` after radians-to-degrees conversion |
| `POST /move-pose` | `MoveToPose` |
| `POST /move-linear` | `MoveL` |
| `GET /state` | `GetCurrentPose` and current gripper state |
| `POST /gripper/open` | OmniPicker `SetPosition` |
| `POST /gripper/close` | OmniPicker `Close` or `SetPosition` |
| `GET /gripper/state` | `/omnipicker_state` subscription state |
| `POST /stop` | Publish `/rm_driver/move_stop_cmd` |

## Validation boundary

The default Python test suite validates adapters and workflow wiring with fakes
or ROS stubs. It does not move physical hardware. Treat live motion, grasp
stability, camera calibration, and end-to-end success rate as separate,
supervised acceptance work.
