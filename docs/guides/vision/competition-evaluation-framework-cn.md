# 比赛视觉评估与数据交付规范

更新时间：2026-08-08

这份规范落实 2026-08-05 项目讨论中我负责的三件事：先把评估体系固定下来，整理公开数据和训练证据，收到仿真场景后按同一套规则审计、划分和评测。权重、图片和 `runs/` 结果仍然只保存在本地，GitHub 只提交脚本、配置、文档和哈希记录。

## 1. 当前边界

当前视觉入口是 `vision.grounded_sam2`：输入一张 RGB 图片和英文文本 query，先由 Grounding DINO 给出检测框，再由 SAM 2 细化掩码，输出 `bbox_2d`、`mask_polygons`、`center_px` 和耗时。`depth`、`camera_info`、相机 frame 和 `T_base_camera`/TF 是后续三维坐标的输入，不能代替二维训练标注。

已经验证的是 `red_block_v0` 单类别训练、checkpoint 重载和 Grounded SAM 2 Tool 链路。多类别比赛模型、真实工位泛化、RGB-D 到机械臂基座坐标、抓取成功率和实机验收仍然等待场景数据或集成人员的同步证据。

## 2. 数据交付格式

正式训练使用 JSONL，每行一张图片。`objects` 可以有多个实例；空列表表示确认过的负样本。路径必须相对于清单文件，不能写本机绝对路径。

```json
{
  "sample_id": "scene_001_view_03",
  "scene_id": "scene_001",
  "split": "train",
  "image": "rgb/scene_001/view_03.jpg",
  "objects": [
    {
      "class_name": "gear",
      "bbox_xyxy": [120, 80, 360, 300],
      "mask": "masks/scene_001/view_03_gear_01.png",
      "instance_id": "gear_01"
    }
  ],
  "source": {
    "kind": "simulation",
    "capture_session": "sim_20260808_a"
  }
}
```

仿真负责人至少要提供 `image`、`scene_id`、`class_name` 和 `bbox_xyxy`。能导出时保留 `instance_id`、mask、object pose、capture session、depth、`camera_info`、相机 frame、时间戳和深度单位。类别名必须和队长确认过的英文 prompt 顺序完全一致；当前模板是 `roller`、`gear`、`hex nut`、`short bolt`、`stepped shaft`、`flange`，`wrench` 和 `screwdriver` 在确认前不加入。

## 3. 审计和场景划分

收到数据后先运行审计，不要先占用 GPU。审计脚本会检查文件路径、重复 sample/image、图片内容重复、类别、场景 ID、对象列表、框格式、来源和 scene-level split leakage，并把三个 split 清单写入单独目录。

已有 split 的清单：

```powershell
python scripts\vision_dataset_audit.py `
  --manifest data\vision\competition\manifest.jsonl `
  --classes roller gear "hex nut" "short bolt" "stepped shaft" flange `
  --require-all-splits `
  --output-dir data\vision\competition\manifests\audited
```

如果收到的每一行还没有 split，可以让脚本按排序后的 `scene_id` 做确定性分组。它不会把同一场景拆开；这里的比例只是第一版清单生成规则，正式交付后仍需人工复核每个场景的代表性：

```powershell
python scripts\vision_dataset_audit.py `
  --manifest data\vision\competition\manifest_unassigned.jsonl `
  --classes roller gear "hex nut" "short bolt" "stepped shaft" flange `
  --assign-splits `
  --train-ratio 0.70 `
  --val-ratio 0.15 `
  --output-dir data\vision\competition\manifests\audited
```

退出码为 `2` 或 `audit.json` 的 `valid` 为 `false` 时，不得把生成的清单交给训练脚本。重点检查：同一 `scene_id` 不能同时出现在 train、val、test；同一张图片或相同图片内容不能跨 split；val/test 必须覆盖最终类别；负样本必须人工确认没有目标，不能把“有目标但未标注”当背景。

之后再做训练预检：

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino.example.yaml `
  --manifest data\vision\competition\manifests\audited\all.jsonl `
  --dry-run
