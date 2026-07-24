# 开放语义视觉 Tool 接入说明

本文说明当前预留的开放语义检测接口：

```text
vision.open_vocab_detect
```

它暂时不接入工业 ActionList，目的是先稳定通信格式和模型目录。后续可把
YOLOE、YOLOv11-seg 或其他开放词汇检测器接到这个 Tool 后面。

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

第一版至少需要 `query`。`image_path` 和 `depth_path` 是为后续真实视觉检测与
深度融合预留的通信字段。

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

## 4. 当前占位行为

如果模型权重还没有放入 `models/vision/yoloe.pt`，Tool 会返回结构化失败：

```text
VISION_MODEL_NOT_READY
```

这样可以先测试工具注册、配置加载、输入输出契约和上层通信，不会误以为模型已经可用。

## 5. 后续实现位置

后续真正接 YOLOE/YOLOv11-seg 时，优先修改：

```text
src/sensoragent/tools/vision/open_vocab.py
```

建议只替换 `PlaceholderOpenVocabularyBackend`，保持 `VisionOpenVocabularyDetectTool`
的输入输出不变。
