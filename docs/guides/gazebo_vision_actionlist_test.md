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
to use `vision.config_detect`. This guide uses a parallel workflow:

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

## Notes

- `python3 scripts/linux/capture_gazebo_rgbd_frame.py` uses ROS 2 Python because
  it imports `rclpy`.
- `.venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py` uses
  the Agent Python environment.
- `vision.open_vocab_detect` currently uses a simple bbox-center depth median
  and a fixed Gazebo `T_base_camera` from `configs/robot_sim.yaml`.
