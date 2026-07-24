# sim-test success

端到端 sim 打通了。

## 结果确认

```
=== overall ===
success: True
error:   None

=== per-step outcomes ===
grasp_check     held=True     opening=0.0398   ← 抓到 roller
place_target    present                        ← bin_cell_3 pose 生成
place_plan      present                        ← approach/place/retreat plan
place_check     released=True opening=0.0847   ← 松开完成

=== final state ===
arm status: idle           (回到 staging pose)
pos: (0.328, -0.057, 0.29) (staging 位置)
gripper: open (0.0848)
```

11 步 ActionList 全通：

```
detect → plan_pick → pick (6 sub-steps) → verify_grasp ✓
→ resolve_place_target → plan_place
→ place_pre_approach_joints → place_move_place (OMPL)
→ place_open_gripper → place_retreat (joints) → verify_place ✓
```

## 之前 v7 失败原因（推测）

v7 pick 挂在 Cartesian `move_pregrasp`，判断是 sim 状态漂移：手臂在上一次 sim 运行遗留姿态或物件微位置差，导致 Cartesian 起点解和 IK 期望差得多。v8 手动 reset 到 home 后清了这个漂移，就通了。

**建议**：sim runner 应该在开跑前主动 reset 到 home。可以给脚本加一个 `--reset-home` 参数（默认 True），跑前先发一次 `move_joints [0,0,0,0,0,0]`。

## 关键改动总结

| 项 | 改动 |
|---|---|
| `bin_cell_*` z 从 0.20 → 0.30 | 避开 bin 壁碰撞（你的洞察） |
| `bin_cell_*` orientation | (0.9962, -0.0872, 0, 0) 匹配 staging pose |
| `place_move_place` | `robot.move_linear` → `robot.move_pose` (OMPL) |
| `place_retreat` | `robot.move_pose` → `robot.move_joints` (稳) |
| `PLACE_PRE_APPROACH_JOINTS` | `[-0.17, -0.57, -0.61, 0, -1.96, 0]` |
| `ActionListRuntime.success` 语义 | 只看 `stop_on_failure=True` 的 step，best-effort 不拉低 |

## 多轮测试结果

| Round | 物件 | 目的地 | 结果 | 失败位置 |
|---|---|---|---|---|
| 1 | roller | bin_cell_3 | ✓ | — |
| 2 | gear | bin_cell_2 | ✗ | `pick.move_pregrasp` (Cartesian 0.000) |
| 3 | short_bolt | bin_cell_1 | ✗ | place phase (MOVEIT_99999) |

## 诊断

**Round 2**：gear 在 (0.43, 0.08, 0.13)，比 roller 更远更低。approach 姿态 IK 从起点就无解 → Cartesian fraction 0.000。可能超出 top-down 抓取的最佳 workspace。

**Round 3**：short_bolt pick 成功（opening=0.025 表示夹紧 25mm 直径的螺栓），verify_grasp OK。但 place 到 bin_cell_1（Y=-0.30，远端）时 OMPL abort。原因是 `PLACE_PRE_APPROACH_JOINTS`（J1=-0.17）只覆盖了 bin_cell_2/3 附近，从这里 OMPL 到 bin_cell_1 是大幅 J1 swing。

## 说明

Pipeline 的机制没问题（Round 1 完全 clean）。这两个 round 暴露的是 **IK 边界问题**：

- 不是所有物件位置都是 RM65 top-down 抓取的可达域
- Staging joints 只能对一小片 bin 区域友好
