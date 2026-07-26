# Gazebo Vision Pipeline VM Setup

Use this when `pip install -r requirements-vision.txt` fails with:

```text
OSError: [Errno 28] No space left on device
```

The fix is to avoid installing the large CUDA/GPU PyTorch wheels on the Ubuntu
VM. Install CPU-only PyTorch first, then install Ultralytics.

## 1. Clean safe caches and install vision dependencies

Copy and paste this whole block:

```bash
cd ~/SensorAgent

# Clean safe caches
.venv312/bin/python -m pip cache purge || true
rm -rf ~/.cache/pip
sudo apt clean 2>/dev/null || true

# Remove partial CUDA/GPU packages from a failed install
.venv312/bin/python -m pip uninstall -y \
  torch torchvision torchaudio triton \
  nvidia-cublas-cu13 nvidia-cuda-cupti-cu13 nvidia-cuda-nvrtc-cu13 \
  nvidia-cuda-runtime-cu13 nvidia-cudnn-cu13 nvidia-cufft-cu13 \
  nvidia-cufile-cu13 nvidia-curand-cu13 nvidia-cusolver-cu13 \
  nvidia-cusparse-cu13 nvidia-cusparselt-cu13 nvidia-nccl-cu13 \
  nvidia-nvjitlink-cu13 nvidia-nvshmem-cu13 nvidia-nvtx-cu13 || true

# Install CPU-only PyTorch first, so pip does not pull CUDA wheels
.venv312/bin/python -m pip install --no-cache-dir \
  --index-url https://download.pytorch.org/whl/cpu \
  torch torchvision

# Install YOLO/Ultralytics without forcing a CUDA torch reinstall
.venv312/bin/python -m pip install --no-cache-dir ultralytics

# Check model weight location
mkdir -p models/vision
if [ ! -f models/vision/yoloe.pt ]; then
  echo "MISSING: put your YOLOE weight at: ~/SensorAgent/models/vision/yoloe.pt"
  echo "After copying it there, rerun the pipeline command below."
fi

# Verify packages
.venv312/bin/python - <<'PY'
import torch
import ultralytics
print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())
print("ultralytics: ok")
PY
```

## 2. Put the YOLOE model in the expected location

The pipeline expects:

```text
~/SensorAgent/models/vision/yoloe.pt
```

If your model has a different filename, either rename it to `yoloe.pt` or update:

```text
configs/robot_sim.yaml
```

## 3. Start Gazebo and the robot bridge

In terminal 1:

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

## 4. Run the Gazebo RGB-D vision pipeline

In terminal 2:

```bash
cd ~/SensorAgent
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query roller \
  --target bin_cell_3 \
  --execute
```

For the red roller, use a more descriptive open-vocabulary query:

```bash
cd ~/SensorAgent
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query "red roller" \
  --target bin_cell_3 \
  --execute
```

If you only want to test detection and planning without moving the robot, omit
`--execute`:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query "red roller" \
  --target bin_cell_3
```

If frame capture cannot find ROS Python, set it explicitly:

```bash
export SENSORAGENT_ROS_PYTHON="$HOME/snap/copilot-cli/common/micromamba/envs/sensoragent-ros-humble/bin/python"

PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query roller \
  --target bin_cell_3 \
  --execute
```

This runs:

```text
Gazebo RGB-D camera
→ capture RGB/depth/camera_info
→ vision.open_vocab_detect
→ YOLOE/Ultralytics backend
→ 3D pose estimate
→ robot.plan_top_down_pick
→ pick/place
→ verify_grasp / verify_place
```

## 5. Check camera topics manually

If capture fails, confirm the camera topics exist:

```bash
ros2 topic list | grep industrial_camera
ros2 topic echo /industrial_camera/camera_info --once
ros2 topic hz /industrial_camera/image
```

## 6. Check the camera transform

The Gazebo camera pose is published as a static TF from `world` to the camera
frame used in `/industrial_camera/camera_info`:

```text
sensoragent_rgbd_rig/rig/depth_camera
```

After changing launch/config files, restart the sim:

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

Then check the transform:

```bash
source "$HOME/snap/copilot-cli/common/micromamba/envs/sensoragent-ros-humble/setup.bash"
source ~/SensorAgent/ros2_ws/install/setup.bash

ros2 run tf2_ros tf2_echo base_link sensoragent_rgbd_rig/rig/depth_camera
```

Expected translation is approximately:

```text
x: 0.34
y: 0.00
z: 0.88
```

The runner captures this matrix into:

```text
logs/vision/latest/manifest.json
```

under:

```json
"T_base_camera": [...]
```

If TF is unavailable, the runner falls back to the fixed matrix in:

```text
configs/robot_sim.yaml
```

## 7. Understanding `OBJECT_NOT_FOUND`

`OBJECT_NOT_FOUND` means `vision.open_vocab_detect` did not return any bounding
box for the text prompt in `--object-query`. For example, if you pass:

```bash
--object-query roller
```

the detector searches for exactly that text concept. For the red roller, try:

```bash
--object-query "red roller"
--object-query "red cylinder"
--object-query "red cylindrical object"
```

The runner prints the failed `detect_object` step, including the detector output:

```json
{
  "step": "detect_object",
  "success": false,
  "output": {
    "found": false,
    "label": "red roller",
    "confidence": 0.0
  },
  "error": "OBJECT_NOT_FOUND"
}
```

## 8. If the roller slips out during transfer

The roller and gripper finger collision surfaces are tuned for higher Gazebo
friction:

```text
ros2_ws/src/sensoragent_rm65_b_bringup/models/sensoragent_part_roller/model.sdf
ros2_ws/src/robotiq_description/urdf/robotiq_2f_85_macro.urdf.xacro
```

After changing either file, rebuild and restart the sim:

```bash
cd ~/SensorAgent/ros2_ws
source "$HOME/snap/copilot-cli/common/micromamba/envs/sensoragent-ros-humble/setup.bash"

colcon build --symlink-install \
  --packages-select robotiq_description sensoragent_rm65_b_bringup

source install/setup.bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

Then rerun the pipeline:

```bash
cd ~/SensorAgent
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query "red cylinder" \
  --target bin_cell_3 \
  --execute
```
