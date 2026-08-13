# 第一步修改方案：让恢复策略真实影响后续执行

## 背景

当前流程里 `recovery.plan` 已经能根据失败类型输出 `updated_input`，例如：

- `RETRY_WITH_EXPANDED_VISION`：`recapture_frame`、`depth_window_delta`、`min_confidence_delta`
- `RETRY_PICK_ORIENTED`：`pick_planner: robot.plan_oriented_pick`、`approach_distance_delta`、`position_offset_delta`
- `RETRY_PICK_ADJUSTED_GRASP`：`close_opening_delta`、`position_offset_candidates`
- `RETRY_PLACE_CANDIDATES`：`place_candidate_offsets`、`clearance_delta`
- `REPICK_FROM_OBSERVED_POSE`：`use_observed_pose_as_new_pick_target`

但这些字段目前大多只是进入日志和 `result.output["recovery"]`，没有真正改变后续 detect / plan_pick / pick / plan_place / place 的输入。

第一步目标是把这件事补上：**恢复策略不仅被记录，还要进入后续节点输入。**

## 不修改范围

明确不改：

- `src\sensoragent\workflows\actionlists\sorting_config.py`
- `industrial.sorting_config_pick_place_actionlist`

它继续作为稳定基线，用于当前已跑通的 config-detect sorting workflow。

第一步只动恢复树相关能力：

- `industrial.recovery_pick_place_tree`
- `industrial.pick_only_actionlist`
- `industrial.place_only_actionlist`
- `DecisionTreeRuntime`
- `RecoveryPlanner`
- 相关测试

## 总体原则

1. **默认行为不变**：没有 recovery 时，所有节点输入和当前一致。
2. **恢复后才覆盖**：只有 `recovery.plan` 成功后，才把 recovery overrides 写入 context。
3. **覆盖可追踪**：每次覆盖都写入 `recovery_history` 或 `recovery_applied_overrides`，方便报告和调试。
4. **先做可验证闭环，不追求一步到位**：第一版优先覆盖最容易验收的输入变化，再逐步接入 oriented pick / observed pose。

## 设计方案

### 1. 在 DecisionTreeRuntime 增加通用 node input override 机制

新增 context 字段：

```python
context["node_input_overrides"] = {
  "recover_redetect": {...},
  "plan_pick": {...},
  "pick": {...},
  "plan_place": {...},
  "recover_pick": {...},
  "recover_place": {...}
}
```

执行任意可调用节点前：

1. 先按原逻辑渲染 `node.input`。
2. 再读取 `context["node_input_overrides"]`。
3. 按优先级合并：

```text
base rendered input
-> overrides by node.target
-> overrides by node.name
```

例如：

```python
node.name == "plan_pick"
node.target == "robot.plan_top_down_pick"
```

则可以同时匹配：

```python
node_input_overrides["robot.plan_top_down_pick"]
node_input_overrides["plan_pick"]
```

节点名 override 优先级更高。

这样做的好处：

- 不把 recovery 专有逻辑硬塞进所有 workflow。
- 后续多 Agent / batch workflow 也能复用。
- 默认没有 overrides 时完全不影响旧流程。

### 2. 扩展 RecoveryPlan 输出结构

当前 `RecoveryPlan` 只有：

```python
updated_input: dict
```

建议保留它，新增派生字段：

```python
node_overrides: dict[str, dict]
```

兼容策略：

- `updated_input` 保持原样，用于报告和语义解释。
- `node_overrides` 是运行时真正消费的具体节点输入覆盖。

示例：

```json
{
  "strategy": "retry_pick_adjusted_grasp",
  "updated_input": {
    "close_opening_delta": -0.005,
    "position_offset_candidates": [[0.0, 0.0, 0.02], [0.0, 0.0, 0.035]]
  },
  "node_overrides": {
    "plan_pick": {
      "position_offset": [0.0, 0.0, 0.035]
    },
    "pick": {
      "close_opening": 0.027
    }
  }
}
```

如果不想立刻改 dataclass，也可以第一版先让 `updated_input` 中包含保留键：

