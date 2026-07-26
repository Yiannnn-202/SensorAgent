# Gazebo 失败恢复演示

本文说明如何在 Gazebo 中演示 SensorAgent 的失败检测与恢复能力。推荐视频演示
使用 `wrong-bin` 模式：系统第一次故意把物体放到错误格，随后检测到
`WRONG_BIN`，进入恢复树重新抓取并放入正确格。

## 1. 演示脚本

```text
scripts/linux/run_gazebo_recovery_demo.py
```

脚本运行：

```text
industrial.recovery_pick_place_tree
```

并支持确定性故障注入：

| 模式 | 故障 | 恢复路径 |
| --- | --- | --- |
| `wrong-bin` | 首次 `robot.resolve_place_target` 返回错误目标格位姿，实际执行一次错误放置 | `WRONG_BIN` → `recover_pick` → 重新放入正确格 |
| `place-plan` | 首次 `robot.plan_place` 返回 `PLACE_PLAN_FAILED` | `PLACE_PLAN_FAILED` → `recover_place` |
| `release` | 首次 `gripper.open` 返回 `RELEASE_FAILED` | `RELEASE_FAILED` → `recover_release` |
| `none` | 不注入故障 | 正常恢复树主流程 |

## 2. 启动 Gazebo

在 Ubuntu 22.04 + ROS 2 Humble 主机上：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

另一个终端确认 bridge 和 ROS 接口：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

`/ready` 中至少应看到：

```text
move_action
execute_trajectory
cartesian_path
gripper_cmd
```

均为 `true`。

## 3. 推荐录制命令：放错格后恢复

```bash
cd ~/SensorAgent
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure wrong-bin \
  --object-query roller \
  --target bin_cell_3 \
  --wrong-target bin_cell_2 \
  --execute \
  --json-out logs/tasks/recovery_wrong_bin_demo.json
```

预期行为：

1. 机器人从当前工业场景中抓取 `roller`；
2. 首次放置被故障注入改到 `bin_cell_2`；
3. `vision.verify_object_in_bin` 使用目标 `bin_cell_3` 验证时失败；
4. `recovery.classify_failure` 分类为 `WRONG_BIN`；
5. `recovery.plan` 输出 `repick_from_observed_pose`；
6. 恢复树进入 `recover_pick`，从错误格位姿重新抓取；
7. 后续 `robot.resolve_place_target` 恢复为 `bin_cell_3`；
8. 机器人重新放置并通过目标格验证。

视频中建议同时拍摄：

- Gazebo 画面；
- 终端输出中的 `classification.failure_type=WRONG_BIN`；
- `recovery.strategy=repick_from_observed_pose`；
- 最终 `success=true`。

## 4. 不移动机器人 dry run

不加 `--execute` 时，脚本会把 robot backend 切成 fake，用于确认恢复树和输出：

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure wrong-bin \
  --object-query roller \
  --target bin_cell_3 \
  --wrong-target bin_cell_2 \
  --json-out logs/tasks/recovery_wrong_bin_dry_run.json
```

检查输出：

```bash
python - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("logs/tasks/recovery_wrong_bin_dry_run.json").read_text())
print(data["success"])
print(data["classification"]["failure_type"])
print(data["recovery"]["strategy"])
print([node["node"] for node in data["nodes"]])
PY
```

应看到：

```text
True
WRONG_BIN
repick_from_observed_pose
```

## 5. 其他故障模式

### Place planning failure

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure place-plan \
  --object-query roller \
  --target bin_cell_3 \
  --execute \
  --json-out logs/tasks/recovery_place_plan_demo.json
```

用于展示：

```text
PLACE_PLAN_FAILED → retry_place_candidates / recover_place
```

### Gripper release failure

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure release \
  --object-query roller \
  --target bin_cell_3 \
  --execute \
  --json-out logs/tasks/recovery_release_demo.json
```

用于展示：

```text
RELEASE_FAILED → retry_open_gripper / recover_release
```

## 6. 输出文件

`--json-out` 保存报告可用的结构：

```json
{
  "success": true,
  "failure_injection": {},
  "classification": {},
  "recovery": {},
  "bin_check": {},
  "last_failure": {},
  "nodes": []
}
```

其中：

- `classification.failure_type`：失败类型；
- `recovery.strategy`：恢复策略；
- `nodes`：完整 DecisionTree 节点执行轨迹；
- `bin_check`：目标格验证结果。

## 7. 当前边界

- `wrong-bin` 模式使用故障注入让首次目标格解析成错误格，并使用注入位姿作为恢复
  阶段的“观测位姿”。它适合演示恢复树闭环，但还不是完全基于重新拍摄的真实视觉
  wrong-bin 检测。
- 真正视觉闭环需要在放置后重新捕获 RGB-D 帧，并用
  `vision.open_vocab_detect` 或后续 verifier 判断物体是否在目标格。
- 每轮 Gazebo 演示后，建议重启仿真或手动复位物体，避免上一次放置结果影响下一次。
