# Aether 2607 团队总览

本文是团队级总览文档，用于说明 Aether 2607 这一代系统的总体方向。它不是 SensorAgent 的实现文档，而是 SensorAgent 所属的更大系统背景。

## 1. 版本关系

```text
Radish（2602）
→ Aether（2607）
→ Anima（未来版本）
```

Aether 2607 的目标是把过往项目中分散的机器人能力重新整理为更清晰的具身智能架构。

## 2. 总体架构

团队系统分为两大部分：

```text
GECA：General Embodied Cognition Agent，负责智能体决策侧
ECOS：Embodied Cognition Operating System，负责机器人运行时侧
```

可以简单理解为：

```text
GECA = 大脑
ECOS = 身体
```

GECA 负责任务理解、规划、工具调用、记忆和决策；ECOS 负责感知、运动控制、硬件驱动、仿真桥接和运行时安全。

## 3. 与 SensorAgent 的关系

SensorAgent 是 GECA 侧的一个具体落地仓库，负责：

```text
Agent 框架
MCP / API 协作
skills / tools 编排
ActionList / DecisionTree workflow
结构化日志
外部模块适配
```

SensorAgent 不负责 Isaac Sim 部署、ROS 2 驱动、机械臂底层控制或真实硬件安全。

## 4. 当前测试平台

当前团队测试平台包括：

```text
RealMan RM65-B 机械臂
x30 pro 机器狗 / 移动底盘
Jetson Orin NX
GPU 工作站 / 服务器
NAS 模型与数据存储
```

这些是当前测试资源，不是系统架构的固定绑定。架构目标是让不同机器人或仿真平台通过适配层接入。

## 5. SensorAgent 仓库架构

SensorAgent 的完整职责、运行时结构、ROS 2 仿真边界和目录说明统一维护在
[仓库架构文档](../../architecture.md) 中。其他模块的详细设计由对应仓库维护，
本仓库不再保存副本。

## 6. 项目阶段

当前阶段的重点是：

```text
先明确架构边界
再搭建基础框架
随后针对具体赛题编写 workflow
最后接入外部感知、机械臂、仿真和展示系统
```

对 SensorAgent 来说，近期重点是第一阶段：完善 Agent 架构，而不是直接实现完整机器人闭环。
