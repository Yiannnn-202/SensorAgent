# 竞赛多实例分拣会话

`scripts/linux/run_competition_sorting_session.py` 是当前竞赛主流程的第一阶段
入口。它把文本或真实语音统一转换为结构化意图，在三类、九实例场景中选择
唯一物体，执行抓放，维护任务世界状态，并在失败时调用分类和恢复规划工具。

## 当前闭环

```text
文本或麦克风
→ Silero VAD + SenseVoice（语音模式）
→ ObjectOntology 领域词汇接地
→ GroundedIntent 类型化指令
→ 多实例歧义检查
→ oracle/config 实例选择
→ industrial.sorting_config_pick_place_actionlist
→ 抓取与放置状态验证
→ 失败分类、恢复计划与有限重试
→ 更新物体和料格状态
```

当前感知后端明确标记为 `oracle_config`：实例位置来自
`configs/robot_sorting_sim.yaml`，用于先验证语言、决策、执行和恢复逻辑。
它不是视觉识别成绩。真实 RGB-D 多实例检测和跨步骤实例跟踪接入后，需保持
相同的 `GroundedIntent` 与世界状态接口。

## 支持的语义

标准类别和常见别名由 `scene.object_ontology` 配置：

| 标准类别 | 示例说法 |
| --- | --- |
| `roller` | 滚轮、滚柱、圆柱滚轮、金属滚轮 |
| `hex_nut` | 六角螺母、螺母、六边形螺母、罗母 |
| `short_bolt` | 短螺栓、螺栓、短螺丝、倒放螺栓 |

支持的实例关系包括：

```text
左、右、前、后、最近、最远、最大、最小、序号
```

`left/right/front/back` 默认以相机视角解释，`nearest/farthest` 以机械臂底座
为参考。当前规则场景中每类三个实例沿 world X 排列，在画面中可能接近同一
列，因此 `left/right` 可能无法区分并触发澄清；规则布局优先使用：

```text
把离机械臂最近的滚轮放到三号格
把最前面第二个六角螺母放到六号格
把最远的短螺栓放到一号格
```

随机混排场景可使用“左边”“右边”等表达。

以下情况不会驱动机械臂：

- 指令未包含受支持类别；
- 多个同类实例但没有空间选择条件；
- 序号超过候选数量；
- 同类物体尺寸相同却要求按最大/最小选择；
- 目标格不存在或已经被本会话中的物体占用；
- “所有/全部”批量任务尚未启用。

系统会返回 `needs_clarification` 或 `unsupported` 以及具体原因，而不是默认
选择中间物体。

## 启动 Gazebo

在 Ubuntu 22.04 + ROS 2 Humble：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh \
  world_file:=industrial_sorting_metal_pgs.sdf
```

等待以下接口就绪：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

## 文本模式

先用 fake robot 验证语言和决策，不控制 Gazebo：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/run_competition_sorting_session.py \
  --mode text
```

输入：

```text
把离机械臂最近的滚轮放到三号格
状态
退出
```

连接真实 Gazebo/MoveIt 执行：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/run_competition_sorting_session.py \
  --mode text \
  --execute
```

单条命令模式适合自动验收：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/run_competition_sorting_session.py \
  --execute \
  --command "把离机械臂最近的滚轮放到三号格"
```

## 真实语音模式

语音模式使用 `robot_sorting_sim.yaml` 中配置的 `sounddevice_vad`、
Silero VAD 和 SenseVoice：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/run_competition_sorting_session.py \
  --mode voice \
  --execute \
  --duration 15
```

每轮会等待一条语音、完成转写，再进入与文本模式完全相同的语义接地和执行
链路。ASR 文本、结构化意图、所选实例、执行步骤和世界状态都会写入结果。

## 失败恢复

默认每条任务允许一次恢复：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/run_competition_sorting_session.py \
  --mode text \
  --execute \
  --max-recovery-attempts 1
```

ActionList 失败后，会：

1. 提取失败步骤、输出和错误；
2. 调用 `recovery.classify_failure`；
3. 调用 `recovery.plan` 生成可解释恢复策略；
4. 若可重试，先调用 `robot.stop`；
5. 在预算内重新执行一次抓放。

报告会保留每次尝试、失败类型、恢复策略和重试结果。当前 oracle 后端无法
在失败后读取 Gazebo 中被碰移物体的真实新位姿，所以掉落后的精确重定位仍
属于真实 RGB-D 阶段；不能把配置坐标重试宣传为视觉重定位。

## 世界状态和日志

会话维护：

- 九个实例的 `on_table / selected / placed / unknown` 状态；
- 每个料格是否为空及占用实例；
- 当前任务步骤和恢复次数；
- 状态变化历史。

默认结果写入：

```text
logs/tasks/competition_sorting_<timestamp>.jsonl
logs/tasks/competition_sorting_<timestamp>.trace.jsonl
```

可通过 `--jsonl-out` 指定路径。交互中输入 `状态` 可查看完整状态快照。

## 下一阶段

保持指令和状态接口不变，替换 `oracle_config` 的顺序为：

1. RGB-D 捕获；
2. Grounding DINO + SAM2 返回全部同类候选；
3. 深度定位和工作空间过滤；
4. 空间约束选择；
5. 任务内实例跟踪；
6. 抓后和放后重新感知；
7. 根据真实观测位置恢复。

完成前，演示和实验必须明确区分 oracle 决策闭环与 live RGB-D 感知闭环。
