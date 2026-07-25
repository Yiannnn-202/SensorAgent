# 开放语义视觉 Tool 接入说明

本文说明当前开放语义检测接口：

```text
vision.open_vocab_detect
```

它已接入 `industrial.vision_pick_place_actionlist`，用于 Gazebo RGB-D
抓取放置实验。Tool 会在模型权重存在时加载 YOLOE/Ultralytics；模型或可选
依赖缺失时返回结构化失败，便于上层流程判断。

## 1. 模型权重位置

默认权重路径：

```text
models/vision/yoloe.pt
```

该目录已保留：

```text
models/vision/
```

你可以手动把模型权重放进去。若文件名不同，修改：

```yaml
integrations:
  vision:
    backend: yoloe
    model_path: models/vision/yoloe.pt
```

当前配置位置：

```text
configs/robot_sim.yaml
```

## 2. Tool 输入

```json
{
  "query": "roller",
  "image_path": "logs/vision/frame.png",
  "depth_path": "logs/vision/depth.npy"
}
```

`query` 必填。`image_path` 指向 RGB `.npy` 或常见图像文件；`depth_path`
当前支持 `.npy` 深度图。`camera_info_path` 或 `camera_info` 与
`T_base_camera` 可用于把 bbox 中心深度投影到 `base_link`。

## 3. Tool 输出

成功输出应保持如下结构：

```json
{
  "found": true,
  "label": "roller",
  "confidence": 0.88,
  "source": "yoloe",
  "object_id": "roller_001",
  "bbox_2d": [10.0, 20.0, 50.0, 80.0],
  "position_camera": [0.1, 0.2, 0.8],
  "position_base": [0.24, 0.23, 0.142],
  "pose_3d": [0.24, 0.23, 0.142, 0.0, 0.0, 0.0]
}
```

其中 `pose_3d` 用于后续：

```text
robot.plan_top_down_pick
→ robot.pick
```

## 4. 当前行为

如果模型权重还没有放入 `models/vision/yoloe.pt`，Tool 会返回结构化失败：

```text
VISION_MODEL_NOT_READY
```

如果缺少 `ultralytics` 等可选依赖，会返回：

```text
VISION_BACKEND_UNAVAILABLE
```

如果检测不到目标，会返回：

```text
OBJECT_NOT_FOUND
```

当查询词包含 `red` 且 RGB 输入是 `.npy` 时，Tool 还包含一个红色连通域兜底
路径，方便在当前 Gazebo 红色滚柱场景中验证 RGB-D 投影链路。

## 5. Gazebo ActionList 使用

完整 RGB-D 测试见：

```text
docs/guides/gazebo_vision_actionlist_test.md
docs/guides/gazebo_vision_vm_setup.md
```

常用命令：

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_vision_actionlist_sim.py \
  --object-query "red roller" \
  --target bin_cell_3 \
  --execute
```

## 6. 后续实现位置

继续扩展 YOLOE/YOLOv11-seg 或其他开放词汇检测器时，优先修改：

```text
src/sensoragent/tools/vision/open_vocab.py
```

建议保持 `VisionOpenVocabularyDetectTool` 的输入输出不变，只替换或扩展后端
适配层。
