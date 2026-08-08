# Grounded SAM 2 严格 Tool 使用与验证说明

本文说明仓库中的 `vision.grounded_sam2` 是什么、如何运行、如何把 COCO 分割数据转成
评测清单，以及 2026-08-01 使用 `red block` 小型仿真数据得到的真实基线结果。

## 1. Tool 的作用

`vision.grounded_sam2` 把两个模型固定组合成一个 Agent Tool：

```text
RGB 图 + 文本 query
  -> Grounding DINO：根据文字找到候选框
  -> SAM 2：根据候选框生成像素级掩码
  -> 中心点、可选 RGB-D 坐标、overlay 和结构化 JSON
```

- Grounding DINO 负责回答“目标大概在哪里”。
- SAM 2 负责回答“目标具体包含哪些像素”。
- Tool 名固定为 `vision.grounded_sam2`。
- 调用者传入 `--no-refine`、`refine_masks=false` 或 `require_masks=false` 都不会关闭
  SAM 2。
- 已检测到目标但 SAM 2 没有返回有效掩码时，调用明确失败，不退化成只有检测框的
  假成功。
- 没有检测到目标时，正常返回 `found=false`。

该实现是对仓库已有 Grounding DINO、SAM 2、RGB-D 几何和空间筛选代码的严格组合
适配层，不是把官方 Grounded-SAM-2 仓库整体复制进来。

## 2. 代码位置

| 内容 | 路径 |
| --- | --- |
| 严格 Tool | `src/sensoragent/tools/vision/grounded_sam2.py` |
| 模型和 RGB-D 实现 | `src/sensoragent/tools/vision/open_vocab.py` |
| Tool 注册 | `src/sensoragent/agent/bootstrap.py` |
| 单图 CLI | `src/sensoragent/services/cli/main.py` |
| 配置 | `configs/vision_grounded_sam2.yaml` |
| 外部接口契约 | `contracts/tools/vision.grounded_sam2.schema.json` |
| 离线评测 | `scripts/vision_eval.py`、`src/sensoragent/evaluation/vision.py` |
| COCO 转换器 | `scripts/vision_coco_segmentation_to_eval.py` |
| 单元测试 | `tests/unit/test_vision_grounded_sam2.py` |

## 3. 环境和权重

在仓库根目录执行：

```powershell
python -m venv .venv-vision
.\.venv-vision\Scripts\python.exe -m pip install --upgrade pip
.\.venv-vision\Scripts\python.exe -m pip install -e .
.\.venv-vision\Scripts\python.exe -m pip install -r requirements-vision.txt
```

默认模型：

```text
Grounding DINO: IDEA-Research/grounding-dino-tiny
SAM 2: models/vision/sam2_t.pt
```

也可以用环境变量指定本地权重：

```powershell
$env:SENSORAGENT_GROUNDING_DINO_MODEL = "D:\models\grounding-dino-tiny"
$env:SENSORAGENT_SAM2_WEIGHTS = "D:\models\sam2_t.pt"
```

首次运行需要下载 Grounding DINO。模型已经完整缓存后，如果 Hugging Face 联网检查
阻塞，可以临时使用离线模式：

```powershell
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
```

离线模式不能用于第一次下载模型。

## 4. 先跑一张图片

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
.\.venv-vision\Scripts\python.exe -m sensoragent.services.cli.main vision-detect `
  --config configs\vision_grounded_sam2.yaml `
  --tool vision.grounded_sam2 `
  --image examples\scene.jpg `
  --query "wrench" `
  --device 0 `
  --overlay runs\vision\wrench_grounded_sam2.jpg
```

没有 NVIDIA 显卡时把 `--device 0` 改为 `--device cpu`。成功结果中的主要字段：

| 字段 | 含义 |
| --- | --- |
| `found` | 是否找到文本目标 |
| `confidence` | Grounding DINO 的文本检测置信度 |
| `bbox_2d` | 图像中的检测框 `[x1, y1, x2, y2]` |
| `mask_polygons` | SAM 2 输出的掩码轮廓 |
| `mask_area_px` | 掩码像素面积 |
| `center_px` | 掩码质心；没有掩码时才使用框中心 |
| `position_camera` | 有深度和相机内参时的相机坐标 |
| `position_base` | 再提供 `T_base_camera` 后的机械臂基坐标 |
| `timing_ms` | 检测、分割和 overlay 的分阶段耗时 |

## 5. 转换 red block COCO 分割数据

原始目录应包含 `train/`、`valid/`、`test/`，每个目录内有图片和
`_annotations.coco.json`。在仓库根目录执行：

```powershell
.\.venv-vision\Scripts\python.exe scripts\vision_coco_segmentation_to_eval.py `
  --source-root "..\red block.v2i.coco-segmentation" `
  --output-root data\vision\team\red_block_v2 `
  --sample-prefix red_block_v2 `
  --query "red block" `
  --category-name "red-block" `
  --dataset-name "Roboflow red block v2" `
  --source-url "https://universe.roboflow.com/yiannnn202s-workspace/red-block" `
  --source-license "CC BY 4.0"
