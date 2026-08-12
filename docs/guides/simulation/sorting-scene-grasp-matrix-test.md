# 金属分拣场景逐件抓取测试

本测试用于验证 `industrial_sorting_metal_pgs.sdf` 中 9 个零件是否均在
RM65-B 的可达范围内，并检查 Robotiq 2F-85 能否完成下降、夹紧和提升。
测试直接使用配置坐标，不依赖 ASR、LLM 或视觉模型，因此结果主要反映
MoveIt 规划、机械臂可达性、夹爪和 Gazebo 接触物理。

## 测试对象

```text
metal_roller_01        metal_hex_nut_01        metal_short_bolt_01
metal_roller_02        metal_hex_nut_02        metal_short_bolt_02
metal_roller_03        metal_hex_nut_03        metal_short_bolt_03
```

每轮开始前，脚本会停止当前运动、张开夹爪、回到观察关节位，并通过
Gazebo `set_pose` 服务恢复全部 9 个零件的标准位姿。随后只抓取本轮目标，
提升后读取夹爪状态进行验证。下一轮复位场景，因此不会沿用上一轮碰乱的
零件位置。

## 启动仿真

在 Ubuntu 22.04 + ROS 2 Humble 环境中：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh \
  world_file:=industrial_sorting_metal_pgs.sdf
```

等待 Gazebo、MoveIt、控制器和 HTTP Bridge 完全启动。可以先检查：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

## 先做离线烟测

不加 `--execute` 时使用 fake robot，不会控制 Gazebo：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/test_sorting_scene_grasp_matrix.py
```

该命令只能验证脚本、配置和 Agent 调用链，不能证明机械臂真实可达。

## 测试一个实例

建议先从中间位置开始：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/test_sorting_scene_grasp_matrix.py \
  --execute \
  --instance metal_hex_nut_02
```

确认动作方向、抓取高度和场景复位正确后，再测试边缘位置：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/test_sorting_scene_grasp_matrix.py \
  --execute \
  --instance metal_roller_03
```

## 测试全部实例

单轮测试：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/test_sorting_scene_grasp_matrix.py \
  --execute
```

正式验收建议每件重复 3 次，共执行 27 次：

```bash
PYTHONPATH=src .venv312/bin/python \
  scripts/linux/test_sorting_scene_grasp_matrix.py \
  --execute \
  --repeat 3 \
  --json-out logs/tasks/sorting_grasp_matrix_acceptance.json
```

默认遇到失败会记录错误并继续测试其他实例。调试单个失败时可增加
`--stop-on-failure`。

## 结果说明

终端每轮输出一行摘要：

```json
{"instance_id":"metal_roller_01","attempt":1,"success":true}
```

详细 JSON 报告保存在 `logs/tasks/`，包括：

- 场景准备和复位结果；
- 配置坐标解析结果；
- approach、pregrasp、grasp、lift 规划点；
- `robot.pick` 每个原子步骤的结果；
- 夹爪验证开度；
- 最终机器人状态和失败阶段。

常见失败阶段：

| 阶段 | 含义 |
| --- | --- |
| `resolve_config_pose` | 配置中缺少该实例或抓取参数 |
| `plan_pick_waypoints` | Agent 未能生成合法抓取路点 |
| `pick_and_lift` | MoveIt 规划、运动、夹爪或提升失败 |
| `verify_grasp` | 动作完成，但夹爪状态未确认持有物体 |

脚本中的 `plan_pick_waypoints` 只是生成几何路点；真正的 MoveIt 可达性在
`pick_and_lift` 执行阶段验证。Windows 下只能运行 fake 烟测和静态测试，
最终结论必须以 Ubuntu/Gazebo 的实际执行报告和画面为准。

## 建议验收标准

- 9 个实例均至少成功一次；
- 每个实例 3 次中至少成功 2 次；
- 规划失败与夹持失败分别统计；
- 无工作台、相机架和邻近零件碰撞；
- 测试结束后机械臂回到观察位、夹爪张开、场景恢复标准布局。
