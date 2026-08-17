# YOLOE 与 Grounding DINO 同集对照

更新时间：2026-08-13

## 数据与权重

本次对照使用同一份 `red_block_v2` 固定数据：

- 数据来源：Roboflow `red block v2`，CC BY 4.0；
- 数据性质：公开的仿真桌面数据，不是 `room_110` 或 `training_building` 的实拍数据；
- 类别：`red block`；
- 划分：48 张 train、4 张 validation、4 张 test；共 24 个独立 `scene_id`，包含负样本；
- test：4 张，其中 3 张有目标、1 张为空场景；
- test manifest SHA-256：`8F8F9EDF9A30085903051E242752B339C3456CD1D06FDB31268103193DE3CE27`；
- train manifest SHA-256：`260C5C58AE8D1B87F957691CB876EAFF12C2CBF1D9A47B5F89E36BC48D804523`；
- validation manifest SHA-256：`ADC8947B75A5F55C8D917924ECD55D6889DACF95B58116FA47C636C31F2E16AD`。

两路模型如下：

| 路线 | 模型和权重 | 权重 SHA-256 |
| --- | --- | --- |
| Grounding DINO + SAM 2 | `grounding_dino_red_block_v0/output/checkpoint-best` + `sam2_t.pt` | Grounding DINO `07FA5A27B23E91A4DEA2A6E3D12CE070C54513A4E25D386FC9023C7D4983AA84`；SAM 2 `94375F988270836169320BD901960C67B5770E8BEF3867D70102F01A8B5CA501` |
| YOLOE + SAM 2 | Ultralytics `yoloe-11s-seg.pt` + `sam2_t.pt` | YOLOE `8E439445C87338B79D9CE21DEC109F4621E26DF67E94D26EA1A98C1E64DCE3E3`；SAM 2 同上 |

YOLOE 使用的是 Ultralytics 官方通用权重，不是比赛专用或真实工位微调权重。Grounding DINO 使用本地已经完成的 `red_block_v0` 单类微调权重。

## 参数冻结

validation 只用于选择 YOLOE 的置信度和 NMS 参数，test 不参与调参。

在 validation 上测试的网格为：

- confidence/text threshold：`0.005`、`0.01`、`0.02`、`0.05`、`0.10`；
- YOLOE NMS IoU：`0.45`、`0.55`、`0.70`。

所有组合在 4 张 validation 图上得到相同的 `precision=0.75`、`recall=1.0`、`F1=0.857143`。为保持与冒烟记录和配置一致，冻结参数取 `confidence=0.005`、`text_threshold=0.005`、`NMS IoU=0.55`。

Grounding DINO 使用 validation 选择并冻结的 `box_threshold=0.05`、`text_threshold=0.05`。两路都使用：

- 同一 `manifest_test.jsonl`；
- 同一 `bbox IoU >= 0.5` 定位匹配规则；
- 同一 `query_level_single_best_box` 排序指标协议；
- 同一 SAM 2 权重和 mask 输出要求；
- `warmup_runs=0`，记录首帧和后续运行时间。

## 冻结 test 结果

| 指标 | Grounding DINO + SAM 2 | YOLOE + SAM 2 | 差值（Grounding DINO - YOLOE） |
| --- | ---: | ---: | ---: |
| test 样本数 | 4 | 4 | - |
| TP / FP / TN / FN | 3 / 1 / 0 / 0 | 3 / 1 / 0 / 0 | - |
| precision | 0.750000 | 0.750000 | 0 |
| recall | 1.000000 | 1.000000 | 0 |
| F1 | 0.857143 | 0.857143 | 0 |
| mean box IoU | 0.912312 | 0.909753 | +0.002559 |
| mean mask IoU | 0.844524 | 0.772599 | +0.071925 |
| mean center error | 0.739752 px | 0.753758 px | -0.014006 px |
| AP50 | 1.000000 | 1.000000 | 0 |
| AP75 | 1.000000 | 1.000000 | 0 |
| mAP50:95 | 0.889109 | 0.811221 | +0.077888 |
| mask 输出率 | 1.000000 | 1.000000 | 0 |
| 执行错误 | 0 | 0 | 0 |
| warm P50 | 618.743 ms | 654.167 ms | -35.424 ms |
| warm P95 | 9181.085 ms | 2815.794 ms | +6365.291 ms |

## 结果判断

在这份 4 张 test 的公开仿真数据上：

1. 两路的 precision、recall、F1 和 AP50/AP75 相同；
2. Grounding DINO 的平均框 IoU、平均 mask IoU 和 mAP50:95 略高；
3. YOLOE 的 warm P95 延迟低于 Grounding DINO，但样本数太少，且 Grounding DINO 的首轮/缓存状态会显著影响延迟，不能据此形成稳定的实时性结论；
4. 两路都在空场景上产生了 1 个 FP，说明这份 test 已经暴露出假阳性，但 4 张图不足以评估真实工位的拒识能力；
5. 当前结果只说明在这份固定仿真 test 上，Grounding DINO + SAM 2 的定位和分割数值略好于官方通用 YOLOE + SAM 2，不能外推到 110/工训楼，也不能代表比赛专用 YOLOE 权重的表现。

本次评测输出保留在本地 `runs/vision/` 中，没有把运行日志、overlay、数据和权重加入 Git。仓库只保留代码、配置、数据合同、测试和本报告。

## 110/工训楼正式对照的输入状态

当前仍缺少以下输入，因此尚未形成 110/工训楼实拍数据上的正式比较：

- 110 和工训楼的原始 RGB 图片及完整 `scene_id`；
- 每张图所有目标的类别和 bbox，最好同时提供 mask；
- 比赛专用 YOLOE 权重、类别 ID 顺序、Ultralytics 版本和输入尺寸；
- validation/test 的场景级冻结划分。

上述输入到位后，应沿用本报告的四路方案：Grounding DINO 框、Grounding DINO + SAM 2、YOLOE 框、YOLOE + SAM 2，并在同一场景级 test 上重新选择阈值、记录每类和总体指标、保留失败样例及哈希。
