# 桌面场景约束候选重排

更新时间：2026-08-11

## 这项创新解决什么问题

在复杂桌面上，同一个文本 query 可能得到多个候选框。单纯按 detector confidence 取最高框，容易把桌面外的背景、禁抓区域、被裁切的边缘目标或重复框交给后面的抓取流程。比赛场景的关键不是追求通用数据集上的最高分，而是让固定工位中的候选选择稳定、可解释、能在风险高时主动停下来。

我在现有 `Grounding DINO -> SAM 2 -> JSON` 之前加入了一个可选的 `scene_aware` 候选策略：

```text
Grounding DINO 全部候选框
        |
        v
桌面场景约束评分与风险判断
  - 工作区 ROI 覆盖率
  - 禁抓区域重叠
  - 图像边界裁切程度
  - 目标宽高和长宽比先验
  - 候选框之间的重复重叠
        |
        v
排序后的一个候选 / 明确拒绝 / 歧义停机
        |
        v
SAM 2 掩码细化 -> 结构化视觉 JSON
```

该模块只使用 RGB 图像中的二维几何和检测置信度。没有 `depth`、`camera_info`、TF 时，它不能给出机器人 base 坐标，也不能证明机械臂抓取成功。

## 接口和评分

通过 `candidate_policy: scene_aware` 开启；不传或传 `baseline` 时保持原来“最高 detector confidence”行为。策略可在 Tool 构造时配置，也可以在一次调用中覆盖。

```json
{
  "query": "gear",
  "candidate_policy": "scene_aware",
  "scene_profile": {
    "name": "industrial_tabletop_v1",
    "image_size": [424, 240],
    "workspace_roi": [12, 12, 412, 228],
    "forbidden_rois": [[0, 0, 424, 18]],
    "min_roi_coverage": 0.65,
    "min_boundary_coverage": 0.90,
    "max_forbidden_overlap": 0.10,
    "max_candidate_iou": 0.75,
    "min_scene_score": 0.08,
    "ambiguity_margin": 0.04
  }
}
```

候选分数采用可解释的乘积形式：

```text
scene_score =
  detection_confidence
  * roi_consistency
  * size_prior
  * boundary_quality
  * non_overlap_quality
```

禁抓区、工作区覆盖不足、边界裁切、重复重叠和低于 `min_scene_score` 的候选会带有 `rejection_reason`。结果还会返回 `scene_features`、`scene_profile`、`scene_score` 和 `ambiguity`，方便视频展示、失败分析和后续任务策略读取。

当最优候选与次优候选的 `scene_score` 差值不超过 `ambiguity_margin` 时，Tool 返回 `OBJECT_AMBIGUOUS`，不把不确定框交给机器人动作。候选策略不改变 SAM 2 的掩码契约；它只改变进入 SAM 2 的候选选择。

## 配置和运行

仓库提供了一个可修改的起始配置：

```text
configs/vision_scene_aware.example.yaml
```

其中的 424x240 和 ROI 是 Gazebo 相机的起始 profile，不是最终比赛工位的测量结论。场景冻结后应重新测量桌面可见区域、料箱/禁抓区域和常见目标尺寸，再把 profile 与对应权重版本一起同步给队长。单独的 profile 文件是 `configs/vision_scene_profile.example.yaml`；完整 Tool 配置示例是 `configs/vision_scene_aware.example.yaml`。

也可以在评估时覆盖策略和 profile：

```powershell
python scripts/vision_eval.py run `
  --manifest data/vision/competition_test.jsonl `
  --config configs/vision_grounding_dino.yaml `
  --tool vision.grounded_sam2 `
  --candidate-policy scene_aware `
  --scene-profile configs/vision_scene_profile.example.yaml `
  --output-dir runs/vision/eval_scene_aware
```

评估摘要在原有 precision、recall、AP、IoU 和延迟之外增加：

| 指标 | 统计规则 |
| --- | --- |
| `scene_rejection_rate` | 被场景规则拒绝的候选数 / 返回候选总数；不是模型 recall |
| `ambiguity_rate` | 返回 `OBJECT_AMBIGUOUS` 的 scene-aware 样本数 / scene-aware 样本数 |
| `policy_latency_ms` | 场景评分本身的 mean/P50/P95；与模型推理延迟分开 |

应在同一固定 test 上跑两份结果：`baseline` 和 `scene_aware`。先报告精度、召回、AP/mAP、box/mask IoU、中心误差和总耗时，再报告场景拒绝率、歧义率和额外延迟。若场景策略提高了安全拒绝但降低了 recall，应保留失败样本和 overlay，调整 ROI/尺寸先验后重新在 val 选择参数；不能只挑好看的数字。

## 当前证据和边界

- 代码、合同和专项测试已经完成，覆盖 ROI 重排、禁抓区过滤、歧义停机和 baseline 兼容。
- 现有 `red_block_v0` 的 `0.750` precision、`1.000` recall、`0.912` box IoU、`0.845` mask IoU 和 `536/544 ms` 延迟仍然只是 4 张固定 test 图上的单类别流程证据，没有经过本策略的正式比赛对照。
- 最终多类别类别表、场景数据、固定 test、目标尺寸先验和真实工位 ROI 尚未由场景负责人冻结，因此不能把示例 profile 写成最终比赛配置。
- 该模块没有宣称 RGB-D 三维坐标、机械臂抓取成功率、工业泛化或实机比赛验收。
