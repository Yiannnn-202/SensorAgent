# Grounding DINO red_block_v0 训练交接记录

这份记录是我这边把第一轮 Grounding DINO 微调做完后的交接说明。重点是把目前真正做过的事情、权重怎么交接、结果能说明到什么程度写清楚，避免把一版权重说成最终比赛模型。

## 1. 当前结论

我已经直接微调了 Grounding DINO 本体，并把权重重新加载到 `vision.grounded_sam2` 链路中验证过。当前权重叫 `red_block_v0`，只有一个类别：`red block`。

这版可以用于：

- 检查 Grounding DINO 训练脚本是否能正常工作；
- 检查 checkpoint 能否重新加载；
- 检查 Grounding DINO + SAM 2 的整体 Tool 链路；
- 给后续多类别训练提供第一版参数和评测方式。

这版不能直接说明最终比赛模型已经完成。现在仍然缺少多类别数据、真实工位数据、RGB-D 到机械臂坐标的验收，以及仿真抓取成功率统计。

## 2. 我这次做了什么

### 数据

数据来自本地 `red block` COCO 分割数据，转换成 Grounding DINO 使用的 JSONL 清单后再训练。数据没有上传 GitHub。

| split | 图片 | 正实例 | 负样本 | 场景 |
| --- | ---: | ---: | ---: | ---: |
| train | 48 | 42 | 6 | 16 |
| val | 4 | 3 | 1 | 4 |
| test | 4 | 3 | 1 | 4 |

这轮数据规模比较小，test 只有 4 张图，所以结果只能作为流程验证，不能当作工业泛化结论。

### 训练

- 基础模型：`IDEA-Research/grounding-dino-tiny`
- 微调方式：Grounding DINO 全参数微调
- 类别提示词：`red block`
- epoch：10
- batch size：1
- learning rate：`1e-5`
- device：`cuda:0`
- AMP：关闭
- 有效 optimizer update：480
- 跳过的 optimizer step：0
- 最好验证集 loss：`27.77961301803589`
- 训练耗时：约 263 秒

训练 loss 从约 `43727.97` 降到 `170.08`，验证集 loss 从约 `9088.99` 降到 `27.78`。这说明训练过程确实发生了参数更新，但不等于模型已经具备足够的比赛泛化能力。

## 3. 权重怎么交接

完整 checkpoint 目录在我电脑上：

```text
runs/vision/train/grounding_dino_red_block_v0/output/checkpoint-best
```

目录里需要一起保留 `model.safetensors`、`config.json`、tokenizer 和预处理配置，不能只拿一个权重文件。当前目录约 657 MB。

SHA-256：

```text
030594d0ed79ddaeffe4d0df9b34e1a59e1ff4078d8c1c57f3d08424e619426e
```

这版权重不提交 GitHub。GitHub 里只记录模型来源、训练配置、数据哈希、权重哈希和评测边界；实际权重通过共享目录、网盘或其他大文件方式单独交接。

训练摘要和本地报告分别是：

```text
runs/vision/train/grounding_dino_red_block_v0/output/sensoragent_grounding_dino_train_summary.json
runs/vision/train/grounding_dino_red_block_v0/REPORT_CN.md
```

## 4. 评测结果

微调后不能直接照搬预训练模型的默认阈值。默认使用 `box_threshold=0.35`、`text_threshold=0.25` 时，test 结果是：

```text
TP / FP / TN / FN = 0 / 0 / 1 / 3
Recall = 0
```

我只在 val 上重新选择阈值，然后固定阈值评测 test。使用：

```text
box_threshold = 0.05
text_threshold = 0.05
```

得到：

| 指标 | 结果 |
| --- | ---: |
| TP / FP / TN / FN | 3 / 1 / 0 / 0 |
| Precision | 0.750 |
| Recall | 1.000 |
| F1 | 0.857 |
| 平均 box IoU | 0.912 |
| 平均 mask IoU | 0.845 |
| 平均中心误差 | 0.740 px |
| 掩码输出率 | 1.000 |
| 稳定推理 P50 | 536 ms |
| 稳定推理 P95 | 544 ms |
| 执行错误 | 0 |

3 个正样本都检测到了，框和 SAM 2 掩码基本落在目标上。但负样本里的背景粉色区域仍被识别成 `red block`，所以还有 1 个假阳性。这是下一轮必须补的困难负样本类型。

## 5. 本地加载方式

训练配置模板：

```text
configs/vision_train_grounding_dino_red_block_v0.example.yaml
```

评测配置模板：

```text
configs/vision_eval_grounding_dino_red_block_v0.example.yaml
```

拿到完整 checkpoint 后，把评测配置中的 `grounding_dino_model` 改成实际目录，再使用仓库已有的 `scripts/vision_eval.py` 和 `vision.grounded_sam2` 运行。数据清单和 SAM 2 权重也必须在本地准备好。

## 6. 我下一步还要补什么

1. 接收并核对仿真多类别数据，最终确认类别名称和英文 prompt 顺序。
2. 使用完整场景划分 train、val、test，不能把同一场景的图片拆到不同 split。
3. 加入扳手、螺丝刀、滚筒、齿轮等比赛目标，重新训练 Grounding DINO。
4. 增加背景颜色相近、遮挡、不同角度和不同光照的困难负样本。
5. 用 val 选阈值，再在固定 test 上报告 precision、recall、box IoU、mask IoU 和 P50/P95 延迟。
6. 接入仿真 RGB-D、`camera_info` 和 TF，确认像素中心能正确转换到相机坐标和机械臂基座坐标。
7. 最后再做批量场景重置、抓取成功率和失败恢复统计。

## 7. 这次应该上传到 GitHub 的内容

我这次上传的是：

- `red_block_v0` 的训练和评测配置模板；
- 模型元数据、数据集哈希和 checkpoint 哈希；
- 本训练交接记录；
- README 和视觉交付计划中的状态更新。

我没有上传：

- `model.safetensors` 和其他权重文件；
- `data/vision/` 下的图片、掩码和 JSONL 数据；
- `runs/vision/` 下的评测结果、overlay 和日志；
- Python 虚拟环境、模型缓存和下载文件。

这样其他人能知道我做到了哪一步，也能拿到权重后按同一套配置复现；同时不会让仓库变成几百 MB 的本地实验目录。
