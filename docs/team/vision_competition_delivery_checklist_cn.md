# XH-202607 视觉模块比赛交付清单

更新时间：2026-08-11

这份清单用于我和项目组对照比赛任务书推进视觉交付，按“已完成、收到输入后执行、需要联调验收”区分状态。项目目标是服务于 `XH-202607：工业环境下物体感知识别与指令交互型智能体研发`，不把阶段性验证结果写成最终比赛结果。

## 一、已经完成

| 工作项 | 交付结果 | 位置/证据 |
| --- | --- | --- |
| 视觉链路 | RGB + 英文 query -> Grounding DINO -> SAM 2 -> 结构化 JSON | `vision.grounded_sam2` |
| 场景化创新 | `scene_aware` 候选重排、风险拒识和歧义停机 | `src/sensoragent/tools/vision/open_vocab.py` |
| 评估框架 | AP50、AP75、query 级 mAP50:95、IoU、中心误差、延迟和错误统计 | `src/sensoragent/evaluation/vision.py` |
| 数据审计 | JSONL 合同检查、重复内容检查、scene-level split leakage 检查和确定性切分 | `scripts/vision_dataset_audit.py` |
| 训练边界 | val 选阈值和 checkpoint，固定 test 报告；公开数据只作预热 | `docs/guides/vision/competition-evaluation-framework-cn.md` |
| 展示包装 | 桌面场景创新单页 PPT、讲解词、来源和能力边界 | 本地 PPTX、`vision_video_slide_cn.md` |
| 专项测试 | 87 项视觉专项测试通过 | 本地 pytest 结果 |

## 二、收到场景负责人输入后执行

### 必须确认的输入

- 最终桌面场景和展示任务；
- 最终类别列表和英文 prompt 顺序；
- 多类别 RGB 图像、`scene_id`、类别、bbox，最好同时提供 mask 和 instance ID；
- 空场景、遮挡、多目标、近似颜色背景、不可抓干扰物、料箱和机械臂边缘等情况；
- 最终相机分辨率、工作区 ROI、禁抓 ROI 和常见目标尺寸。

### 执行顺序

1. 审计原始数据，不修改来源清单；
2. 按完整场景生成 train/val/test，并人工复核代表性；
3. 运行训练 dry-run，确认 optimizer update 大于 0；
4. 训练官方初始化和公开预热初始化两条路线；
5. 只在 val 选择阈值、checkpoint 和 scene-aware profile；
6. 冻结 test，分别运行 baseline 和 scene-aware；
7. 交付 summary、逐样本结果、失败 overlay、配置和 SHA-256。

## 三、视觉和比赛评分的对应关系

| 评分关注点 | 我能提供的视觉材料 | 还需要的外部证据 |
| --- | --- | --- |
| 创新性与完整性 | 场景约束候选选择、风险拒识、结构化 JSON | 完整感知-决策-执行视频 |
| mAP 和推理效率 | 固定 test 的 AP/mAP、IoU、P50/P95 | 正式多类别 test 结果 |
| 工业场景微调 | 专属 scene profile、训练配置、前后对照表 | 最终场景数据和专属 checkpoint |
| 工程可用性 | Tool 合同、错误状态、数据审计和复现实验命令 | depth、camera_info、TF 和机械臂联调 |
| 文档和展示 | 技术报告章节、单页 PPT、讲解词 | 最终运行截图、视频和失败恢复片段 |

## 四、当前不能写成完成的内容

- 不能把 `red_block_v0` 单类别 4 张 test 图写成最终多类别比赛 mAP；
- 不能把示例 424x240 ROI 写成最终工位测量结果；
- 不能把二维 `center_px` 写成机器人 base 坐标；
- 不能在没有 depth、camera_info、TF 和真实联调时写机械臂抓取成功率；
- 不能把公开 Mechanical Parts Dataset 预热 checkpoint 写成最终比赛权重；
- 不能把 PR #30 写成已经合并到 `main`。

## 五、最终提交包应包含

1. 完整源代码、配置和 Tool schema；
2. 训练/评测命令和依赖说明；
3. 类别、prompt 顺序、manifest 和 checkpoint 的哈希记录；
4. 固定 test 的 summary、逐样本结果、失败 overlay 和延迟定义；
5. 场景化策略的技术说明和前后对照；
6. 仿真或实机视频、运行截图和异常恢复证据；
7. 硬件配置、相机参数、通信接口和系统集成说明。

正式场景数据到位前，我先保持当前代码、评估和文书闭环，不重复增加小规模 red-block 数据的 epoch。
