# SensorAgent 项目架构文档

## 1. 项目目标

本项目面向工业环境下的物体感知识别与指令交互任务，研发一个具备自然语言理解、开放词汇视觉感知、三维定位、任务规划、机械臂执行与失败恢复能力的交互型智能体系统。

系统目标是实现如下闭环：

```text
自然语言指令
→ 任务理解
→ 开放词汇分割
→ RGB-D 三维定位
→ 行为树任务规划
→ 机械臂抓取与放置
→ 视觉验证
→ 失败恢复
```

项目采用 **仿真先行、真实迁移** 的实现路线：先搭建与真实机械臂型号一致的仿真环境，跑通完整 Agent 工作流，再迁移至真实 ROS2 机械臂系统进行验证。

## 2. 总体架构

系统采用 **Agent 中台 + WebSocket 服务编排 + ROS2 执行底座** 的架构。

```text
┌────────────────────────────┐
│        Web UI / CLI         │
│ 自然语言输入、状态展示、视频 │
└─────────────┬──────────────┘
              │ WebSocket
┌─────────────▼──────────────┐
│        Agent Server         │
│ 指令解析 / 任务编排 / 状态机 │
└─────────────┬──────────────┘
              │
      ┌───────┼──────────────────────┐
      │       │                      │
┌─────▼───┐ ┌─▼────────┐      ┌──────▼──────┐
│感知服务 │ │行为树服务 │      │恢复策略服务 │
│SAM3/RGBD│ │BT Runtime│      │RL Recovery  │
└─────┬───┘ └─┬────────┘      └──────┬──────┘
      │       │                      │
      └───────┼──────────────────────┘
              │ Robot Command API
┌─────────────▼──────────────┐
│       Robot Gateway         │
│ WebSocket/HTTP ↔ ROS2 Bridge│
└─────────────┬──────────────┘
              │ ROS2
┌─────────────▼──────────────┐
│ ROS2 Robot Stack            │
│ MoveIt2 / tf2 / ros2_control│
│ Camera / Gripper / Driver   │
└────────────────────────────┘
```

## 3. 模块划分

| 模块 | 职责 |
|---|---|
| **Web UI / CLI** | 接收自然语言指令，展示 RGB 图、深度图、分割结果、行为树状态和执行日志 |
| **Agent Server** | 系统主控，负责指令接收、任务编排、模块调用和状态管理 |
| **Instruction Parser** | 将自然语言解析为结构化任务 JSON |
| **Perception Service** | 调用 SAM3 / DINO-X 完成开放词汇分割，并结合 RGB-D 输出 3D 位姿 |
| **Scene Graph Service** | 构建工业场景图，包括物体、料箱格子、空间关系和可抓取区域 |
| **Behavior Tree Runtime** | 将任务拆解为可执行节点，控制 detect、grasp、place、verify、recover 流程 |
| **Robot Gateway** | 将 Agent 高层动作转换为 ROS2 action/service/topic |
| **ROS2 Robot Stack** | 负责机械臂控制、MoveIt2 规划、tf 坐标变换、夹爪控制和相机驱动 |
| **RL Recovery Service** | 针对抓取失败、放置偏移、目标遮挡等场景生成恢复动作 |

## 4. 核心数据流

用户输入：

```text
把左边的银色滚柱放到第三个格子里
```

指令解析结果：

```json
{
  "task_type": "pick_and_place",
  "object_query": "left silver roller",
  "target_query": "third cell of the bin",
  "constraints": {
    "avoid_collision": true,
    "verify_after_place": true
  }
}
```

感知模块输出：

```json
{
  "object": {
    "label": "silver roller",
    "mask_id": "mask_001",
    "pose_3d": [0.42, -0.13, 0.08, 0, 0, 1.57],
    "confidence": 0.91
  },
  "target": {
    "label": "bin_cell_3",
    "pose_3d": [0.60, 0.20, 0.10, 0, 0, 0],
    "confidence": 0.95
  }
}
```

行为树执行流程：

```text
ParseInstruction
→ CaptureRGBD
→ SegmentObject
→ EstimateObjectPose
→ SegmentTargetCell
→ EstimateTargetPose
→ PlanGrasp
→ ExecuteGrasp
→ VerifyGrasp
→ PlanPlace
→ ExecutePlace
→ VerifyPlace
→ RecoverIfFailed
```

## 5. WebSocket 与 ROS2 的边界

系统中 WebSocket 和 ROS2 分工明确：

| 通信层 | 负责内容 |
|---|---|
| **WebSocket** | Agent 高层任务、状态事件、感知结果、行为树状态、前端展示 |
| **ROS2** | 机械臂控制、轨迹执行、传感器数据、tf 坐标变换、实时硬件接口 |

Agent 不直接控制电机或底层关节，而是通过 Robot Gateway 调用高层动作原语：

```python
capture_rgbd()
move_to_pose()
open_gripper()
close_gripper()
pick()
place()
verify_object_in_cell()
```

Robot Gateway 再将这些动作转换为 ROS2 MoveIt2 规划、夹爪控制和相机调用。

## 6. 仿真与真实机械臂统一接口

系统通过统一执行接口屏蔽仿真和真实环境差异：