```python
updated_input["_node_overrides"] = {...}
```

但长期建议独立字段更清晰。

### 3. 在 recovery.plan 成功后写入 context

当前 `DecisionTreeRuntime` 在 `node.target == "recovery.plan"` 后只回填 history：

```python
history[-1]["strategy"] = recovery_plan.get("strategy")
history[-1]["next_step"] = recovery_plan.get("next_step")
```

第一步应增加：

```python
node_overrides = recovery_plan.get("node_overrides") or {}
context["node_input_overrides"] = deep_merge(
  context.get("node_input_overrides", {}),
  node_overrides,
)
context.setdefault("recovery_applied_overrides", []).append({
  "attempt": recovery_attempts,
  "strategy": recovery_plan.get("strategy"),
  "node_overrides": node_overrides,
})
```

并把 `node_overrides` 同步写到 `recovery_history[-1]`。

### 4. 第一版优先落地的恢复策略

第一版建议先实现 4 类低风险、容易测试的策略：

#### 4.1 `RETRY_WITH_EXPANDED_VISION`

目标：影响下一次 detect。

建议 override：

```json
{
  "recover_redetect": {
    "depth_window": 11
  }
}
```

如果后续接入阈值，可加入：

```json
{
  "box_threshold": 0.30,
  "text_threshold": 0.20
}
```

注意：不要修改普通 `detect_object`，只覆盖恢复分支 `recover_redetect`。

#### 4.2 `RETRY_PICK_ADJUSTED_GRASP`

目标：影响下一次 pick-only recovery。

建议先选择第一个候选：

```json
{
  "recover_pick": {
    "position_offset": [0.0, 0.0, 0.035],
    "close_opening": 0.027
  }
}
```

这里需要同步调整 `industrial.pick_only_actionlist`，让它接受可选输入：

- `position_offset`
- `close_opening`
- `grasp_orientation`
- `pregrasp_distance`
- `lift_height`

默认值保持原常量，因此不影响旧调用。

#### 4.3 `RETRY_PLACE_CANDIDATES`

目标：影响下一次 place-only recovery。

第一版先不做完整候选循环，只用第一个 candidate offset：

```json
{
  "recover_place": {
    "place_offset": [0.0, 0.0, 0.03],
    "clearance": 0.13
  }
}
```

需要让 `industrial.place_only_actionlist` 支持可选：

- `place_offset`
- `clearance`

默认值保持原常量。

#### 4.4 `RETRY_OPEN_GRIPPER`

目标：影响 `recover_release`。

当前 `recover_release` 已经用了固定低速：

```python
"opening": GRIPPER_OPEN_OPENING,
"speed": 0.3
```

第一版只需要把它改成可被 override：

```json
{
  "recover_release": {
    "opening": 0.0848,
    "speed": 0.3
  }
}
```

### 5. 第二版再处理的策略

这些更复杂，第一步只保留设计，不建议马上实现：

#### 5.1 `RETRY_PICK_ORIENTED`

原因：

- `robot.plan_oriented_pick` 需要 base-frame point cloud。
- 当前视觉链路还没有稳定输出 `points`。

第一版行为：

- 如果没有 `object.points` / `object_point_cloud`，不要强行切换。
- 在 recovery history 里记录：

```json
{
  "oriented_pick_requested": true,
  "oriented_pick_applied": false,
  "reason": "missing_base_frame_object_points"
}
```

第二版再打通：

```text
mask + depth + camera_info + T_base_camera -> object point cloud -> robot.plan_oriented_pick
```

#### 5.2 `REPICK_FROM_OBSERVED_POSE`

原因：

- 需要 world state 或 live verification 产出错误格/掉落位置。
- 当前 deterministic verify 有时使用 commanded pose，不一定是真实观测。

第一版行为：

- 如果 `observed_object.pose_3d` 存在，则覆盖 `object.pose_3d`。
- 否则记录未应用原因。

## 需要改的文件

### 必改

