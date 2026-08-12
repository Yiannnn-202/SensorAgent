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
  --dataset-dir data/vision/sorting_clear_v1 \
  --count 100 \
  --seed 20260812 \
  --occlusion-rate 0 \
  --position-jitter 0.0075 \
  --settle-seconds 1
```

The collector matches the current sorting world: three rollers, three hex nuts,
and three short bolts. It randomly assigns all nine instances to the current
3x3 safe grid and applies up to 7.5 mm of XY jitter. The default has no overlap,
keeps rollers horizontal, keeps nuts upright, and keeps short bolts head-down
with their narrow shafts pointing up.

Images for annotation are in:

```text
data/vision/sorting_clear_v1/roboflow_images/
```

The `raw/` directory preserves RGB arrays, depth, camera information, and TF.
`randomized_manifest.jsonl` records the Gazebo entity, position, pitch, and yaw
for each image, and is only for label checking or later 3D evaluation.

## Optional Occlusion Set

Collect a small separate difficult set after clear images are labeled:

```bash
python3 scripts/linux/collect_randomized_sorting_dataset.py \
  --dataset-dir data/vision/sorting_occlusion_v1 \
  --count 30 \
  --seed 20260813 \
  --occlusion-rate 0.15 \
  --settle-seconds 1
```

Do not use heavily overlapped images as the majority of the first training set.
For any fully hidden object, do not create a mask or box. Label only visible
object regions.

## Classes

Use these exact English class names. Each image contains three instances of
each class:

```text
roller
hex_nut
short_bolt
```

Use instance masks when the annotation tool supports them; otherwise use tight
bounding boxes. Export the completed labels in YOLO segmentation or COCO format.