```text
RobotExecutor
├── SimExecutor
└── RealExecutor
```

Agent 和行为树只依赖 `RobotExecutor`，不直接依赖具体仿真平台或真实机械臂驱动。

```python
class RobotExecutor:
    def capture_rgbd(self): ...
    def move_to_pose(self, pose): ...
    def open_gripper(self): ...
    def close_gripper(self): ...
    def pick(self, grasp_pose): ...
    def place(self, target_pose): ...
    def get_robot_state(self): ...
    def verify_object_in_cell(self, object_id, cell_id): ...
```

切换仿真或真实机械臂时，仅通过配置切换：

```yaml
robot:
  backend: sim   # sim / real
```

## 7. 推荐目录结构

```text
sensoragent/
├── apps/
│   ├── agent_server/          # FastAPI + WebSocket 主服务
│   ├── web_ui/                # 可视化前端
│   └── cli/                   # 命令行入口
│
├── core/
│   ├── agent/                 # Agent 编排逻辑
│   ├── planner/               # 指令解析与任务 JSON 生成
│   ├── behavior_tree/         # 行为树节点与运行时
│   ├── schemas/               # Pydantic 数据结构
│   └── config/                # 配置管理
│
├── perception/
│   ├── open_vocab/            # SAM3 / DINO-X 适配器
│   ├── rgbd/                  # 深度图、点云、相机内参
│   ├── scene_graph/           # 3D 场景图
│   └── calibration/           # 手眼标定、坐标变换
│
├── execution/
│   ├── executor_base.py       # RobotExecutor 抽象接口
│   ├── sim_executor.py        # 仿真执行器
│   ├── real_executor.py       # 真实执行器
│   └── primitives/            # pick/place/move/verify 动作原语
│
├── ros2_ws/
│   └── src/
│       ├── robot_gateway/     # WebSocket/HTTP ↔ ROS2 桥接节点
│       ├── robot_bringup/     # 真实机械臂启动配置
│       ├── robot_moveit/      # MoveIt2 配置
│       └── sim_bringup/       # 仿真启动配置
│
├── recovery/
│   ├── rl_envs/               # 强化学习仿真环境
│   ├── policies/              # 训练好的恢复策略
│   └── trainers/              # PPO/SAC 等训练脚本
│
├── simulation/
│   ├── scenes/                # 工作台、料箱、零件场景
│   ├── assets/                # URDF / mesh / CAD
│   └── randomization/         # 随机摆放、光照、遮挡
│
├── data/
│   ├── samples/               # 示例 RGB-D、mask、任务记录
│   ├── datasets/              # 训练/评测数据
│   └── logs/                  # 执行日志
│
├── docs/
│   ├── zh/                    # 中文留档
│   ├── setup.md
│   └── experiment.md
│
└── tests/
```

## 8. 技术路线

项目按以下顺序推进：

1. **搭建同型号机械臂仿真环境**  
   加载机械臂、夹爪、相机、工作台、料箱和工业零件。

2. **建立 Agent 工作流**  
   完成自然语言输入、任务 JSON 生成、行为树执行和状态反馈。

3. **跑通仿真闭环**  
   实现指令输入到仿真机械臂完成抓取放置的完整流程。

4. **接入开放词汇感知**  
   使用 SAM3 / DINO-X 根据文本提示分割目标物体和目标格子。

5. **融合 RGB-D 三维定位**  
   将 mask、深度图和相机参数转换为机器人坐标系下的 3D 位姿。

6. **迁移真实机械臂**  
   接入 ROS2、MoveIt2、真实相机、夹爪和手眼标定结果。

7. **加入失败恢复能力**  
   通过规则恢复和 RL 局部策略处理抓取失败、放置偏移和遮挡问题。

## 9. 项目创新点

本项目的主要创新点包括：

1. **开放词汇工业感知**  
   使用 SAM3 / DINO-X 支持自然语言驱动的工业零件和料箱格子分割，适应未知类别和新增零件。

2. **RGB-D 三维场景理解**  
   将开放词汇分割结果与深度图结合，生成机器人可执行的 3D 坐标、位姿和空间关系。

3. **VLA 风格任务规划**  
   将自然语言、视觉结果和机器人状态融合为结构化任务图，而不是仅输出文本说明。

4. **行为树执行控制**  
   用行为树组织感知、抓取、放置、验证和恢复流程，使系统可解释、可调试、可展示。

5. **RL 局部失败恢复**  
   针对抓取失败、放置偏移等高频失败场景训练恢复策略，提高系统自主闭环能力。

6. **仿真到真实迁移**  
   通过统一 `RobotExecutor` 接口，使同一套 Agent 工作流同时支持仿真和真实 ROS2 机械臂。

## 10. 最终交付形态

项目最终应交付：

```text
可运行源代码
仿真环境
ROS2 机械臂接口
开放词汇感知模型适配
行为树任务执行系统
失败恢复策略
实验数据与指标
技术报告
使用说明文档
演示视频
```

核心演示场景包括：

```text
自然语言指令输入
→ 识别散乱工业零件
→ 定位目标料箱格子
→ 机械臂抓取目标零件
→ 放置到指定格子
→ 视觉验证结果
→ 失败时自动重试或纠偏
```
