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
