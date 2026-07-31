# SAM3 适配性评估

更新时间：2026-07-31

## 结论先行

SAM3 值得作为后续创新和对照实验，但不应在 2026-08-10 前替换当前交付主线。
当前主线继续使用 Grounding DINO + SAM2：Grounding DINO 直接微调检测框，SAM2 根据
检测框细化实例掩码。这样已经有可运行的接口、配置、测试和本机预训练模型证据，能够
优先完成仿真数据微调和验收。

SAM3 的正确定位是：在基础方案跑通后，使用同一批图片和同一套指标，单独验证它能否
减少模型串联、改善开放词汇实例分割或提升困难样本表现。没有实测前，不能仅凭模型代数
更高就宣称它一定更快或更准。

## 官方资料核验

截至 2026-07-31，Meta 官方仓库已经公开 `facebookresearch/sam3`：

- 仓库：[facebookresearch/sam3](https://github.com/facebookresearch/sam3)
- 项目页：[ai.meta.com/sam3](https://ai.meta.com/sam3)
- 官方论文：[SAM 3: Segment Anything with Concepts](https://arxiv.org/abs/2511.16719)
- 官方模型页：[facebook/sam3](https://huggingface.co/facebook/sam3)
- 官方代码说明模型支持图片和视频，可使用文本、点、框和掩码提示；文字提示可以
  直接参与目标检测、分割和跟踪。
- 官方 README 标注模型约有 8.48 亿参数，由文本条件检测器、跟踪器和共享视觉编码器
  组成。
- 官方安装前提包括 Python 3.12 以上、PyTorch 2.7 以上和 CUDA 12.6 以上，并要求
  申请 Hugging Face checkpoint 访问权限后再下载权重。
- 官方仓库提供训练入口，但训练采用独立的 Hydra 配置和多 GPU/本地 launcher，不能
  直接复用当前 Grounding DINO 的训练脚本。
- 代码、权重和相关材料使用 Meta 的 SAM License。是否可以用于比赛展示、公开分发或
  后续成果发布，需要按许可证和学校/项目要求再确认，不能简单当成 Apache-2.0 处理。
- 2026-03-27 官方又发布了 SAM3.1 Object Multiplex，重点是多目标视频跟踪效率；当前
  项目第一阶段是静态仿真图和单帧 RGB-D，不应为了版本号直接切换到视频优化路线。

## 和当前方案的关系

| 项目 | Grounding DINO + SAM2 | SAM3 候选 |
| --- | --- | --- |
| 当前代码 | 已接入 `vision.open_vocab_detect` | 尚未接入 |
| 检测/分割 | DINO 输出框，SAM2 由框细化掩码 | 一个模型可用文本直接得到框和掩码 |
| 当前训练 | 已有 Grounding DINO 直接微调入口 | 需要另建 SAM3 数据适配和训练配置 |
| 本机证据 | 已完成真实预训练模型冒烟测试 | 尚未申请权重和实测 |
| 资源风险 | 当前视觉环境和 RTX 4060 已跑通 | 8.48 亿参数、权重申请和新环境带来风险 |
| 许可证 | 当前 SAM2 权重按现有使用边界管理 | 需要单独遵守 SAM License |
| 8 月 10 日可交付性 | 高，已有接口和测试 | 低，尚未完成适配和测量 |

## 为什么不能只替换配置

讨论中“只替换底层模型、无需大规模改造”对当前接口层是基本成立的，但对 SAM3
不能理解为改一行 YAML 就完成。当前实现内部明确使用：

```text
GroundingDinoBackend
    -> bbox_2d / confidence / label
UltralyticsSam2Backend
    -> mask_polygons / mask_area_px
VisionOpenVocabularyDetectTool
    -> vision.open_vocab_detect 输出契约
```

如果接入 SAM3，需要新增一个 SAM3 backend，至少处理：模型加载、文本提示、框和掩码
后处理、设备选择、错误信息、耗时统计、checkpoint 路径和许可证说明。只要最终输出仍
符合 `vision.open_vocab_detect` 的现有契约，上层 Agent、ActionList 和机械臂模块可以
继续复用；但内部适配、依赖和测试不能省略。

## 后续对照实验设计

SAM3 不进入当前主线，先按下面顺序做独立实验：

1. 申请官方 checkpoint，建立单独的 `sam3` 环境，不改写 `.venv-vision` 的当前依赖。
2. 用相同的 bus、扳手、螺丝刀、滚筒、齿轮冒烟图片运行文本提示，确认框和掩码都能输出。
3. 使用相同的 10～20 张仿真初始图片和相同的场景划分，记录每类检出情况、框 IoU、
   mask IoU、漏检/误检、冷启动和热启动延迟、显存、模型大小。
4. 如果 SAM3 只在掩码质量上更好，再考虑替换 SAM2；如果检测质量和延迟都更合适，再
   评估是否替换 Grounding DINO；如果不能达到部署预算，就保留为研究结果，不接入演示主线。
5. 所有结果必须和 Grounding DINO + SAM2 在同一测试集上比较，不能用不同图片或不同
   阈值分别得出结论。

当前不做的事情：不在没有 checkpoint 的情况下声称 SAM3 已运行；不把官方 benchmark
数字直接当成比赛效果；不把 SAM3 权重、公开图片或训练输出上传到 SensorAgent。