```

预检通过且 `optimizer_updates > 0` 后，才启动正式微调。RTX 4060 的 AMP 冒烟曾出现 0 次有效更新，比赛数据第一轮继续使用 `amp: false` 并记录显存和温度。

## 4. 指标和统计规则

| 指标 | 统计规则 | 使用 split |
| --- | --- | --- |
| `precision` / `recall` / `f1` | 在固定检测阈值下按 query 行统计 TP、FP、TN、FN | test 报告 |
| `ap50` / `ap75` | 按 confidence 排序，IoU >= 0.50 或 0.75 算 TP，使用 101 点插值 | test 报告 |
| `map50_95` | IoU 从 0.50 到 0.95、步长 0.05 的 query 级 AP 宏平均 | test 报告 |
| `mean_box_iou` | 只对有真实框和预测框的样本取平均 | test 报告 |
| `mean_mask_iou` | 真实 mask 与 SAM 2 polygon 栅格化结果的 IoU | test 报告 |
| `mean_center_error_px` | 真实中心和预测中心的像素欧氏距离 | test 报告 |
| `latency_ms.warm_p50/p95` | 同一个进程复用模型；排除首个 warmup；从 Tool 调用入口计时 | test 报告 |
| `mask_output_rate` / 执行错误数 | 掩码输出覆盖率以及非 `OBJECT_NOT_FOUND` 的运行错误 | test 报告 |

当前 Tool 每张图只返回一个 query 的最佳候选，因此仓库中的 `ap50`、`ap75`、`map50_95` 明确标为 `query_level_single_best_box`。它能满足当前单目标链路的排序评估，但不是 COCO 多实例 mAP。最终多物体场景如果需要标准 COCO mAP，必须保存每个 query 的全部候选框和 confidence，再使用同一份固定 test 做多实例匹配。

阈值只能在 val 上选择，选择后冻结到 test。不能看 test 结果再回调 `box_threshold`、`text_threshold` 或 checkpoint；每一版权重必须记录具体用途，不能把展示专用过拟合权重写成通用模型。

评测命令：

```powershell
python scripts\vision_eval.py run `
  --manifest data\vision\competition\manifests\audited\test.jsonl `
  --config configs\vision_grounded_sam2.yaml `
  --tool vision.grounded_sam2 `
  --output-dir runs\vision\eval\competition_v0 `
  --device 0 `
  --require-masks `
  --save-overlays `
  --box-threshold 0.05 `
  --text-threshold 0.05
```

输出目录必须保留 `results.jsonl`、`summary.json`、`tool_calls.jsonl` 和人工复核过的 `overlays/`。若赛事硬性门槛已确定，可以追加 `--min-map50-95`、`--min-recall`、`--max-warm-p95-ms` 等参数；没有正式门槛时不人为编造通过线。

## 5. 当前公开数据证据

公开 Mechanical Parts Dataset 2022 只做通用机械零件预热，保留原始宽类别 `bearing`、`bolt`、`gear`、`nut`，许可证记录为 CC BY 4.0。当前清单有 1799 张 train、225 张 val 和 9497 个框。

已完成的无 AMP smoke 训练使用 30 张 train + 6 张 val、1 epoch、8 次有效 optimizer update，只证明训练入口可以更新参数。计划中的全量公开预热在第 8 轮附近因 RTX 4060 达到 87 C 并报告 `SW Thermal Slowdown: Active` 而主动停止；保留的 `checkpoint-best` 是 7 个文件、约 690 MB，`model.safetensors` SHA-256 为：

```text
18B868C794FAEB1AE21CB6B7AFB6AFA6326C15B9537CD8EE9A887F0C5FC84159
```

这份权重是“公开预热中间 checkpoint”，没有完整公开训练摘要和最终公开评测，不能命名或宣传为 `public_mechanical_v1`。`red_block_v0` 的单类别链路证据也只用于流程验证，不能补齐比赛缺失类别。

## 6. 交付清单

每一版展示或比赛权重交付以下内容：

1. 完整 checkpoint 目录，而不是单独的 `model.safetensors`。
2. 训练配置、类别和 prompt 顺序、manifest SHA-256、数据来源/许可证和 checkpoint SHA-256。
3. 固定 test 的 `summary.json`、逐样本 `results.jsonl`、延迟定义、阈值来源和失败 overlay。
4. 一段用途说明：展示专用、仿真验证、公开预热或正式比赛候选。
5. 当前限制：是否有 mask、depth、camera_info、TF、Gazebo 或真实机器人证据。

没有新场景数据时，不重复增加 `red-block` epoch。下一次训练的阻塞项是最终场景、类别和英文 prompt 的确认，以及对应的多类别图片和标注交付。
