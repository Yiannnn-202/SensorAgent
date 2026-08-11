# 8 月 5 日讨论后视觉任务闭环

更新时间：2026-08-09

我已经按 8 月 5 日项目讨论，把视觉侧当前能独立推进的任务完成到可执行、可复核的状态。下面区分我已经完成的工作、收到场景数据后立即执行的工作，以及需要团队其他模块提供的输入。

## 我已经完成

| 讨论任务 | 当前结果 | 仓库证据 |
| --- | --- | --- |
| 设计评估指标框架 | 已补 AP50、AP75、query 级 mAP50:95，并统一 precision、recall、F1、box/mask IoU、中心误差、P50/P95 延迟和错误统计 | `src/sensoragent/evaluation/vision.py`、`scripts/vision_eval.py` |
| 建立数据审计和场景隔离规则 | 已提供 JSONL 审计脚本，可检查类别、框、来源、重复数据、scene leakage，并生成 `all/train/val/test.jsonl` | `scripts/vision_dataset_audit.py` |
| 验证审计工具边界 | 已修正 3-5 个场景时可能缺少 test 的切分边界，并覆盖确定性切分、泄漏、重复图片、公开来源和坏输入 | `tests/unit/test_vision_dataset_audit.py` |
| 整理公开数据集与训练证据 | 已核对 Mechanical Parts Dataset 2022 的 2024 张图片、9497 个框、四个宽类别、许可证和中间 checkpoint 边界 | `docs/guides/vision/competition-evaluation-framework-cn.md` |
| 配合视频文案包装 | 已整理单页内容，并生成可编辑原生 PPTX；真实指标、能力边界和 35 秒讲解词分别放在页面与演讲者备注 | `docs/team/vision_video_slide_cn.md`、本地 PPTX 交付物 |
| 验证现有训练入口 | `red_block_v2` 训练预检通过，48 张 train + 4 张 val、20 个场景，无场景泄漏 | 本地 `--dry-run` 结果 |
| 面向比赛桌面的模块创新 | 已实现可选 `scene_aware` 候选重排：工作区 ROI、禁抓区、边界裁切、尺寸/长宽比先验、候选重叠和歧义停机；baseline 默认行为不变 | `src/sensoragent/tools/vision/open_vocab.py`、`configs/vision_scene_aware.example.yaml`、`tests/unit/test_vision_open_vocab.py` |
| 创新模块评估接口 | 已在评估摘要增加 `scene_rejection_rate`、`ambiguity_rate`、`policy_latency_ms`，支持同一 test 的 baseline/scene-aware 对照 | `src/sensoragent/evaluation/vision.py`、`scripts/vision_eval.py`、`tests/unit/test_vision_evaluation.py` |

当前评估代码的 AP/mAP 是适配现有 Tool 的 query 级单目标协议。它不会冒充 COCO 多实例 mAP；最终多物体场景需要保存每个 query 的全部候选框后再补标准 COCO 评测。

新增的桌面场景创新是二维候选选择和风险输出，不是 RGB-D 定位或机械臂抓取规划。示例 profile 的 424x240 相机尺寸和 ROI 需要在最终比赛场景冻结后重新测量；当前没有把它们当成最终比赛指标。

## 收到场景数据后我立即执行

1. 和队长确认最终类别及英文 prompt 顺序。
2. 审计图片、scene ID、类别、框、mask、来源和重复内容。
3. 按完整场景生成并人工复核 train/val/test，冻结 test。
4. 用官方 Grounding DINO 和公开预热中间 checkpoint 分别初始化，在同一份比赛 test 上做对照。
5. 只在 val 选择 checkpoint、box threshold 和 text threshold。
6. 在固定 test 输出 precision、recall、AP/mAP、box/mask IoU、中心误差、P50/P95 延迟、失败样本和 overlay。
7. 交付完整 checkpoint、配置、manifest/checkpoint 哈希、用途说明和限制说明。
8. 在同一固定 test 上分别运行 baseline 和 scene-aware，比较精度/召回/AP、IoU、总耗时，以及场景拒绝率、歧义率和策略额外延迟。

没有新数据时，我不会重复增加 `red-block` epoch，也不会提前添加未确认的 `wrench` 或 `screwdriver` 类别。

## 当前等待团队输入

| 输入 | 负责人边界 | 缺失时不能完成的结果 |
| --- | --- | --- |
| 最终桌面场景和展示任务 | 场景/项目负责人 | 无法确定数据覆盖和展示专用权重用途 |
| 最终类别和英文 prompt 顺序 | 队长/视觉共同确认 | 无法冻结多类别训练配置 |
| 多类别 RGB、scene ID、框和可选 mask | 仿真/数据负责人 | 无法训练或评测正式比赛视觉权重 |
| 同步 depth、camera_info、frame、TF、时间戳和单位 | ROS/集成人员 | 无法证明 RGB-D 三维坐标 |
| Gazebo/真实机械臂批量验收 | 集成人员 | 无法报告抓取成功率或实机结果 |

因此当前准确状态是：视觉评估、数据交付/审计框架、审计工具专项测试和视频单页 PPTX 已完成；单类别训练链路已验证，正式多类别权重等待场景数据。不能把 7 月的全流程演示或其他模块的抓取结果改写成视觉模型已经完成实机抓取验收。
