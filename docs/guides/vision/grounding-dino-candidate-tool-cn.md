# Grounding DINO 多类别候选工具

`vision.grounding_dino_candidates` 是一个独立的图片处理工具。它接收一张 RGB 图片和多个英文类别 prompt，分别运行 Grounding DINO，再把候选框分成 `selected`、`suppressed` 和 `ambiguous` 三组。

## 输入

```json
{
  "image_path": "data/vision/example.jpg",
  "queries": ["hex nut", "roller", "short bolt"],
  "box_threshold": 0.15,
  "text_threshold": 0.001,
  "classwise_nms_iou": 0.50,
  "cross_class_iou": 0.50,
  "ambiguity_margin": 0.03
}
```

`image_path` 和 `queries` 是必需项。阈值可以按调用覆盖，正式 test 前应先在 valid 上固定。

## 处理顺序

1. 对每个 prompt 收集 Grounding DINO 候选框。
2. 对同一类别执行 class-wise NMS，默认 IoU 为 `0.50`。
3. 对不同类别且 IoU 不低于 `cross_class_iou` 的框进行比较。
4. 分数差大于 `ambiguity_margin` 时保留分数更高的框，另一框标记为 `suppressed`。
5. 分数差不超过 `ambiguity_margin` 时，两框标记为 `ambiguous`，不应直接交给机械臂动作。

Grounding DINO 是多个独立 prompt 推理，分数用于排序，不代表校准概率。若多个类别长期出现接近分数，应增加困难样本或做 valid 集上的类别校准，不能只依赖微小分数差。

## 输出

每个候选包含类别、排序分数、`bbox_2d`、中心点和处理状态。被抑制或不确定的候选还会记录原因、冲突候选索引、IoU 和分数差。工具同时返回 `timing_ms`，便于比较多 prompt 推理开销。

该工具当前没有注册到 agent bootstrap、ActionList 或机械臂流程。它用于独立验证候选策略，后续接入前需要在真实场景数据上确认类别、阈值和不确定处理策略。
