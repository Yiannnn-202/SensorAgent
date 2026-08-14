# Phase G1 Gazebo smoke 验证

本验证点用于确认流程内核改动没有破坏当前最稳定的 config-detect sorting baseline。

G1 不验证 live RGB-D，不做批量随机场景，也不要求覆盖所有失败恢复；它只保护稳定基线：

```text
industrial.sorting_config_pick_place_actionlist
单实例 grasp matrix smoke
```

## 1. 启动 Gazebo

在 Ubuntu 22.04 + ROS 2 Humble 环境中：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh \
  world_file:=industrial_sorting_metal_pgs.sdf
```

等待 Gazebo、MoveIt、控制器和 HTTP Bridge 启动后检查：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

`/ready` 中 `move_action`、`execute_trajectory`、`cartesian_path`、`gripper_cmd` 应为 true。

## 2. 先跑 fake smoke

这一步不控制 Gazebo，只确认脚本、配置和 Agent 调用链：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/run_g1_gazebo_smoke.py \
  --json-out logs/tasks/g1_fake_smoke.json
```

期望：

```text
success: true
mode: fake
```

## 3. 运行 G1 Gazebo smoke

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/run_g1_gazebo_smoke.py \
  --execute \
  --json-out logs/tasks/g1_gazebo_smoke.json
```

脚本会执行两个检查：

1. `industrial.sorting_config_pick_place_actionlist`
   - 默认对象：`metal_hex_nut_02`
   - 默认目标：`bin_cell_5`
2. 单实例 grasp matrix smoke
   - 默认实例：`metal_hex_nut_02`
   - 会 reset 场景、stop robot、open gripper、回观察位，然后执行一次抓取。

## 4. 通过标准

`logs/tasks/g1_gazebo_smoke.json` 中：

```json
{
  "success": true,
  "mode": "gazebo"
}
```

同时检查：

- `actionlist.success == true`
- `grasp_matrix_smoke.result.success == true`
- 无模板变量缺失；
- 无 schema validation 错误；
- MoveIt planning / Cartesian / gripper command 没有新增流程层错误。

## 5. 失败时怎么判断

| 失败位置 | 优先判断 |
| --- | --- |
| `/ready` false | ROS/MoveIt/控制器/bridge 没完全启动 |
| actionlist detect/plan 失败 | config 或 workflow 模板问题 |
| actionlist pick/place 失败 | MoveIt 可达性、碰撞、夹爪或场景状态问题 |
| grasp matrix preparation 失败 | robot stop/open/observe 或 Gazebo set_pose 问题 |
| grasp matrix pick 失败 | 单实例抓取可达性或夹持稳定性问题 |

G1 失败不要直接进入 G2/G3；先恢复稳定 baseline。

