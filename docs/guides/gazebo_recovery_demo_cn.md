# Gazebo 失败恢复演示

本文说明如何在 Gazebo 中演示 SensorAgent 的失败检测与恢复能力。推荐视频演示
使用 `wrong-table` 模式：系统第一次故意把物体放到桌面上的错误位置，随后检测到
`WRONG_BIN`，进入恢复树后重新采集 RGB-D 图像，并通过 YOLOE
(`vision.open_vocab_detect`) 重新定位桌面上的 block 抓取点，再放入正确目标区。这个模式
比从 bin 内重新抓取更容易，因为桌面位姿没有 bin 壁碰撞约束。

当前 Gazebo 场景只保留一个稳定 `block`，并把原来的 3x3 盒子替换成桌面上的 2x2
平面目标区：`target_area_1` 到 `target_area_4`。彩色区域是视觉标记，白色边界线是
低矮实体碰撞条（约 6-8 mm 厚）。桌面碰撞面使用高摩擦系数。

工作台尺寸为 `0.5 x 0.75 m`，桌面大约覆盖 base_link
`x=[0.09,0.59]`、`y=[-0.375,0.375]`。演示用的 block 和 2x2 目标区放在靠近机械臂的
可达中心区域内，用于降低恢复抓取难度。

四个目标区放在这个可达桌面范围内，中心点为：
`target_area_1=[0.24,-0.10]`、`target_area_2=[0.40,-0.10]`、
`target_area_3=[0.24,0.04]`、`target_area_4=[0.40,0.04]`（单位 m，base_link）。
`wrong-table` 故障会把物体放到靠近起始方块位置的中性桌面区域 `[0.28,0.22]` 附近，
并用适中的释放高度做“轻放”，避免夹爪压桌；默认目标为
`target_area_3`。

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
| `wrong-table` | 首次 `robot.resolve_place_target` 返回一个可达桌面位姿，实际执行一次桌面错误放置 | `WRONG_BIN` → YOLOE 重新定位 → `recover_pick` → 重新放入正确格 |
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

## 3. 推荐录制命令：放到桌面错误位置后恢复

```bash
cd ~/SensorAgent
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure wrong-table \
  --object-query block \
  --target target_area_3 \
  --execute \
  --json-out logs/tasks/recovery_wrong_table_demo.json
```

预期行为：

1. 机器人从当前工业场景中抓取 `block`；
2. 首次放置被故障注入改到桌面上的可达错误位置；
3. `vision.verify_object_in_bin` 使用目标 `target_area_3` 验证时失败；
4. `recovery.classify_failure` 分类为 `WRONG_BIN`；
5. `recovery.plan` 输出 `repick_from_observed_pose`；
6. 脚本采集一帧新的 Gazebo RGB-D 图像，并调用 YOLOE 重新定位桌面上的 `block`
   （会按 `block`、`red block`、`cube`、`box`、`industrial part`
   等提示词和较低阈值重试）；
7. 恢复树进入 `recover_pick`，使用 YOLOE 返回的 `pose_3d` 重新抓取；
   脚本会对 YOLOE 深度点使用较小但安全的 Z 偏移（2 cm），避免按配置位姿的 3 cm
   偏移抓空，同时减少夹爪压入桌面的风险；
8. 后续 `robot.resolve_place_target` 恢复为 `target_area_3`；
9. 机器人重新放置后，先保持夹爪朝向不变做一段约 8 cm 的严格竖直 Cartesian 抬升；
   只有夹爪已经离开方块接触范围后，才执行后续普通 MoveIt/关节退回；
10. 最后通过目标格验证。

视频中建议同时拍摄：

- Gazebo 画面；
- 终端输出中的 `classification.failure_type=WRONG_BIN`；
- `recovery.strategy=repick_from_observed_pose`；
- 最终 `success=true`。

## 4. 不移动机器人 dry run

不加 `--execute` 时，脚本会把 robot backend 切成 fake，用于确认恢复树和输出：

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure wrong-table \
  --object-query block \
  --target target_area_3 \
  --json-out logs/tasks/recovery_wrong_table_dry_run.json
```

检查输出：

```bash
python - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("logs/tasks/recovery_wrong_table_dry_run.json").read_text())
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

### Wrong bin recovery（更难）

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure wrong-bin \
  --object-query block \
  --target target_area_3 \
  --wrong-target target_area_2 \
  --execute \
  --json-out logs/tasks/recovery_wrong_bin_demo.json
```

用于展示从错误目标区重新抓取。旧的 `bin_cell_1` 到 `bin_cell_4` 名称仍作为别名保留，
但推荐使用 `target_area_*`。

### Place planning failure

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_gazebo_recovery_demo.py \
  --failure place-plan \
  --object-query block \
  --target target_area_3 \
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
  --object-query block \
  --target target_area_3 \
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
- `wrong-table` 模式同样使用故障注入和可控观测位姿，但位姿在桌面上，适合优先验证
  恢复树和重抓取动作。执行模式下，恢复重检测必须使用配置中的 `yoloe` 后端；如果
  YOLOE 未返回 `pose_3d`，脚本会显式失败，而不是继续使用注入位姿。
- 真正视觉闭环需要在放置后重新捕获 RGB-D 帧，并用
  `vision.open_vocab_detect` 或后续 verifier 判断物体是否在目标格。
- 每轮 Gazebo 演示后，建议重启仿真或手动复位物体，避免上一次放置结果影响下一次。
