# 配置

SensorAgent 使用 YAML 配置文件决定某次运行时 Agent 应该如何装配。

配置负责控制：

```text
启用哪些 tools
启用哪些 skills
默认 skill 是什么
日志写到哪里
当前运行环境是什么
```

## 默认 mock 配置

当前第一份配置文件是：

```text
configs/mock.yaml
```

它启用 Phase 1 本地 mock 链路需要的 mock tools 和 mock skill：

```yaml
agent:
  name: sensoragent
  mode: mock
  default_skill: mock.pick_and_place

tools:
  enabled:
    - vision.mock_detect
    - audio.mock_transcribe
    - robot.mock_pick
    - robot.mock_place

skills:
  enabled:
    - mock.pick_and_place
```

## 配置路径解析顺序

SensorAgent 按以下优先级决定加载哪份配置：

```text
1. 代码或 CLI 显式传入的路径
2. SENSORAGENT_CONFIG
3. SENSORAGENT_ENV 映射到 configs/<env>.yaml
4. configs/mock.yaml
```

示例：

```bash
SENSORAGENT_CONFIG=configs/dev.yaml
```

```bash
SENSORAGENT_ENV=mock
```

`SENSORAGENT_ENV=mock` 会映射到：

```text
configs/mock.yaml
```

`SENSORAGENT_ENV=competition` 会映射到：

```text
configs/competition.yaml
```

## 为什么需要配置

Agent 框架不应该把启用哪些 tools 和 skills 写死在代码里。不同环境应该通过配置装配：

```text
mock：全部使用本地 mock tools
dev：混合 mock 与真实服务 adapter
competition：使用真实视觉、音频、机器人工具
```

代码路径保持一致，只切换配置。

## 当前实现位置

配置代码位于：

```text
src/sensoragent/config/
├── env.py       # 根据显式路径或环境变量解析配置路径
├── loader.py    # 把 YAML 读取成类型化配置对象
└── schema.py    # dataclass 配置 schema
```

运行时装配代码位于：

```text
src/sensoragent/agent/bootstrap.py
```

主要辅助函数：

```python
load_config("configs/mock.yaml")
build_agent_from_config("configs/mock.yaml")
build_agent_from_env()
```