1. `src\sensoragent\workflows\decision_trees\runtime.py`
   - 增加 node input override 合并。
   - 在 `recovery.plan` 成功后写入 `context["node_input_overrides"]`。

2. `src\sensoragent\recovery\failures.py`
   - 给 `RecoveryPlan` 增加 `node_overrides` 字段。
   - `to_dict()` 输出该字段。

3. `src\sensoragent\recovery\planner.py`
   - 为低风险策略生成 `node_overrides`。

4. `src\sensoragent\workflows\actionlists\industrial.py`
   - 只改 `build_industrial_pick_only_actionlist` 和 `build_industrial_place_only_actionlist` 的可选参数。
   - 不改 `sorting_config_pick_place_actionlist`。

5. `contracts\tools\recovery.plan.schema.json`
   - 增加 `node_overrides` 输出字段。

### 测试

1. `tests\unit\test_industrial_recovery_tree.py`
   - 新增 recovery override 是否改变后续输入的测试。

2. `tests\unit\test_failure_recovery.py`
   - 新增 `RecoveryPlanner` 产出 `node_overrides` 的单测。

3. `tests\unit\test_industrial_actionlist.py`
   - 确认 pick-only / place-only 新增可选参数不破坏默认行为。

## 关键测试用例

### 1. 默认 nominal 不变

输入：

```python
build_industrial_recovery_pick_place_tree()
```

无故障运行。

断言：

- `plan_pick` 输入仍是原始 `PICK_POSITION_OFFSET`。
- `pick` 输入仍是原始 `GRIPPER_CLOSE_OPENING`。
- 没有 `node_input_overrides`。

### 2. GRASP_EMPTY 后调整抓取参数

注入：

```text
verify_grasp -> failure
```

断言：

- `recovery.strategy == retry_pick_adjusted_grasp`
- `recovery.node_overrides["recover_pick"]` 存在。
- `recover_pick` 内部调用的 `robot.plan_top_down_pick` 使用新的 `position_offset`。
- `robot.pick` 使用新的 `close_opening`。

### 3. LOW_CONFIDENCE 后扩大视觉输入

注入：

```text
vision.config_detect / vision.open_vocab_detect -> low confidence
```

断言：

- `recovery.strategy == retry_with_expanded_vision`
- `recover_redetect` 输入包含新的 `depth_window` 或阈值。

### 4. PLACE_PLAN_FAILED 后改变 place 输入

注入：

```text
robot.plan_place -> failure
```

断言：

- `recovery.strategy == retry_place_candidates`
- `recover_place` 输入包含 `clearance` 或 candidate offset。

## 风险控制

### 风险 1：override 误伤普通流程

控制：

- 只有 `context["node_input_overrides"]` 存在时才合并。
- nominal test 必须证明默认输入不变。

### 风险 2：actionlist 模板缺少变量时报错

控制：

- 对可选字段使用 actionlist input defaults，或让 runtime 删除值为 `None` 的字段。
- 不在模板里直接引用可能不存在的变量，除非在 input_defaults 中提供。

### 风险 3：RecoveryPlanner 做过多运行时计算

控制：

- 第一版只生成明确、可测试的 overrides。
- 需要 scene/world state 的策略先记录 `not_applied_reason`，不强行假装生效。

### 风险 4：影响稳定 sorting config workflow

控制：

- 不改 `src\sensoragent\workflows\actionlists\sorting_config.py`。
- 不改 `industrial.sorting_config_pick_place_actionlist`。
- 新增测试确保该 workflow 的结构仍与当前一致。

## 第一阶段完成标准

完成后应能证明：

1. `recovery.plan.updated_input` 不再只是日志，而能转化为 `node_overrides`。
2. `DecisionTreeRuntime` 能把 overrides 合并进后续节点输入。
3. 至少三类恢复策略能产生实际动作差异：
   - low confidence / pose invalid -> detect 输入变化；
   - grasp empty -> pick 输入变化；
   - place plan failed -> place 输入变化。
4. `industrial.sorting_config_pick_place_actionlist` 完全不受影响。
5. 全量 Python 测试仍通过。

