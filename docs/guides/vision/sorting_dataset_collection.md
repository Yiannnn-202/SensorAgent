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
  --settle-seconds 1
```

The default is no overlap. It keeps all seven parts separated and preserves the
horizontal orientation of `roller` and `stepped_shaft`.

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

Use these exact English class names:

```text
block
roller
hollow_sleeve
stepped_shaft
hex_nut
short_bolt
flange_bushing
```

Use instance masks when the annotation tool supports them; otherwise use tight
bounding boxes. Export the completed labels in YOLO segmentation or COCO format.
