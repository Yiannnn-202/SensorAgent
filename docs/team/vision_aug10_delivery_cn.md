# 8 月 10 日视觉交付计划

更新时间：2026-07-31

## 我对最新讨论的判断

这次讨论的总体判断是对的：先用 Grounding DINO + SAM2 把视觉流程跑通，再用仿真和
真实工业场景数据做微调，最后再评估 SAM3 等创新方向。这样能保证 8 月 10 日前先有
可启动、可复现、可验收的基础方案。

有三点需要明确修正：

1. PR #16 已经合入 `main`，不再是等待审查状态；对应本地分支已清理，主线代码仍然保留。
2. 公开数据可以先用于训练链路、通用外观先验和成果展示，但 Mechanical Parts Dataset
   只有 `gear`、`nut`、`bolt` 等宽类别，不能直接证明 `hex nut`、`short bolt`、`roller`、
   `stepped shaft` 和 `flange` 都已经学会。
3. 10～20 张仿真图适合做快速微调和过拟合式链路验证，不足以证明工业泛化。正式结果
   必须另留独立场景测试集，并在后续补充真实工位数据。

## 当前已经完成的部分

- 已将 Grounding DINO 直接微调确定为当前主训练入口，YOLO11n-seg 不再进入当前开发链路。
- 已把 `vision.open_vocab_detect` 的框、掩码、像素中心、可选 RGB-D 位置和错误返回契约
  写入仓库文档，后续底层模型替换时上层接口可以保持不变。
- 已完成 Grounding DINO 训练脚本、JSONL 数据清单预检、COCO 转换工具、数据来源/许可证
  记录和结果哈希追踪。
- PR #16 已合入 `main`；当前代码不需要再从旧实验分支拣选。
- 已在 RTX 4060 上完成 Grounding DINO + SAM2 预训练模型的真实图片冒烟测试。这个证据
  只能证明推理链路和掩码输出能运行，不是比赛准确率。
- 已核对 SAM3 官方仓库、安装要求、参数量、微调入口和许可证，形成独立评估文档。
- 已同步 `main` 到远端最新状态，并删除已经合入的本地视觉实验分支；未合入的恢复分支
  保留，没有误删。

## 我这边负责的下一步

### 收到仿真数据后

```text
接收原始图片和元数据
  -> 检查损坏、重复、类别和 scene_id
  -> 确认最终文本提示顺序
  -> 按完整场景划分 train/val/test
  -> 生成或接收检测框并人工复核
  -> 生成 Grounding DINO JSONL
  -> 执行 --dry-run 数据预检
  -> 直接微调 Grounding DINO V0
  -> 使用 SAM2 生成掩码并做固定集评测
```

第一批数据至少需要：原始 RGB、类别、`scene_id`。如果仿真可以导出，还应保留实例
掩码、depth、相机内参、camera frame、物体实例 ID 和真实位姿。没有检测框时可以先用
预训练 Grounding DINO 生成草稿，但训练前必须人工复核。

### 截止 8 月 10 日的交付物

- 一套能在仿真图片上稳定启动的 Grounding DINO + SAM2 视觉模型流程；
- 一份可直接启动训练的数据目录、JSONL 清单和类别/提示词映射；
- 一份训练预检和启动命令；
- 一份固定测试集上的框、掩码、延迟和失败样本记录；
- 一份模型创新点初稿，其中 SAM3 只作为已经核实过的后续对照方向，不写成当前已接入模型。

这里的“仿真稳定运行”只表示在约定仿真场景和固定测试集上可重复运行，不等同于真实
工业现场已经验收。

## 需要对方交付给我的最小数据

```text
vision_dataset_batch_01/
├── capture_manifest.csv
├── rgb/
│   ├── scene_001/
│   └── scene_002/
├── masks/                 # 能导出时提供
├── depth/                 # 需要三维定位时提供
└── camera/                # 相机参数和坐标系说明
```

`capture_manifest.csv` 至少写明 `image`、`scene_id`、`class_name`。如果没有框，写明
仿真对象实例 ID 或导出框的方式；如果同一图片有多个物体，要逐个记录。

## 当前训练命令

数据放在本地 `data/vision/`，不要上传 GitHub。先检查：

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino.example.yaml `
  --manifest data\vision\competition_train.jsonl `
  --dry-run
```

检查通过后再训练：

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino.example.yaml `
  --manifest data\vision\competition_train.jsonl `
  --device cuda:0
```

训练结果、权重、图片、公开数据缓存和 checkpoint 都留在本地；GitHub 只上传代码、
配置模板、测试、接口契约、来源和说明文档。
