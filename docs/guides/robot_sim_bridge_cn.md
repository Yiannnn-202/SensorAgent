# SensorAgent 仿真机器人 HTTP Bridge 指引

本文说明已实现的 SensorAgent 到 RM65-B + Robotiq 2F-85 仿真控制链路。
Bridge 已接入 Gazebo/MoveIt 测试脚本和工业 ActionList；默认 Python 测试套件
仍不自动启动 ROS 2、Gazebo 或 MoveIt。

## 架构与运行边界

```text
Python 3.12 SensorAgent
└── HttpRobotControlClient
    └── HTTP http://127.0.0.1:8765
        └── Python 3.10 sensoragent_robot_bridge (ROS 2 Humble)
            ├── MoveIt 2：机械臂关节、位姿和直线运动
            └── control_msgs/action/GripperCommand：夹爪
                └── ros2_control / gz_ros2_control
                    └── Gazebo
```

Agent 与 ROS 2 Bridge 是两个独立进程。这个 HTTP 边界避免 Python 3.12
Agent 直接导入 Ubuntu 22.04 ROS 2 Humble 的 Python 3.10 `rclpy`。

## 准备和启动

首次准备工作区，或仿真包更新后执行：

```bash
cd ~/SensorAgent
bash scripts/linux/prepare_rm65_b_sim.sh
```

该脚本会导入上游 RM65-B 包、安装 ROS 依赖，并构建包括
`sensoragent_robot_bridge` 在内的仿真工作区。

启动 Gazebo、MoveIt、RViz 和 HTTP Bridge：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

Bridge 默认延迟启动并监听 `http://127.0.0.1:8765`。如只需启动已有仿真
而不启动 Bridge：

```bash
bash scripts/linux/run_rm65_b_sim.sh start_robot_bridge:=false
```

可通过 launch 参数修改监听地址和端口：

```bash
bash scripts/linux/run_rm65_b_sim.sh \
  robot_bridge_host:=127.0.0.1 \
  robot_bridge_port:=8765
```

## 健康和状态检查

启动完成后，在同一台 Ubuntu 主机上执行：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/state
curl http://127.0.0.1:8765/gripper/state
```

所有接口返回统一 JSON 结构：

```json
{
  "success": true,
  "error_code": "OK",
  "message": "OK",
  "state": {}
}
```

`/health` 只表示 HTTP Bridge 进程正在响应；执行前还应检查 `/ready` 中的
`move_action`、`execute_trajectory`、`cartesian_path` 和 `gripper_cmd`。

## HTTP 接口

| 方法 | 路径 | 主要请求字段 |
| --- | --- | --- |
| `GET` | `/health` | 无 |
| `GET` | `/ready` | 无；返回 MoveIt、笛卡尔路径、夹爪 Action 等就绪状态 |
| `GET` | `/state` | 无；返回机械臂和夹爪状态 |
| `POST` | `/move-joints` | `joints`（6 个弧度值）、`speed`、`wait` |
| `POST` | `/move-pose` | `pose`、`speed`、`wait` |
| `POST` | `/move-linear` | `pose`、`speed`、`wait` |
| `POST` | `/stop` | `{}` |
| `POST` | `/gripper/open` | `opening`、`speed` |
| `POST` | `/gripper/close` | `opening`、`force`、`speed` |
| `GET` | `/gripper/state` | 无 |

当前 Bridge 仅支持阻塞执行，`wait` 必须为 `true`。这样 Agent 的顺序 Skill
可以在每一步得到明确的完成、失败或取消结果，避免后台轨迹与后续动作重叠。

位姿格式如下；位置单位为米，四元数顺序为 `x, y, z, w`：

```json
{
  "pose": {
    "position": [0.3, 0.0, 0.4],
    "orientation": [0.0, 0.0, 0.0, 1.0],
    "frame_id": "base_link"
  },
  "speed": 0.2,
  "wait": true
}
```

关节运动示例：

```bash
curl -X POST http://127.0.0.1:8765/move-joints \
  -H 'Content-Type: application/json' \
  -d '{"joints":[0,0,0,0,0,0],"speed":0.2,"wait":true}'
```

停止当前运动：

```bash
curl -X POST http://127.0.0.1:8765/stop \
  -H 'Content-Type: application/json' \
  -d '{}'
```

## SensorAgent 配置

`configs/robot_sim.yaml` 启用原子机械臂/夹爪 Tools、`robot.pick` /
`robot.place` Skills，并选择 HTTP backend：

```yaml
integrations:
  robot:
    backend: http
    endpoint: http://127.0.0.1:8765
    timeout_seconds: 120.0
```

运行支持配置参数的 SensorAgent 命令时传入：

```text
--config configs/robot_sim.yaml
```

不连接 ROS 2、只验证 Agent 侧行为时使用 `configs/robot_mock.yaml`，它选择
有状态 fake backend。

## 夹爪开度语义

SensorAgent 接口使用物理开度：

- `opening = 0.0848` 米：完全打开；
- `opening = 0` 米：完全闭合。

仿真 `GripperCommand` Action 使用闭合行程：

- `position = 0`：完全打开；
- `position = 0.0848`：完全闭合。

因此 Bridge 必须执行：

```text
closure = 0.0848 - opening
```

`speed` 为保持 backend-neutral Agent 接口兼容而保留，并在 Bridge 入口进行
范围校验；但是 ROS 2 `control_msgs/action/GripperCommand` **没有 speed
字段**，因此夹爪 Action 实际只接收转换后的 `position` 和 `max_effort`，
不会应用该 speed 值。

机械臂关节和位姿规划使用 MoveIt 的速度/加速度缩放。笛卡尔直线轨迹会在
执行前按 `speed` 调整时间、速度和加速度。

## 网络安全

默认监听地址是 `127.0.0.1`，只允许本机访问。Bridge 本身不提供认证或 TLS。
如将 `robot_bridge_host` 改为 `0.0.0.0` 或其他远程可访问地址，必须使用
防火墙、VPN、受控网络或带认证/TLS 的反向代理进行保护，并限制允许调用的
客户端。

## 验收状态

- Windows 环境目前只覆盖 Agent/Bridge 的单元测试和静态检查。
- Ubuntu 22.04 + ROS 2 Humble 上提供 pick、place、工业 ActionList 和 RGB-D
  视觉 ActionList 脚本，用于手动验收 SensorAgent → HTTP → MoveIt /
  GripperCommand → Gazebo 链路。
- 自动化 ROS 2/Gazebo 验收测试尚未进入默认 Python 测试套件。
- 物理机器人尚未连接。
