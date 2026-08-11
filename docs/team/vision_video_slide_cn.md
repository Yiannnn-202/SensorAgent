# XH-202607 视频文案用视觉模块单页

我已经把这一页落成原生 PowerPoint 文件 `视觉模块_桌面场景创新_单页展示_20260811.pptx`，保存在工作区根目录，作为本地视频/PPT 交付物，不纳入代码仓库。我只呈现目前已经跑通的视觉链路和已经留档的数字，不把 RGB-D 坐标或机械臂抓取结果写成视觉模型已经完成的能力。约 35 秒讲解词和来源说明已写入演讲者备注。

## 页面标题

**视觉模块：从文本目标到桌面场景感知结果**

## 页面主体

```text
RGB 图像 + 英文目标 query
            ↓
Grounding DINO
输出全部候选框与置信度
            ↓
桌面场景约束重排
工作区 / 禁抓区 / 边界 / 重叠风险
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
- 场景创新：可选 `scene_aware` 候选重排，输出 `scene_score`、拒绝原因和歧义风险；最终 ROI 和尺寸先验待比赛工位冻结后校准。

## 讲解词（约 35 秒）

"我把目标类别作为文本 query 送入 Grounding DINO，先保留桌面中的多个候选框，再用工作区、禁抓区和候选重叠等场景约束做一次重排。通过约束的候选交给 SAM 2 细化像素掩码，最后统一输出框、掩码、像素中心、耗时和风险字段。当前我先用小规模单类别数据把训练、checkpoint 重载和工具链跑通，收到最终桌面场景后，再采集多类别数据，在固定 test 上对比普通置信度选择和 scene-aware 选择。"

## 页面底部边界

用小字注明：

```text
当前数字是 red_block_v0 流程验证，不代表最终多类别比赛模型、工业泛化、RGB-D 三维坐标或机械臂抓取验收。
```

场景约束模块目前只有代码级专项测试，不把示例 profile 或拒绝率写成最终比赛指标。

## 收到场景数据后的替换位置

场景和类别确认后，只替换右侧三行数字、类别名称、test 样本数和一张失败 overlay；流程图和 JSON 接口不变。新的权重必须注明用途，并重新生成固定 test 的 `summary.json`。不要把公开 Mechanical Parts Dataset 的 `bearing/bolt/gear/nut` 预热结果直接替换成比赛的 `roller/hex nut/short bolt/stepped shaft/flange` 结果。
