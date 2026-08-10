# 视频文案用视觉模块单页

这一页已经落成原生 PowerPoint 文件 `视觉模块_二维感知链路_单页展示_20260809.pptx`，保存在工作区根目录，作为本地视频/PPT 交付物，不纳入代码仓库。它只呈现目前已经跑通的视觉链路和已经留档的数字，不把 RGB-D 坐标或机械臂抓取结果写成视觉模型已经完成的能力。约 35 秒讲解词和来源说明已写入演讲者备注。

## 页面标题

**视觉模块：从文本目标到可执行的二维感知结果**

## 页面主体

```text
RGB 图像 + 英文目标 query
            ↓
Grounding DINO
检测目标框与置信度
            ↓
SAM 2
细化目标像素掩码
            ↓
结构化视觉 JSON
bbox_2d / mask_polygons / center_px / latency
```

右侧可以放三行结果：

- `red_block_v0`：单类别 Grounding DINO 全参数微调，10 epoch，480 次有效更新。
- 固定 test：precision `0.750`、recall `1.000`、平均 box IoU `0.912`、平均 mask IoU `0.845`。
- 稳定推理延迟：P50 `536 ms`、P95 `544 ms`；结果来自 4 张 test 图，只作流程验证。

## 讲解词（约 35 秒）

“视觉侧把目标类别作为文本 query 送入 Grounding DINO，先得到目标框，再交给 SAM 2 细化像素掩码。最后统一输出目标框、掩码、多边形、像素中心和耗时，供上层任务规划继续使用。我们先用小规模单类别数据把训练、checkpoint 重载和工具链跑通，再按最终桌面场景采集多类别数据，在固定 test 上报告精度、掩码质量和延迟。”

## 页面底部边界

用小字注明：

```text
当前数字是 red_block_v0 流程验证，不代表最终多类别比赛模型、工业泛化、RGB-D 三维坐标或机械臂抓取验收。
```

## 收到场景数据后的替换位置

场景和类别确认后，只替换右侧三行数字、类别名称、test 样本数和一张失败 overlay；流程图和 JSON 接口不变。新的权重必须注明用途，并重新生成固定 test 的 `summary.json`。不要把公开 Mechanical Parts Dataset 的 `bearing/bolt/gear/nut` 预热结果直接替换成比赛的 `roller/hex nut/short bolt/stepped shaft/flange` 结果。
