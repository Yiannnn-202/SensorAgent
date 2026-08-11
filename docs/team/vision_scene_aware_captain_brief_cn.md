# 视觉场景化创新与队长汇报稿

更新时间：2026-08-11

## 先说结论

我没有记错队长在 8 月 5 日讨论中的要求。视觉侧不能只展示一个通用模型跑通，还要围绕比赛的复杂多物体桌面场景做定制化，形成可以写进参赛文书和展示视频的模块创新；同时要保留精度、效率和场景微调的量化证据。

我已经把这项要求落成一个可开关的 `scene_aware` 桌面场景候选策略，并接入现有的 `Grounding DINO -> SAM 2 -> JSON` 链路。

## 已完成的模块创新

```text
Grounding DINO 输出全部候选框
        |
        v
桌面场景约束评分
  - 工作区 ROI
  - 禁抓区域
  - 图像边界裁切
  - 目标宽度、高度、长宽比先验
  - 候选框重复重叠
        |
        v
胜者 / 明确拒绝 / OBJECT_AMBIGUOUS
        |
        v
SAM 2 掩码细化 -> 结构化视觉 JSON
```

这个模块的核心不是重新做一个泛化模型，而是把比赛工位的先验显式加入候选选择。相同 query 产生多个框时，不再只按 detector confidence 选最高框，而是联合判断候选是否位于工作区、是否碰到禁抓区、是否被图像边界裁切、尺寸是否符合该工位常见目标，以及是否与其他候选重复。

当最优候选和次优候选的场景分数过于接近时，Tool 返回 `OBJECT_AMBIGUOUS`，不把不确定的框交给后面的机器人动作。这一停机策略可以在文书中表述为“面向固定桌面工位的风险感知候选选择”，但不能表述为已经完成机械臂安全验收。

## 当前证据

| 项目 | 当前状态 |
| --- | --- |
| 代码 | 已接入 `vision.open_vocab_detect` 和 `vision.grounded_sam2`，baseline 默认行为保持不变 |
| 配置 | 已提供 `configs/vision_scene_profile.example.yaml` 和完整 Tool 配置示例 |
| 合同 | 已更新 open-vocabulary 和 Grounded SAM 2 的 JSON schema |
| 评估 | 已增加场景拒绝率、歧义率和策略额外延迟，并支持 baseline/scene-aware 同一 test 对照 |
| 测试 | 本地视觉专项测试 87 passed |
| 展示 | 已生成本地可编辑 PPTX：`视觉模块_桌面场景创新_单页展示_20260811.pptx` |
| GitHub | 分支 `feat/vision-aug-evaluation-handoff`，最新提交 `9360d56`，PR #30 已打开但尚未合并 |

现有 `red_block_v0` 的 precision、recall、box/mask IoU 和延迟数字仍然只是单类别流程验证，不能写成最终多类别比赛结果，也不能写成 scene-aware 已经取得正式 test 提升。

## 收到正式场景数据后的执行顺序

1. 和队长确认最终类别列表、英文 prompt 顺序、展示任务和抓取顺序。
2. 用完整 `scene_id` 审计图片、框、mask、来源和重复内容，按场景而不是按相邻帧切分 train/val/test。
3. 根据最终相机分辨率重新测量工作区 ROI、禁抓 ROI、目标尺寸和长宽比先验，替换示例 profile。
4. 只在 val 选择 checkpoint、box threshold、text threshold 和 scene-aware 参数，冻结 test。
5. 在同一份固定 test 上比较官方 Grounding DINO 初始化、公开机械零件预热初始化，以及 baseline 和 scene-aware 两种候选策略。
6. 输出 precision、recall、AP50、AP75、mAP50:95、box/mask IoU、中心误差、P50/P95 总延迟、场景拒绝率、歧义率和额外策略延迟。
7. 将胜者 JSON 接入任务规划后，再由集成人员单独验收 depth、camera_info、TF、Gazebo 和真实机械臂抓取；没有这些证据时不报告 RGB-D base 坐标或抓取成功率。

## 可直接向队长汇报

> 我已经按 8 月 5 日讨论，把视觉从“通用检测模型跑通”补成了一个针对比赛桌面场景的可解释候选策略。现在 Grounding DINO 会保留全部候选框，再根据工作区 ROI、禁抓区、边界裁切、目标尺寸和候选重叠做二次评分；候选不确定时主动返回 `OBJECT_AMBIGUOUS`，不会把风险框直接交给机器人。这个策略已经接入现有 Grounding DINO 加 SAM 2 链路，合同、配置、评估指标和专项测试都完成了，本地视觉专项 87 项全部通过，单页展示稿也已经生成，代码推送在 PR #30。现在还不能报最终比赛提升，因为最终多类别场景、固定 test、ROI 和尺寸先验还没冻结。场景数据到位后，我会在同一份 test 上做 baseline 和 scene-aware 对照，给出精度、召回、mAP、IoU、延迟、拒绝率和歧义率，再交给集成人员做 RGB-D 和机械臂验收。

## 当前不能对外宣称

- 最终多类别比赛权重已经完成。
- `scene_aware` 已经在正式比赛 test 上取得提升。
- 已完成 RGB-D 到机器人 base 坐标转换。
- 已完成机械臂抓取成功率或实机比赛验收。
- 已完成工业场景泛化或最终赛事指标。

这些结论必须等正式场景、固定 test、深度/标定/TF 和集成验收证据齐全后再写。
