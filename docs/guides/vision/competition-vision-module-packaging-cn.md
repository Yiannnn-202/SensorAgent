# XH-202607 视觉模块技术报告与包装稿

更新时间：2026-08-11

## 1. 项目定位

我负责本项目的视觉感知部分，目标是让交互型智能体在工业桌面场景中根据自然语言目标完成物体识别、位置输出和后续抓取任务。项目对应榜单题目 `XH-202607：工业环境下物体感知识别与指令交互型智能体研发`。

比赛要求系统覆盖“环境物体感知识别 - 自然语言指令理解 - 作业任务序列分解”全流程，并重点考察感知精度与效率、工业场景微调、仿真和真实环境扩展、技术报告与演示效果。我的视觉模块通过稳定的结构化 JSON 接口向任务规划和执行模块提供结果，不把二维检测结果冒充成未经标定的机器人三维坐标。

## 2. 对照比赛评分标准

| 比赛评分项 | 视觉侧交付内容 | 当前证据 | 正式提交前仍需补齐 |
| --- | --- | --- | --- |
| 方案创新性与完整性（35 分中的视觉/智能体创新部分） | 在 `Grounding DINO -> SAM 2` 前加入面向固定桌面工位的 `scene_aware` 候选重排；把工作区、禁抓区、边界、尺寸和候选重复风险显式加入感知决策 | 代码、Tool 合同、场景配置、87 项视觉专项测试 | 最终工位 profile、指定顺序任务和完整抓取视频 |
| 技术实现质量：精度与效率（10 分） | 统一 precision、recall、F1、AP50、AP75、query 级 mAP50:95、box/mask IoU、中心误差和 P50/P95 延迟统计 | `red_block_v0` 单类别流程 test 证据；评估 CLI 已支持固定 test | 多类别比赛 test 的正式指标和同一 test 的 baseline/scene-aware 对照 |
| 技术实现质量：工业场景微调（15 分） | 按完整场景划分数据；阈值和 checkpoint 只在 val 选择；提供官方初始化与公开机械零件预热初始化两条对照路线 | 数据审计脚本、场景级 split 规则、训练预检和公开数据许可证记录 | 最终类别、英文 prompt、场景数据、专属权重和改进前后数字 |
| 系统集成与工程可用性（20 分） | `vision.open_vocab_detect` 和 `vision.grounded_sam2` 输出稳定 JSON；候选拒识和歧义状态可以被任务规划读取 | Tool schema、bootstrap 配置、局部测试和现有仿真链路 | depth、camera_info、TF、Gazebo 批量验收和真实机械臂验证 |
| 文档与展示效果（10 分） | 单页 PPT、演讲者备注、技术说明、评估规范和交付清单 | 本地 `视觉模块_桌面场景创新_单页展示_20260811.pptx`，文书已入 PR | 录入最终场景截图、正式指标和失败 overlay |

## 3. 面向比赛桌面的视觉创新

### 3.1 处理的问题

复杂桌面中，同一个文本 query 可能得到多个候选框。只取 detector confidence 最高的框，可能选到桌面外背景、禁抓区域、被边界裁切的物体或重复候选。对于比赛展示，我更关注固定工位中的稳定选择、失败可解释和风险可控。

### 3.2 处理流程

```text
RGB 图像 + 英文目标 query
          |
          v
Grounding DINO 输出全部候选框
          |
          v
scene_aware 场景约束评分
  工作区 ROI / 禁抓区 / 边界质量
  目标宽高与长宽比 / 候选重复重叠
          |
          v
胜者 / OBJECT_NOT_FOUND / OBJECT_AMBIGUOUS
          |
          v
SAM 2 掩码细化 -> bbox_2d、mask_polygons、center_px、timing_ms
```

候选分数使用可解释的乘积形式：

```text
scene_score =
  detection_confidence
  * roi_consistency
  * size_prior
  * boundary_quality
  * non_overlap_quality
```

当候选不满足工作区、禁抓区、边界或最低场景分数条件时，输出 `rejection_reason`。当最优候选和次优候选的分数差小于 `ambiguity_margin` 时，返回 `OBJECT_AMBIGUOUS`，不把不确定框直接交给机器人动作。没有 `depth`、`camera_info` 和 TF 时，该模块只负责二维感知和风险输出，不能报告机器人 base 坐标或抓取成功率。