```

转换器支持 COCO 压缩 RLE、普通 RLE 和 polygon，不要求安装 `pycocotools`。它会：

- 把真实 RLE 像素解码成 PNG 掩码；
- 保留正样本和负样本；
- 使用 `--sample-prefix` 生成不会与其他数据集冲突的样本 ID；
- 把 `valid` 规范成 `val`；
- 按 Roboflow 文件名恢复原始 `scene_id` 并检查 train/val/test 场景泄漏；
- 生成 `manifest_train.jsonl`、`manifest_val.jsonl`、`manifest_test.jsonl`、
  `manifest_all.jsonl` 和 `conversion_report.json`。

继续验证完整清单：

```powershell
.\.venv-vision\Scripts\python.exe scripts\vision_eval.py validate `
  --manifest data\vision\team\red_block_v2\manifest_all.jsonl
```

## 6. 批量评测

```powershell
$env:HF_HUB_OFFLINE = "1"          # 仅在模型已缓存时设置
$env:TRANSFORMERS_OFFLINE = "1"    # 仅在模型已缓存时设置
.\.venv-vision\Scripts\python.exe scripts\vision_eval.py run `
  --manifest data\vision\team\red_block_v2\manifest_test.jsonl `
  --config configs\vision_grounded_sam2.yaml `
  --tool vision.grounded_sam2 `
  --output-dir runs\vision\red_block_v2_grounded_sam2_default `
  --device 0 `
  --require-masks `
  --save-overlays `
  --warmup-runs 1
```

输出目录包括：

| 文件 | 内容 |
| --- | --- |
| `results.jsonl` | 每张图的预测、真值、IoU、中心误差和耗时 |
| `summary.json` | 混淆矩阵、均值指标、延迟分位数和验收结果 |
| `tool_calls.jsonl` | Tool 调用开始、成功或失败的结构化日志 |
| `overlays/` | 检测框、掩码、中心点和置信度可视化 |

## 7. red block 数据审计

2026-08-01 的本地转换结果：

| 项目 | 数量 |
| --- | ---: |
| 总图片 | 56 |
| 正样本 | 48 |
| 负样本 | 8 |
| 原始场景 | 24 |
| train | 48 张，其中 42 正、6 负 |
| val | 4 张，其中 3 正、1 负 |
| test | 4 张，其中 3 正、1 负 |
| 跨 split 场景泄漏 | 0 |

原 COCO 文件存在两个同名类别：`id=0, name=red-block` 和
`id=1, name=red-block`，实际 48 条标注全部使用 `id=1`。转换器接受同名 ID，但在
`conversion_report.json` 中保留告警。

另一个数据问题是 48 条标注的 `area` 都等于 bbox 面积，而不是真实掩码面积。评测没有
使用这个错误的 `area` 字段，而是使用解码后的 RLE 像素；本地解码器已与
`pycocotools 2.0.11` 对前 5 条标注逐像素交叉验证，结果一致。仓库运行时不依赖
`pycocotools`。

## 8. 预训练基线结果

使用默认 `box_threshold=0.35`、`text_threshold=0.25`、RTX 4060、
Grounding DINO Tiny 和 SAM 2 Tiny，对 4 张 test 图片实测：

| 指标 | 结果 |
| --- | ---: |
| TP / FP / TN / FN | 3 / 1 / 0 / 0 |
| Precision | 0.750 |
| Recall | 1.000 |
| F1 | 0.857 |
| 正样本平均 box IoU | 0.862 |
| 正样本平均 mask IoU | 0.831 |
| 正样本平均中心误差 | 1.013 px |
| 掩码输出率 | 1.000 |
| 首次冷启动 | 11733 ms |
| 稳定推理 P50 | 515 ms |
| 稳定推理 P95 | 522 ms |
| 执行错误 | 0 |

3 个正样本的框和掩码均落在小红色方块上。唯一负样本中，Grounding DINO 把背景面板
左上角的粉红色大区域当成了 `red block`，SAM 2 随后正确分割了这个错误候选区域，
因此形成 1 个假阳性。

验证集也有同类误检：最低正样本置信度为 `0.62535`，负样本置信度为 `0.62580`。
两者无法靠单一置信度阈值分开，所以没有根据 4 张 test 图片反复调参。后续应补充：

- 只有红色背景区域、没有可抓取方块的困难负样本；
- 不同尺寸、角度、遮挡和光照下的红色方块；
- 比赛相机拍摄的真实工位图片；
- 与背景颜色相近但不应抓取的物体。

以上结果只证明 Tool 链路、数据转换、真实框和真实掩码评测已经跑通。测试集只有 4 张，
不能称为比赛准确率、工业精度或稳定生产模型。

## 9. 2D 与机械臂坐标边界

单张普通 RGB 图只能可靠输出：检测框、掩码、像素中心和置信度。要得到机械臂可使用的
三维位置，还必须同时提供：

1. 与 RGB 对齐的深度图；
2. 相机内参 `camera_info`；
3. 相机到机械臂基座的 `T_base_camera`；
4. 深度单位和时间同步正确的 RGB-D 帧。

缺少其中任一项时，不能把 `center_px` 写成机械臂坐标，也不能声称已经完成真实抓取定位。

## 10. Git 提交边界

应提交：Tool 代码、配置、接口契约、COCO 转换器、评测入口改动、单元测试和本文档。

不应提交：

```text
data/vision/                  数据集和转换后的图片/掩码
runs/vision/                  本地 JSON、耗时和 overlay
models/vision/*.pt            SAM 2 和训练权重
.venv-vision/                 Python 虚拟环境
Hugging Face / Ultralytics 缓存
```

数据和运行结果可单独压缩交接，不能因为本地评测成功就把大文件混入 Git 提交。
