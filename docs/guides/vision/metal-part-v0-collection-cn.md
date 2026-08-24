# metal_part_v0 Gazebo 数据集采集 runbook

目标：为金属零件（滚轮 / 六角螺母 / 短螺栓之外的新类别，或对现有金属类别补充数据）采集一份 Roboflow-ready 数据集，缓解审计报告指出的 recall 不足、数据规模偏小问题。

本 runbook 对应分支 `feat/vision-metal-dataset`。采集脚本已支持 `--prefix`，多类别并行采集时文件互不混淆。

> 所有 `python` 命令一律用仓库 `.venv/bin/python`（Python 3.12）。
> 系统 `python3` 是 3.10，导入项目包会因 `StrEnum` 缺失直接报错。

## 1. 目录结构

数据目录不入 Git（`.gitignore` 已含 `/data/vision/`），只在本机保留：

```text
data/vision/metal_part_v0/
├── manifest.jsonl          # 采集清单（append-only，一行一帧）
├── roboflow_images/        # 上传 Roboflow 标注用的 RGB PNG
│   └── metal_part_001.png
└── raw/                    # 每帧完整 RGB-D 产物
    └── metal_part_001/
        ├── rgb.npy
        ├── depth.npy
        ├── camera_info.json
        └── manifest.json
```

manifest 字段：`capture_index, scene_id, captured_at, class_name, image, raw_dir, depth, camera_info, capture_manifest, annotation_status`。`annotation_status` 初始为 `pending`，Roboflow 标注完成后回写。

## 2. 启动 Gazebo

Ubuntu 22.04 + ROS 2 Humble：

```bash
cd ~/SensorAgent
bash scripts/linux/run_industrial_sorting_metal_sim.sh
```

（等价于 `run_rm65_b_sim.sh world_file:=industrial_sorting_metal_pgs.sdf robot_mount_yaw:=π robot_mount_y:=0`。）

等待启动完成后确认相机话题在发布：

```bash
source /opt/ros/humble/setup.bash
ros2 topic hz /industrial_camera/image
```

注意：采集只需要 Gazebo 相机在跑，机械臂可以不动；不需要 HTTP Bridge。

## 3. 开始采集

```bash
.venv/bin/python scripts/linux/collect_gazebo_dataset.py \
  --dataset-dir data/vision/metal_part_v0 \
  --class-name "metal part" \
  --prefix metal_part \
  --target-count 60
```

交互循环：

1. 在 Gazebo 里拖动 / 旋转零件到一个新位姿（也可以增删同类零件、调整光照）
2. 回到终端按 `1` 采集（直接回车等同 `1`；`2` 看进度，`0` 退出）
3. 重复；中断续采自动接序号，已采数据保留

`--prefix` 是类别命名空间：`metal_part` 与 `red_block` 的序号、scene_id、raw 目录互不干扰。每类一个 prefix，不要混用。

相机话题刚启动还没发布时脚本会等 `--timeout`（默认 10s）后重试；若持续超时，先用 `ros2 topic hz` 确认 Gazebo 完全起来了再重跑。

## 4. 姿态与场景覆盖清单

对照审计报告要求（多姿态、密集、遮挡、负样本），每采 20 张对照打勾：

- [ ] 正放（主姿态，约 40%）
- [ ] 侧放 / 倒放（倾倒姿态）
- [ ] 视野内多个同类实例（密集、部分遮挡）
- [ ] 不同桌位区域（左 / 中 / 右、近 / 远）
- [ ] 与他类零件相邻（类间干扰）
- [ ] 空场景或不含目标类（负样本，每 20 张至少 2 张）

## 5. 数量目标

| split | 目标张数 | 说明 |
| --- | ---: | --- |
| train | ≥ 48 | 与 red_block_v0 对齐起步，越多越好 |
| val | ≥ 6 | 阈值选择用 |
| test | ≥ 8 | 冻结后不再参与调参 |

单类起步 60~70 张采集量，Roboflow 标注后按场景（scene）划分 split，避免同场景图片跨 split。

## 6. 采集完成后

1. 上传 `roboflow_images/` 到 Roboflow 标注，导出 COCO 分割格式
2. 按 `docs/guides/vision/grounding-dino-red-block-v0-cn.md` 的流程转 JSONL、微调、评测
3. 评测时固定 manifest SHA-256 与阈值冻结流程，对照 YOLOE 官方权重跑同集比较——这份数据同时回答"recall 是否达标"和"Grounding DINO vs YOLOE 谁更适合"两个问题

## 7. ontology 配置片段（备用）

采集完成后若要接入 grounding / 批量任务，在 `configs/robot_sorting_sim.yaml` 的 `scene.object_ontology` 增加（按实际零件调整 `grasp_opening`）：

```yaml
    metal_part:
      display_name: 金属零件
      aliases: [金属零件, 金属件, metal part]
      vision_queries: [metal part, industrial metal component]
      instance_ids: [metal_part_01, metal_part_02, metal_part_03]
      grasp_opening: 0.032
```
