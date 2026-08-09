# 黑白料箱金属零件场景

该场景与默认 `industrial_pgs.sdf` 相互独立。它复用相同的 RM65-B、工作台、RGB-D 相机架、照明和 ROS 2 控制链路，并提供桌面散放取料区和白底黑线的 3x3 分格目标料箱。

## 首次准备

首次在新机器上运行前，安装 ROS 2 Humble、`rosdep` 和 `colcon`，然后准备上游 RM65-B 包并构建工作区：

```bash
cd ~/SensorAgent
bash scripts/linux/prepare_rm65_b_sim.sh
```

## 启动场景

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh \
  world_file:=industrial_sorting_metal_pgs.sdf
```

## 初始布局

七类金属零件散放在工作台一侧，3x3 料箱位于另一侧且初始为空，用于语音指令驱动的抓取和分格放置。料箱为 `351 x 351 mm`，每个格位约有 `105 x 105 mm` 的净宽和 `55 mm` 外壁，供 Robotiq 2F-85 自上而下进入。

圆柱、轴和螺栓以横放姿态初始化，避免仿真开始后滚动。料箱墙体和分隔条均有碰撞体，可防止零件跨格。

## 抓取姿态

该场景当前使用配置驱动的自上而下抓取。`configs/robot_sorting_sim.yaml`
中的 `release_profiles` 不只记录释放开口和放置高度，也可以为零件记录
`grasp_orientation`。默认姿态为 `[0.0, 1.0, 0.0, 0.0]`；对于滚轮和阶梯轴
这类长轴沿 `base_link` X 方向的横放长件，配置使用
`[0.70710678, 0.70710678, 0.0, 0.0]`，让俯视下的手爪旋转 90 度，使手指
跨短边闭合，而不是沿长轴夹两端。

这不是点云 PCA 自动定向抓取；它依赖仿真场景中已知的零件初始方向。真实
视觉任意姿态抓取仍需从 mask/depth 生成点云或主轴信息，再接入
`robot.plan_oriented_pick`。

## 语音分拣

启动场景后，在另一终端运行。此入口不使用 LLM 或视觉，只使用本机已有的 ASR/VAD 模型，并将中文指令确定性地转换为分拣抓放任务：

```bash
cd ~/SensorAgent
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_sorting_voice_sim.py --execute --duration 15
```

支持的零件名：`方块`、`阶梯轴`、`中空圆套`、`滚轮`（或“滚柱”）、`六角螺母`、`短螺栓`、`法兰套`。目标格位为 `1号格` 至 `8号格`，分别对应 `bin_cell_1` 至 `bin_cell_8`。

例如：

```text
把方块放到1号格
将短螺栓放到六号格
把滚柱放到第3格
```

可先用文本和假机器人检查指令映射，无需启动 Gazebo 或使用麦克风：

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_sorting_voice_sim.py --text "把方块放到1号格"
```

## 常驻分拣会话

如果希望更接近完整 Agent 工作方式，不要每条指令都重启一次脚本。启动仿真和桥接后，可以运行常驻会话入口，让 Agent 只初始化一次，然后循环等待、解析和执行多条分拣指令：

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_sorting_session.py --mode voice --execute --duration 15
```

开发和调试时可先使用文本循环，不需要麦克风、ASR/VAD 模型或 Gazebo 执行：

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_sorting_session.py --mode text
```

会话启动后输入：

```text
把方块放到1号格
将短螺栓放到六号格
退出
```

`--execute` 会连接 `http://127.0.0.1:8765` 的 Gazebo/MoveIt 机器人桥；不加 `--execute` 时自动切换到 fake robot backend 做干跑。单条指令失败不会结束会话，Agent 会打印该轮 JSON 结果并继续等待下一条指令。`退出`、`exit` 或 `quit` 用于结束会话。
