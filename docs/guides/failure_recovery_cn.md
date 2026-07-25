# 失败检测与局部重新规划方案

本文说明 SensorAgent 当前实现的失败检测与恢复规划基础设施。目标是支撑赛题
“摆放失败后自主感知、重新处理”的评分点，并为后续 DecisionTree 恢复分支、
批量实验和演示视频提供统一证据格式。

## 1. 当前实现范围

已实现：

- `sensoragent.recovery`：失败类型、失败证据、失败分类和恢复计划数据结构；
- `FailureDetector`：按错误码、失败步骤、验证输出和视觉证据进行归因；
- `RecoveryPlanner`：按失败类型输出确定性局部恢复策略；
- `recovery.classify_failure` Tool：把 workflow/tool/skill 失败证据转成
  `failure_type`、`phase`、`retryable` 和 `recommended_strategy`；
- `recovery.plan` Tool：把分类结果转成有界恢复计划；
- `vision.verify_object_lifted` Tool：比较抓取前后物体位姿，检测空抓或掉落；
- `vision.verify_object_in_bin` Tool：判断物体是否在目标格附近，检测放错格；
- `DecisionTreeRuntime.last_failure`：任一节点失败后，失败证据进入上下文，
  后续节点可直接调用 `recovery.classify_failure`。

尚未完成：

- 完整 `industrial.recovery_pick_place_tree` 自动执行所有恢复动作；
- Gazebo 中的动态场景 reset 和重新拍摄闭环；
- 实机视觉验证与标定后的 wrong-bin 检测。

## 2. 失败证据格式

失败检测统一接收 `FailureEvidence` 形状：

```json
{
  "failed_step": "verify_object_in_bin",
  "target": "vision.verify_object_in_bin",
  "phase": "place",
  "error": "WRONG_BIN: object is outside the requested target cell",
  "output": {
    "in_target": false,
    "distance_xy": 0.20
  },
  "observed": {},
  "expected": {},
  "attempt": 1,
  "max_attempts": 2
}
```

DecisionTree 节点失败时，runtime 自动写入：

```text
last_failure
```

因此失败分支可以这样调用：

```text
recovery.classify_failure
  input: {"evidence": "{{ last_failure }}"}
```

## 3. 失败类型

当前分类覆盖：

| 类型 | 阶段 | 默认恢复策略 |
| --- | --- | --- |
| `OBJECT_NOT_FOUND` | perception | 重新感知 |
| `LOW_CONFIDENCE` | perception | 重新采样 RGB-D，扩大视觉窗口 |
| `POSE_INVALID` | perception | 重新采样深度和位姿 |
| `TARGET_NOT_FOUND` | planning | 快速失败，要求修正目标 |
| `ROBOT_NOT_READY` | robot | 检查 `/ready`，stop/reset 后再规划 |
| `BRIDGE_ERROR` | robot | stop、健康检查、reset home |
| `PICK_PLAN_FAILED` | pick | top-down 切换到 oriented pick，增加 clearance |
| `PICK_EXEC_FAILED` | pick | 回 staging，重新检测并重规划 pick |
| `GRASP_EMPTY` | pick | 重新检测，调整 TCP offset 和夹爪闭合量 |
| `DROPPED_OBJECT` | transport | 以掉落后的观测位姿作为新 pick target |
| `PLACE_PLAN_FAILED` | place | 生成目标格附近候选 release pose |
| `PLACE_EXEC_FAILED` | place | 回 place staging，增加 clearance 后重规划 |
| `RELEASE_FAILED` | place | 保守速度重试 gripper open |
| `WRONG_BIN` | place | 从观测错误位置重新抓取并放到目标格 |
| `VISION_MODEL_NOT_READY` | perception | 快速失败，补模型权重 |
| `VISION_BACKEND_UNAVAILABLE` | perception | 快速失败，补可选依赖 |

## 4. 恢复计划输出

`recovery.plan` 输出 `RecoveryPlan`：

```json
{
  "strategy": "retry_place_candidates",
  "failure_type": "PLACE_PLAN_FAILED",
  "retryable": true,
  "next_step": "plan_place",
  "max_attempts": 2,
  "updated_input": {
    "place_candidate_offsets": [
      [0.0, 0.0, 0.03],
      [-0.04, 0.0, 0.04],
      [0.04, 0.0, 0.04],
      [0.0, 0.04, 0.04],
      [0.0, -0.04, 0.04]
    ],
    "clearance_delta": 0.05
  },
  "notes": [
    "Try nearby release poses and slightly higher clearance before giving up."
  ]
}
```

恢复计划只给出受约束的局部重规划建议，不允许 LLM 直接输出任意机器人动作。
后续 DecisionTree 恢复分支应根据 `strategy` 进入固定节点。

## 5. 视觉验证工具

### `vision.verify_object_lifted`

用途：抓取后比较 `before_pose` 和 `after_pose/current_pose`。

成功条件：

```text
after.z - before.z >= min_lift_delta
xy_drift <= max_xy_drift
```

失败时返回：

```text
DROPPED_OBJECT
```

### `vision.verify_object_in_bin`

用途：放置后判断物体位置是否接近目标格 release pose。

成功条件：

```text
distance_xy <= tolerance_xy
z_error <= max_z_error
```

失败时返回：

```text
WRONG_BIN
```

当前版本用目标格中心近似判断，后续实机阶段应替换为料箱格多边形/占用区域判断。

## 6. 推荐后续落地顺序

1. 把 `industrial.pick_place_actionlist` 升级为 `industrial.recovery_pick_place_tree`；
2. 在每个失败分支中调用 `recovery.classify_failure` 和 `recovery.plan`；
3. 先实现 4 条恢复执行分支：`GRASP_EMPTY`、`PICK_PLAN_FAILED`、
   `PLACE_PLAN_FAILED`、`WRONG_BIN`；
4. 为每条分支写 failure-injection 测试；
5. 在 Gazebo 中录制“故意放错格 → 视觉发现 → 重新抓取 → 正确入格”的视频；
6. 批量统计失败检测准确率、恢复后成功率、恢复收益和平均恢复代价。

## 7. 测试命令

```powershell
$env:PYTHONPATH = "$(Get-Location)\src"
python -m unittest tests.unit.test_failure_recovery
```
