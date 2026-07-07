# SensorAgent 架构

SensorAgent 是具身任务的智能体侧编排仓库。本仓库不负责 Isaac Sim 部署、机器人驱动、ROS 2 启动、MoveIt2 配置或真实机械臂执行；这些能力由其他小组提供，本仓库通过 tools、skills 或 integration adapters 调用。

本仓库关注：

```text
用户 / 多模态输入
→ Agent 规划
→ MCP 风格 skill / tool 调用
→ ActionList 或 DecisionTree 执行
→ 结构化日志
→ 外部系统适配
```

## 职责边界

| 领域 | 本仓库负责 | 本仓库不负责 |
|---|---|---|
| Agent | 规划、工具选择、工作流执行 | 机器人固件、ROS 2 驱动 |
| Skills / tools | schema、注册表、适配器、调用日志 | 底层硬件实现 |
| 视觉 / 音频 | 可选处理工具与服务客户端 | 相机部署与运行时维护 |
| 机械臂控制 | 工具适配器契约 | 机械臂控制栈 |
| 仿真 | 工具适配器契约 | Isaac Sim 场景部署 |
| 日志 | Agent 任务日志、工具调用 trace、工作流记录 | 外部运行时日志 |

## 目标目录

```text
sensoragent/
├── src/
│   └── sensoragent/
│       ├── agent/                  # Agent loop、planner、工具选择
│       ├── mcp/                    # MCP 风格契约、server/client 辅助
│       ├── skills/                 # 可组合高层能力
│       ├── tools/
│       │   ├── vision/             # 视觉处理工具或外部客户端
│       │   ├── audio/              # ASR/TTS/音频工具或外部客户端
│       │   └── robot/              # 机器人控制工具适配器
│       ├── workflows/
│       │   ├── actionlists/        # 顺序执行动作列表
│       │   └── decision_trees/     # 带分支的任务策略
│       ├── logger/                 # Agent 自维护结构化日志
│       ├── state/                  # Agent 状态、任务上下文、事件缓冲
│       ├── integrations/           # 外部小组接口适配
│       ├── schemas/                # 共享 Pydantic/dataclass schema
│       ├── config/                 # 运行时配置加载
│       └── services/
│           ├── api/                # HTTP/WebSocket 服务入口
│           └── cli/                # CLI 入口
├── configs/                        # 项目级配置
├── docs/                           # 架构与团队文档
├── scripts/                        # 项目级启动与维护脚本
└── tests/                          # 单元与集成测试
```

## 核心概念

### Tool

Tool 是最小可调用能力。它需要稳定 schema、清晰输入输出、失败语义和结构化日志。

示例：

```text
vision.detect_object
vision.segment_object
audio.transcribe
audio.speak
robot.pick
robot.place
robot.get_state
```

### Skill

Skill 是由多个 tool 组合而成的高层能力。

示例：

```text
inspect_scene = capture image + detect objects + summarize
pick_and_place = detect target + call robot pick + call robot place + verify
```

### Workflow

Workflow 是针对具体任务的执行策略，可以是简单顺序 ActionList，也可以是带分支、重试与恢复的 DecisionTree。

赛题相关逻辑应放在这里，而不是写进底层工具。

### Logger

Logger 是一等模块。每个任务都应记录：

```text
task id
用户输入
解析结果
选中的 workflow
tool 调用
tool 输入输出
耗时
错误
重试决策
最终状态
```

这些日志用于调试、评测、报告、回放和未来训练数据。

## 初始开发重点

本项目接下来很长一段时间的重点是搭建通用 Agent 框架：

1. MCP 风格 tool / skill 契约。
2. Tool registry 与 skill registry。
3. ActionList runtime。
4. DecisionTree runtime。
5. 结构化 logger。
6. 外部 adapter 模式。
7. 最小 API / CLI 任务入口。

等框架稳定后，再逐步加入具体赛题 workflow。
