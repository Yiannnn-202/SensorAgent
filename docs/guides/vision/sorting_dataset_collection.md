# Industrial Sorting Dataset Collection

Use this guide to collect clear Gazebo RGB-D images for annotation and model training.

## Files To Share

Commit these two files so the collector is available to the team:

```text
scripts/linux/collect_randomized_sorting_dataset.py
scripts/linux/capture_gazebo_rgbd_frame.py
```

Do not commit the generated `data/vision/` images, depth arrays, or model weights.

## Start Gazebo

```bash
bash scripts/linux/run_rm65_b_sim.sh world_file:=industrial_sorting_metal_pgs.sdf
```

Wait until the camera image and robot bridge are ready.

## Collect Clear Images

Run this in a second terminal:

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash

python3 scripts/linux/collect_randomized_sorting_dataset.py \
  --dataset-dir data/vision/sorting_variable_count_v1 \
  --count 100 \
  --seed 20260812 \
  --min-per-class 0 \
  --max-per-class 3 \
  --position-jitter 0.0075 \
  --settle-seconds 1
```

The collector matches the current sorting world: three rollers, three hex nuts,
and three short bolts. For every image it independently samples 0-3 visible
instances of each class. Unselected entities are moved to parking positions
outside the camera view. Selected instances are randomly assigned to the current
3x3 safe grid with up to 7.5 mm of XY jitter. The default prevents a completely
empty image but allows any individual class to have zero instances. Add
`--allow-empty-scene` if fully empty negative images are also required.

Images for annotation are in:

```text
data/vision/sorting_variable_count_v1/roboflow_images/
```

The `raw/` directory preserves RGB arrays, depth, camera information, and TF.
`randomized_manifest.jsonl` records `class_counts`, `empty_classes`, and every
Gazebo entity's active/parked state, position, roll, pitch, and yaw. It is for
label checking and later 3D evaluation; it does not replace image annotations.

## Classes

Use these exact English class names. Each image contains a random 0-3 instances
of each class:

```text
roller
hex_nut
short_bolt
```

Use instance masks when the annotation tool supports them; otherwise use tight
bounding boxes. Export the completed labels in YOLO segmentation or COCO format.
