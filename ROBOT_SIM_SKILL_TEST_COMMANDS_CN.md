# Ubuntu 仿真环境 Robot Skill 测试命令

本文记录在 Ubuntu 22.04 + ROS 2 Humble 仿真环境中测试 SensorAgent 机器人规划 Tool 和 `robot.pick` Skill 的可复制命令。

## 1. 启动仿真与 Bridge

第一个终端：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

新开第二个终端，检查 Bridge：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/state
curl http://127.0.0.1:8765/gripper/state
```

## 2. 首次准备 Python 3.12 环境

如果 Ubuntu 没有 conda，也没有 `python` 命令，直接使用 Python 3.12 venv：

```bash
sudo apt update
sudo apt install -y software-properties-common curl

sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev

cd ~/SensorAgent
python3.12 -m venv .venv312
source .venv312/bin/activate

python -m pip install -U pip
python -m pip install -r requirements.txt
export PYTHONPATH=$PWD/src
```

以后重新开终端只需要：

```bash
cd ~/SensorAgent
source .venv312/bin/activate
export PYTHONPATH=$PWD/src
```

## 3. 测试规划 Tool + robot.pick Skill

复制下面整段到已经激活 `.venv312` 的终端中执行：

```bash
python - <<'PY'
from pathlib import Path
from sensoragent.agent import build_agent_from_config
from sensoragent.schemas import TraceContext

bundle = build_agent_from_config(Path("configs/robot_sim.yaml"))
trace = TraceContext()

grasp_pose = {
    "position": [0.35, 0.0, 0.35],
    "orientation": [0.0, 1.0, 0.0, 0.0],
    "frame_id": "base_link",
}

plan_result = bundle.tool_runtime.invoke(
    "robot.plan_top_down_pick",
    {
        "grasp_pose": grasp_pose,
        "approach_distance": 0.10,
        "pregrasp_distance": 0.03,
        "lift_height": 0.10,
    },
    trace,
)

print("PLAN RESULT:")
print(plan_result)

if not plan_result.success:
    raise SystemExit(1)

pick_result = bundle.skill_runtime.invoke(
    "robot.pick",
    {
        "object_id": "test_object",
        "plan": plan_result.output["plan"],
        "close_opening": 0.02,
        "speed": 0.2,
    },
    trace,
)

print("PICK RESULT:")
print(pick_result)
PY
```

## 4. 单独测试点云定向抓取规划

这段不依赖真实相机，用假点云验证 `robot.plan_oriented_pick` 是否能生成 `PickPlan`：

```bash
python - <<'PY'
from pathlib import Path
from sensoragent.agent import build_agent_from_config
from sensoragent.schemas import TraceContext

bundle = build_agent_from_config(Path("configs/robot_sim.yaml"))
trace = TraceContext()

points = []
for i in range(-20, 21):
    y = i * 0.01
    radius = 0.03 if y >= 0 else 0.01
    points += [
        [0.35 + radius, y, 0.30],
        [0.35 - radius, y, 0.30],
        [0.35, y, 0.30 + radius],
        [0.35, y, 0.30 - radius],
    ]

plan_result = bundle.tool_runtime.invoke(
    "robot.plan_oriented_pick",
    {
        "points": points,
        "frame_id": "base_link",
        "approach_distance": 0.10,
        "pregrasp_distance": 0.03,
        "lift_height": 0.10,
    },
    trace,
)

print("ORIENTED PICK PLAN RESULT:")
print(plan_result)
PY
```

## 5. 常见问题

| 报错/现象 | 处理 |
| --- | --- |
| `ImportError: cannot import name 'UTC' from 'datetime'` | 用的是 Python 3.10；请激活 `.venv312` 后再运行 |
| `ROBOT_BRIDGE_UNAVAILABLE` | 仿真 Bridge 没启动，检查 `curl http://127.0.0.1:8765/health` |
| `Unknown tool: robot.plan_top_down_pick` | Ubuntu 上代码不是最新，或没有使用最新 `configs/robot_sim.yaml` |
| `No module named numpy` | 在 `.venv312` 中执行 `python -m pip install -r requirements.txt` |
| MoveIt planning failed | 目标位姿不可达或姿态不合适，先换一个 RViz 中确认可达的位姿 |
