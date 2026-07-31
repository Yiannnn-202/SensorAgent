# 视觉公开数据集选择与使用

更新时间：2026-07-31

## 先说结论

网上有能用的公开数据，但没有一个数据集同时覆盖比赛里的 `roller`、`gear`、
`hex nut`、`short bolt`、`stepped shaft`、`flange`，并且拥有最终比赛相机和真实工位
的外观。公开数据的正确用法是：先补充 Grounding DINO 对机械零件和工具的视觉先验，
再用 Gazebo 精确类别和真实工位数据完成比赛域微调与验收。

当前最值得先核实的是 **Mechanical Parts Dataset 2022**：它有齿轮、螺栓、螺母和轴承，
提供 COCO/YOLO/VOC 标注，能补 `gear`、`bolt`、`nut` 的第一轮通用预热。它仍然
不能替代比赛数据：来源图片来自互联网，已有 split 是否按原始拍摄来源隔离需要重新检查，
`bolt` 也不一定等于比赛的 `short bolt`。

## 推荐清单

| 数据集 | 能补什么 | 标注和许可证 | 在本项目中的定位 |
| --- | --- | --- | --- |
| [Mechanical Parts Dataset 2022](https://zenodo.org/records/7504801) | `bearing`、`bolt`、`gear`、`nut` | 2250 张图；10597 个框；YOLO、COCO、VOC；页面标注 CC BY 4.0 | **首选公开预热集**。公开阶段保留四个原始宽类别；人工确认的特定图片才能进入 `hex nut`、`short bolt` 比赛微调 |
| [MVTec Screws](https://www.mvtec.com/research-teaching/datasets/mvtec-screws) | 13 类螺钉和螺母 | 384 张图、4426 个旋转框；CC BY-NC-SA 4.0 | 可补螺纹/螺母外形和旋转框鲁棒性；许可证限制明显，不能未经确认用于最终公开/商业用途 |
| [Open Images V7](https://storage.googleapis.com/openimages/web/index.html) | `Drill (Tool)`、`Screwdriver`、`Wrench` | 600 类、约 1600 万框；逐图核对来源和许可证 | 只补扳手、螺丝刀、钻头等工具；不覆盖比赛六类零件，适合工具类辅助训练或测试 |
| [BOP T-LESS](https://bop.felk.cvut.cz/datasets/) | 无纹理、相似形状和对称工业物体 | 30 个工业相关物体；RGB-D、2D 框、掩码、6D 位姿；CC BY 4.0 | 补遮挡、弱纹理和相似零件的鲁棒性；对象是实例编号，不能直接当自然语言比赛类别 |
| [BOP ITODD / ITODD-MV](https://bop.felk.cvut.cz/datasets/) | 工业物体、灰度深度、遮挡和多视角 | ITODD 28 个物体；ITODD/ITODD-MV；CC BY-NC-SA 4.0 | 适合 RGB-D 和几何鲁棒性参考；传感器域与最终 RGB 相机不一致 |
| [BOP IPD](https://bop.felk.cvut.cz/datasets/) | 工业 HDR、结构光深度、多视角 | 工业对象、深度和 HDR；CC BY-SA 4.0，部分内容需另行申请 | 适合研究工业光照、相机和深度；不保证有比赛零件 |
| [BOP XYZ-IBD](https://bop.felk.cvut.cz/datasets/) | 工业料箱抓取、杂乱、遮挡和复杂几何 | 6D/2D 框/掩码；CC BY-NC-SA 4.0，部分内容需另行申请 | 最接近 bin-picking 场景，但对象类别仍需人工映射，非商业限制需先确认 |
| [MVTec D2S](https://www.mvtec.com/company/research/datasets/mvtec-d2s) | 复杂背景、实例掩码、光照和遮挡 | 21000 张高分辨率图、60 类；CC BY-NC-SA 4.0 | 主要作实例分割方法参考；主体是超市商品，不建议直接当比赛零件训练集 |

## 目前的使用顺序

1. 先下载并检查 Mechanical Parts Dataset 2022 的 COCO 版本，公开预热阶段保留
   `bearing`、`bolt`、`gear`、`nut` 原始宽类别。
2. 用 `scripts/vision_coco_to_grounding_dino.py` 转为本项目 JSONL。转换前先检查原图、
   COCO 框、重复图片和类别名；不要在全量转换时自动执行 `bolt -> short bolt` 或
   `nut -> hex nut`。只有人工确认的特定样本才能进入更窄的比赛类别清单。
3. 与 Gazebo 数据合并前，按原始来源/场景重新划分 `train/val/test`。不能把公开集的
   `test` 直接当比赛最终测试集，也不能把同一网络图片的裁剪版分到不同集合。
4. 公开数据先使用独立四类配置做通用预热；随后再用比赛六类文本顺序和仿真/真实数据
   微调。`roller`、`stepped shaft`、`flange` 仍必须靠仿真和真实工位数据补齐。
5. 最终冻结一批不参与训练的真实工位图片，单独报告公开集预热、仿真微调和真实数据微调
   三种设置，不能把混合后的一个数字当成公开数据集效果。

## Mechanical Parts Dataset 的落地命令

下载页面提供 COCO 压缩包。解压后，假设 COCO 文件为
`data/vision/public/mechanical_parts_2022/annotations/instances_train.json`，原图根目录为
`data/vision/public/mechanical_parts_2022/images`，类别映射可以从模板开始：

```powershell
python scripts\vision_coco_to_grounding_dino.py `
  --annotations data\vision\public\mechanical_parts_2022\annotations\instances_train.json `
  --image-root data\vision\public\mechanical_parts_2022\images `
  --output data\vision\public\mechanical_parts_2022\mechanical_train.jsonl `
  --category-map configs\vision_public_mechanical_parts_mapping.example.yaml `
  --split train `
  --scene-prefix public_mechanical_train `
  --source-url https://zenodo.org/records/7504801 `
  --source-license "CC BY 4.0"
```

转换器只保留明确映射的正样本。默认不把没有映射目标的图片自动写成负样本，这是为了
避免“图里有目标但没有标注”被错误训练成背景。只有人工确认其余目标都已标注后，才可以
追加 `--include-negative`。

转换完成后先运行 Grounding DINO 预检：

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino_public_mechanical.example.yaml `
  --manifest data\vision\public\mechanical_parts_2022\mechanical_parts_train_val.jsonl `
  --dry-run
```

公开预热配置要求 train/val 都覆盖 `bearing`、`bolt`、`gear`、`nut`。比赛六类训练
仍使用 `configs/vision_train_grounding_dino.example.yaml`；不要为绕过预检伪造公开集
没有的比赛类别。

## 下载、提交和许可证边界

- 公开集原图、标注压缩包、解压目录、转换后的 JSONL 和训练运行结果都放在本地
  `data/vision/` 或 `runs/`，不上传 GitHub。
- GitHub 只提交下载页、数据集版本、许可证、类别映射模板、转换脚本和哈希记录。
- Zenodo 页面上的 CC BY 4.0 只说明该数据集发布记录的授权；原始互联网图片的来源和
  使用边界仍要由项目确认。MVTec Screws、ITODD、XYZ-IBD、D2S 的非商业条款尤其不能
  忽略。
- 公开数据只进入训练或辅助验证，最终比赛测试集必须来自独立的仿真场景和真实工位，
  且不能把公开图片混进去后再宣称是真实工位准确率。
