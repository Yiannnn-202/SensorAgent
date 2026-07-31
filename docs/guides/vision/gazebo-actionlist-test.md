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

Current scene layout:

- one stable `block` only, spawned near base_link `[-0.24, -0.18, 0.140]`
  after the 180-degree robot mount yaw;
- a flat 2x2 target grid instead of a walled bin; colored areas are visual-only,
  while white boundaries are low-profile physical strips;
- target names are `target_area_1` to `target_area_4`;
- the workbench is `0.5 x 0.75 m`, has a high-friction collision surface, and
  the camera is centered over it.

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
  --object-query block \
  --target target_area_3 \
  --no-capture
```

Capture and execute against Gazebo:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query block \
  --target target_area_3 \
  --execute
```

If a descriptive prompt like `red block` is too narrow for YOLOE, the runner
now retries practical aliases such as `block`, `cube`, `box`, and
`industrial part`. The selected detection output includes
`query_attempts` so you can see which prompt/threshold succeeded.

The runner passes an empty object (`{}`) when no spatial selector is requested.
Do not pass JSON `null` as `spatial_constraint`; the tool schema expects an
object.

## 5. Optional spatial selection

The current default world has only one block, so spatial selection is normally
unnecessary. You can still test the spatial resolver if you add multiple
objects or use a custom world:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query block \
  --spatial-relation left \
  --target target_area_3 \
  --execute
```

Relations `left/right/front/back/largest/smallest` need no depth;
`nearest/farthest` back-project through `scene.workspace.table_z`. See
[open-vocabulary.md](open-vocabulary.md) section 7 for the full
resolver semantics and the `OBJECT_AMBIGUOUS` cases.

## Notes

- `python3 scripts/linux/capture_gazebo_rgbd_frame.py` uses ROS 2 Python because
  it imports `rclpy`.
- `.venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py` uses
  the Agent Python environment.
- `vision.open_vocab_detect` uses YOLOE/Ultralytics when the model is present.
  For current red-object Gazebo debugging, it also has a red-component fallback.
- 3D projection uses bbox/mask-center depth median plus camera intrinsics, then
  transforms through captured TF (`T_base_camera` and `T_world_camera`). If TF is
  unavailable, the runner falls back to fixed Gazebo `T_base_camera` from
  `configs/robot_sim.yaml` for base-frame localization.