## 4. 当前已经验证的证据

### 4.1 单类别链路证据

`red_block_v0` 用于验证 Grounding DINO 微调、checkpoint 重载、Grounded SAM 2 和固定 test 评估链路，不能代替最终多类别比赛证据。当前记录为：

| 指标 | 当前记录 | 证据边界 |
| --- | ---: | --- |
| precision | 0.750 | 4 张固定 test 图、单类别 |
| recall | 1.000 | 4 张固定 test 图、单类别 |
| mean box IoU | 0.912 | 仅对有效框匹配统计 |
| mean mask IoU | 0.845 | SAM 2 掩码细化结果 |
| center error | 0.740 px | 图像像素坐标 |
| warm P50/P95 | 536/544 ms | 不含首个 warmup |

### 4.2 工程验证证据

- 视觉专项测试共 87 项通过，覆盖候选策略、SAM 2、评估统计、数据审计、训练入口、CLI、COCO 转换和合同校验。
- `scene_aware` 默认关闭，baseline 原有行为不变。
- 评估摘要已经增加 `scene_rejection_rate`、`ambiguity_rate` 和 `policy_latency_ms`。
- GitHub PR #30 已上传代码、配置、合同、测试和正式项目文档；数据集、权重、runs、缓存、虚拟环境和本地 PPTX 不进入 Git。

## 5. 正式比赛数据到位后的实验设计

### 5.1 数据规则

我会先核对最终类别和英文 prompt 顺序，再检查图片、`scene_id`、框、mask、来源和重复内容。数据按完整场景划分 train/val/test，同一场景的近重复帧不能跨 split。空场景必须作为人工确认的负样本，不能把未标注目标当背景。

### 5.2 对照路线

在相同固定 test 上保留以下两条训练初始化对照：

1. 官方 Grounding DINO 初始化 -> 比赛数据；
2. 官方 Grounding DINO 初始化 -> Mechanical Parts Dataset 2022 公开预热 -> 比赛数据。

每条路线都在 val 选择 checkpoint、box threshold、text threshold 和场景 profile 参数，冻结后只在同一份 test 上报告结果。

### 5.3 必报指标

| 维度 | 指标 |
| --- | --- |
| 感知精度 | precision、recall、F1、AP50、AP75、query 级 mAP50:95 |
| 定位/分割 | mean box IoU、mean mask IoU、中心误差 |
| 效率 | cold first、warm mean、warm P50、warm P95、scene policy mean/P50/P95 |
| 场景风险 | scene rejection rate、ambiguity rate、各拒绝原因计数 |
| 集成结果 | 有效 JSON 率、任务规划接收率、抓取成功率（需另有 depth/TF/机械臂证据） |

如果 scene-aware 提高了风险拒识但降低了 recall，我会保留失败样本和 overlay，在 val 调整 profile 后重新对照，不能只挑选表现更好的数字。

## 6. 可用于技术报告和视频的表述

### 正式技术表述

> 针对工业桌面中多目标、遮挡、禁抓区域和候选重复的问题，系统在开放词汇检测后增加了场景约束候选重排模块。模块将工位工作区、禁抓区、目标尺寸和候选重叠先验转化为可解释的联合评分，并在候选不确定时输出歧义状态，从而降低错误目标进入后续抓取规划的风险。该模块不改变 Grounding DINO 和 SAM 2 的基础接口，能够通过场景 profile 迁移到不同固定工位。

### 当前阶段的边界表述

> 目前已经完成场景化策略的代码实现、合同、配置、评估接口和专项测试；`red_block_v0` 数字只用于证明单类别流程。最终多类别比赛权重、正式场景提升、RGB-D 坐标和真实机械臂抓取结果，待最终场景数据和集成验收后报告。

## 7. 视觉提交材料

当前我负责交付以下内容：

1. 视觉 Tool 源代码和配置；
2. Tool JSON schema 和错误状态说明；
3. 评估脚本、数据审计脚本和专项测试；
4. 训练/评测规范、场景化策略说明和任务闭环文档；
5. 视频单页文案与本地可编辑 PPTX；
6. 正式场景到位后补充 checkpoint 目录、manifest/checkpoint SHA-256、固定 test 结果和失败 overlay。

权重、数据集、runs、缓存、虚拟环境和本地 PPTX 作为独立交付物保存，不上传到 GitHub。
