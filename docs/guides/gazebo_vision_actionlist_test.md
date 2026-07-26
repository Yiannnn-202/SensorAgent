# Gazebo RGB-D Vision to Pick-and-Place Test

This guide describes the first-pass text-guided Gazebo vision pipeline:

```text
operator text / object query
→ capture one Gazebo RGB-D frame
→ vision.open_vocab_detect
→ robot.plan_top_down_pick
→ robot.pick
→ robot.resolve_place_target
→ place steps
→ verify_place
```

The existing `industrial.pick_place_actionlist` remains unchanged and continues
to use `vision.config_detect`. This guide uses the parallel RGB-D workflow:

```text
industrial.vision_pick_place_actionlist
```

## 1. Optional vision dependencies

Install these in the Agent Python 3.12 environment:

```bash
cd ~/SensorAgent
source .venv312/bin/activate
python -m pip install -r requirements-vision.txt
```

Model weights are local runtime assets and are not committed. The default path is:

```text
models/vision/yoloe.pt
```

## 2. Start Gazebo

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

The industrial camera topics should be available:

```text
/industrial_camera/image
/industrial_camera/camera_info
/industrial_camera/depth_image
/industrial_camera/depth_camera_info
```

## 3. Capture one RGB-D frame

Run this with the ROS 2 Python environment:

```bash
cd ~/SensorAgent
python3 scripts/linux/capture_gazebo_rgbd_frame.py --out-dir logs/vision/latest
```

It writes:

```text
logs/vision/latest/rgb.npy
logs/vision/latest/rgb.ppm
logs/vision/latest/depth.npy
logs/vision/latest/camera_info.json
logs/vision/latest/manifest.json
```

## 4. Run the vision ActionList

Plan-only / fake robot backend:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query roller \
  --target bin_cell_3 \
  --no-capture
```

Capture and execute against Gazebo:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query roller \
  --target bin_cell_3 \
  --execute
```

## 5. Disambiguate two identical rollers

`worlds/industrial_pgs.sdf` spawns two rollers so the spatial resolver has a
real multi-candidate scene:

| Model | World pose (x, y) | base_link (x, y) | In the camera image |
| --- | --- | --- | --- |
| `roller_01` | (0.24, 0.23) | (0.24, 0.23) | left |
| `roller_02` | (0.24, -0.12) | (0.24, -0.12) | right |

The rig's optical +X maps to base -Y, so the larger-Y roller (`roller_01`)
appears on the image left. Pick one explicitly:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query roller \
  --spatial-relation left \
  --target bin_cell_3 \
  --execute
```

`--spatial-relation right` selects `roller_02` instead. Without the flag the
detector falls back to top-1 confidence, which is not deterministic across two
identical parts — so always pass a relation in this scene.

`roller_02` sits 0.030 m in front of the bin's near wall (bin footprint starts
at x=0.290, the roller ends at x=0.260). That clears the world geometry, but it
is tight for the 2F-85 fingertips — if a right-roller pick trips a collision
check, move `roller_02` to a smaller x rather than widening the gripper stroke.

Relations `left/right/front/back/largest/smallest` need no depth;
`nearest/farthest` back-project through `scene.workspace.table_z`. See
[vision_open_vocab_cn.md](vision_open_vocab_cn.md) section 7 for the full
resolver semantics and the `OBJECT_AMBIGUOUS` cases.

## Notes

- `python3 scripts/linux/capture_gazebo_rgbd_frame.py` uses ROS 2 Python because
  it imports `rclpy`.
- `.venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py` uses
  the Agent Python environment.
- `vision.open_vocab_detect` uses YOLOE/Ultralytics when the model is present.
  For current red-object Gazebo debugging, it also has a red-component fallback.
- 3D projection uses bbox-center depth median and either captured TF or the
  fixed Gazebo `T_base_camera` from `configs/robot_sim.yaml`.
