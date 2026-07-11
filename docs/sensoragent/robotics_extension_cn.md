# SensorAgent 机械臂与强化学习扩展结构草案

> 状态：结构方案已确认，目录骨架已建立。本文暂不展开具体任务，也不直接更新 `TODO.md`。

## 背景与目标

根据新的项目安排，SensorAgent 不再只负责调用外部机械臂能力，还需要具备一定的项目内机械臂处理能力。新增范围包括：

1. 在现有 Agent、Tool、Skill 和 Workflow 结构中加入机械臂能力。
2. 面向 **RealMan RM65-B**（统一标识：`rm65_b`）搭建 Gazebo 仿真环境。
3. 在仓库内维护可复现的工业场景、机器人模型、仿真配置和启动入口。
4. 支持在仿真环境中进行机械臂操作调试。
5. 建立基于 Gymnasium 风格接口的强化学习训练、评估和策略接入方案。

项目最终运行环境为 **Ubuntu + ROS 2**。Windows 仅作为当前代码、配置和文档开发环境，不作为 ROS 2、Gazebo、MoveIt 2 或强化学习仿真运行环境。

## 调整后的职责边界

本仓库计划新增并维护：

- `rm65_b` 的机器人描述、仿真适配和 MoveIt 2 集成配置。
- Gazebo 工业场景与仿真启动配置。
- SensorAgent 到 ROS 2 机械臂接口的适配层。
- 机械臂原子 Tool、高层 Skill 和任务 Workflow。
- 强化学习环境封装、训练配置、评估流程和策略适配器。
- 仿真任务与真实机械臂任务共用的接口契约和安全约束。

本仓库仍不负责：

- 机械臂固件和厂商底层驱动的开发。
- 绕过 ROS 2 控制栈直接操作硬件。
- 用强化学习策略替代急停、限位、碰撞检测等硬安全机制。

## 建议新增项目分区

```text
SensorAgent/
├── src/sensoragent/
│   ├── skills/
│   │   └── robot/                         # 抓取、放置、复位等高层机械臂技能
│   ├── tools/
│   │   └── robot/                         # 机械臂原子操作及状态查询
│   ├── workflows/
│   │   └── robot/                         # 感知、规划、执行、验证与恢复流程
│   └── integrations/
│       └── ros2/                          # SensorAgent 与 ROS 2 的适配边界
│
├── ros2_ws/
│   └── src/
│       ├── rm_description/                  # 官方 RM65 URDF/Xacro 与网格的最小子集
│       ├── rm_65_config/                    # 官方 RM65 MoveIt 2 配置的最小子集
│       ├── rm_gazebo/                       # 官方 RM65 Gazebo 配置与启动文件的最小子集
│       └── sensoragent_robot_bridge/       # 面向 Agent 的 ROS 2 Action/Service 接口
│
├── simulation/
│   └── gazebo/
│       ├── worlds/
│       │   └── industrial/                # 工业工作台、料箱、装配等场景
│       ├── models/                        # 工件、夹具、设备和场景模型
│       ├── scenarios/                     # 任务初始条件与随机化配置
│       └── config/                        # 物理、传感器和仿真参数
│
├── reinforcement_learning/
│   ├── envs/                              # Gymnasium 环境与 ROS 2/Gazebo 封装
│   ├── policies/                          # 策略网络与推理适配器
│   ├── training/                          # 训练入口和算法配置
│   ├── evaluation/                        # 基线、指标和回归评测
│   └── configs/                           # 奖励、观测、动作和场景配置
│
├── scripts/
│   ├── linux/                             # Ubuntu、ROS 2、Gazebo 启动脚本
│   └── windows/                           # 不依赖 ROS 2 的开发辅助脚本
│
├── tests/
│   ├── ros2/                              # ROS 2 接口和消息契约测试
│   ├── simulation/                        # Gazebo 场景与机械臂仿真测试
│   └── reinforcement_learning/            # 环境、奖励和策略评估测试
│
└── docs/
    ├── robotics/                          # RM65-B、ROS 2、MoveIt 2 和 Gazebo 文档
    └── reinforcement_learning/            # 强化学习方案和实验规范
```

以上目录的 Git 可跟踪骨架已经建立；具体 ROS 2 包、仿真资源和强化学习代码仍应根据后续实施顺序逐步加入。

## 建议的数据与控制链路

```text
用户任务
→ SensorAgent Planner / Workflow
→ Robot Skill
→ Robot Tool
→ ROS 2 Bridge
→ MoveIt 2 / ros2_control
→ Gazebo 中的 rm65_b 或真实 rm65_b
→ 关节、夹爪、视觉、碰撞和任务结果
→ SensorAgent 日志与状态
```

强化学习训练链路建议为：

```text
Gymnasium Environment
→ ROS 2 Action / Service
→ Gazebo + rm65_b
→ observation / execution result
→ reward / terminated
→ RL trainer
→ trained policy
→ SensorAgent policy adapter
```

第一阶段强化学习应优先优化高层操作决策，例如抓取候选选择、重新感知、重试和失败恢复。关节轨迹规划和底层控制继续由 MoveIt 2、`ros2_control` 及安全控制层负责。

## 跨平台约束

- ROS 2、Gazebo、MoveIt 2、`colcon` 和相关 `.sh` 脚本以 Ubuntu 为准。
- Linux 脚本必须使用 LF 换行、POSIX 路径和明确的 ROS 2 环境加载方式。
- Windows 下不假设 ROS 2 或 Gazebo 可运行，只进行 Python 逻辑、配置、契约和文档开发。
- Python 代码不得硬编码 Windows 或 Linux 路径，应使用 `pathlib` 和配置项。
- ROS 2 工作区生成的 `build/`、`install/`、`log/`，以及训练生成的 checkpoint、回放数据和实验输出不得提交到 Git。
- 仿真与真实机械臂应尽量共用 Tool/Skill 契约，仅在 ROS 2 adapter 和运行配置处切换后端。

## 进入 TODO 前需要确认

1. Ubuntu 和 ROS 2 的目标版本，以及与之匹配的 Gazebo 版本。
2. `rm65_b` 官方描述包、驱动和 MoveIt 2 配置的来源与许可。
3. 首批工业场景和工件类型。
4. 首批机械臂 Skill、Tool 及 ROS 2 Action/Service 契约。
5. 强化学习第一阶段的观测空间、动作空间、奖励函数和基线任务。
6. 仿真训练是否需要无界面运行、加速运行或多实例并行。

上述事项确认后，再将工作拆分为可验收阶段并更新根目录 `TODO.md`。
