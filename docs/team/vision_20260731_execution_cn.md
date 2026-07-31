# 7 月 31 日视觉任务执行记录

更新时间：2026-07-31

## 1. 我确认的技术路线

8 月 10 日前继续使用 Grounding DINO + SAM 2。Grounding DINO 负责根据文本找目标并
输出检测框，SAM 2 根据框生成实例掩码；当前训练直接微调 Grounding DINO。YOLO11n-seg
不进入本阶段开发链路，SAM3 放在基础方案完成后做同测试集对照。

这条路线能按时形成可运行、可训练、可验收的基础方案，但要保留三个边界：

- 公开数据只用于训练流程验证和机械零件通用预热，不能替代比赛场景数据；
- 10～20 张仿真图只够做快速微调和过拟合式链路验证，不能证明真实工业泛化；
- 没有同步深度、相机内参和相机到机械臂基座的变换时，像素中心不是抓取坐标。

## 2. 本次实际完成的内容

我从 Zenodo 下载并校验了 Mechanical Parts Dataset 2022 的 COCO 版本。原始 RAR 大小为
`92,749,519` 字节，MD5 为 `b2964da3c2e8171b63849f6d15c6e733`，与官方记录一致，
许可证记录为 CC BY 4.0。图片、标注、清单和训练结果都留在本地，没有提交 GitHub。

训练集原始 COCO 声明 1800 张图片，但压缩包实际只有 1799 张，缺少图片 ID `378`，
对应 2 个轴承框。我新增了 `scripts/vision_coco_audit.py`：它默认只审计，只有显式指定
`--clean-output` 才会生成清洗副本，并在报告中记录原始标注哈希、缺失文件、图片 ID、
删除的框数和清洗副本哈希。原始 COCO 和 RAR 没有被修改。

清洗和转换结果如下：

| split | 图片 | 实例框 | bearing | bolt | gear | nut |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 1799 | 8384 | 1680 | 2074 | 2086 | 2544 |
| val | 225 | 1113 | 213 | 334 | 257 | 309 |

合并清单已通过真实文件、类别覆盖、框格式、来源/许可证、重复图片和跨 split `scene_id`
检查：

```text
manifest_sha256: 10dcdfc04acad7d17092a6499f386ebe0cd1ddf2a1b72df801130e1edb035b00
dataset_sha256:  34d9483c9f4cc3bcc116ff749051fac36cf607edbc09e907b866830cebbae5e0
```

我还对 train/val/test 共 2249 个实际图片文件做了 SHA-256 和 Roboflow 原始文件名前缀
检查，没有发现跨 split 的完全相同文件或同源增强文件。这个检查不能代替感知哈希或人工
近重复审查，因此正式比赛数据仍要按真实 `scene_id`/采集批次先划分再增强。

公开预热阶段保留 `bearing/bolt/gear/nut` 四个宽类别。这里没有把全部 `nut` 自动改成
`hex nut`，也没有把全部 `bolt` 自动改成 `short bolt`。

## 3. 一轮 Grounding DINO 预热验证

我从全量清单抽取了四类均覆盖的小子集：30 张训练图、6 张验证图，训练集 192 个框，
验证集 56 个框。该子集只用于验证训练、优化器更新、checkpoint 保存和重新加载，不用于
报告准确率。

第一次按 FP16 AMP 运行时，8 次优化器更新全部被动态缩放跳过，脚本返回
`no_optimizer_update`。我保留了失败记录，并按脚本提示用 `--no-amp` 重跑。第二次结果：

```text
status:                  completed
optimizer_updates:       8
skipped_optimizer_steps: 0
duration_s:              21.681
train_loss:              41678.1972
val_loss:                11041.0410
peak_allocated_bytes:    5686481408
peak_reserved_bytes:     5895094272
checkpoint_sha256:       bcbd3c1de29176de1cfc778fc0c26aa27aa3bfa9be7c04fae551f545be46d4bb
model_file_sha256:       b790f6630c487b4c2c247ac412cda3007ae01ff1fcc26c24189d84eb174635d5
```

保存后的模型文件哈希与初始模型不同，并且已经离线重新加载成功，模型参数量为
`172,249,090`。因此这次验证能证明参数发生了更新、checkpoint 可读；单轮小子集的 loss
不能解释为精度、收敛结果或比赛效果。基于本机结果，公开预热示例配置当前使用
`amp: false`。

本次视觉专项回归为 `63 passed`。完整仓库回归为 `249 passed, 3 failed`，三个失败分别
来自本机缺少 `models/asr/vad/silero_vad.onnx`、未启动 `127.0.0.1:8765` robot bridge，
以及 DecisionTree 的 `failed_step` 实际值与测试预期不同，均不在本次视觉改动范围内。

## 4. 还缺的输入和下一步

截至 7 月 31 日，我还没有收到正式的 10～20 张仿真图片，因此比赛类别微调仍未开始。
仿真侧最少需要给我原始 RGB、`scene_id` 和 `class_name`；能导出检测框、实例掩码、
depth、`camera_info`、相机坐标系和物体真实位姿时一起提供。

数据到位后我按下面顺序执行：

```text
检查图片和类别
  -> 按完整场景划分 train/val/test
  -> 生成或接收检测框并人工复核
  -> 生成比赛六类 Grounding DINO JSONL
  -> 执行 --dry-run
  -> 微调 Grounding DINO V0
  -> SAM 2 生成掩码
  -> 固定测试集输出框、掩码、延迟和失败样本
```

## 5. 简短说明

我负责把文字目标转换成后续模块能用的检测框、掩码和位置。现在 Grounding DINO +
SAM 2 的推理、统一接口、数据检查和 Grounding DINO 直接微调入口都已经完成。7 月 31 日
我又完成了公开机械零件数据的下载校验、缺图审计、全量转换和一轮有效参数更新，训练
checkpoint 也能离线重新加载。当前真正没开始的是比赛仿真数据微调，因为第一批正式
仿真图还没有交付；收到后我会直接按固定场景划分启动 V0 训练和评测。
