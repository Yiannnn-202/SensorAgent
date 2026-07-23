# 汇报：当前系统能力与用法

## 一、已具备的能力

### 1. 自然语言 → 结构化 intent → 工业 ActionList 全链路

操作员用中/英文说一句「把滚柱放到 bin_cell_3」，系统内部的处理流程：

```
user_input
  │
  ▼ LLMPlanner（DeepSeek 已接入，temperature=0，response_format=json_object）
  │  system_prompt = src/sensoragent/agent/prompts/intent_to_workflow.md
  │  强制输出 intent + allowed_targets 白名单校验
  ▼
AgentPlan {
  target = "industrial.pick_place_actionlist",
  input  = {"object_query": "滚柱", "target": "bin_cell_3"},
  reason = "intent={...}; ..."
}
  │
  ▼ ActionListRuntime 按顺序执行 8 步
```

### 2. 工业 pick-and-place ActionList（8 步）

`industrial.pick_place_actionlist` 的完整链路：

| # | Step | Kind | Target | 作用 |
|---|------|------|--------|------|
| 1 | detect_object | tool | vision.mock_detect | 目标检测，输出 `object_id` + `pose_3d` |
| 2 | plan_pick | tool | robot.plan_top_down_pick | 由检测位置生成 approach/pregrasp/grasp/lift |
| 3 | pick | skill | robot.pick | open → approach → pregrasp → grasp → close → lift |
| 4 | **verify_grasp** | skill | robot.verify_grasp | 读夹爪开度判定是否夹到 |
| 5 | resolve_place_target | tool | robot.resolve_place_target | `bin_cell_3` → 具体 pose |
| 6 | plan_place | tool | robot.plan_place | 生成 approach/place/retreat |
| 7 | place | skill | robot.place | approach → place → open → retreat |
| 8 | **verify_place** | skill | robot.verify_place | 读夹爪开度确认已松开 |

任意一步失败 → `stop_on_failure=True` 立即短路，`ActionListResult.error` 定位失败 step。

### 3. verify 层（新增）

- `robot.verify_grasp`：`gripper.get_state.state.opening` 在 `[0.002, 0.08]` 内 → 判定为夹住。
- `robot.verify_place`：`opening ≥ 0.05` → 判定为已松开。

判据参数可覆盖：ActionList 中传 `min_opening` / `max_opening` / `open_threshold` 即可调整。

### 4. 目的地寄存器（新增）

`robot.resolve_place_target` 内置默认注册表（`src/sensoragent/tools/robot/place_targets.py:53`）：

```
bin_cell_1  → (0.40, -0.20, 0.05)
bin_cell_2  → (0.40,  0.00, 0.05)
bin_cell_3  → (0.40,  0.20, 0.05)
conveyor    → (0.55,  0.00, 0.05)
```

未知 target 会返回 `unknown place target: <name>`，短路上游 workflow。

### 5. 兼容性

- 旧的 `mock.pick_place_actionlist`、`audio.voice_command_ack_actionlist` 保持不变。
- `planner_mode="static"` 时继续走静态 planner；`planner_mode="llm"` 时启用 DeepSeek，白名单自动同步 `actionlists.keys()`。

---

## 二、当前不能做什么（有意保留的边界）

1. **失败后不会自动重试**。verify_grasp 失败就直接终止。仓库里有 `DecisionTreeRuntime` + `build_mock_retry_pick_tree` 模板可以后续挂 `industrial.retry_pick_place_tree`。
2. **pick-only / place-only 语句还没独立 workflow**。Prompt 支持解析出 `action: "pick"|"place"`，但一期只挂了 `pick_place`。
3. **bin 坐标是占位值**。真机前需要把 `default_place_target_registry` 的坐标换成实测值，或者做成从 yaml 读。
4. **判据只用 gripper opening**。真机若接力矩/视觉复核，把 `verify.py:_read_gripper_opening` 换成注入式验证器即可。
5. **检测走的是 mock**。`vision.mock_detect` 返回固定结果；真机替换成真实视觉 tool 时，ActionList 只要改一行 `target`。

---

## 三、用法

### 3.1 环境准备

`.env`（仓库根）：

```
SENSORAGENT_LLM_PROVIDER=deepseek
SENSORAGENT_LLM_BASE_URL=https://api.deepseek.com
SENSORAGENT_LLM_API_KEY=<你的 key>
SENSORAGENT_LLM_MODEL=deepseek-chat   # 或 deepseek-v4-flash
```

依赖：venv 里补装了 `numpy`（`planning.py` 依赖），后续 push 前建议加进 `requirements.txt`。

### 3.2 端到端 Python 调用

```python
from sensoragent.agent import build_agent_from_env

bundle = build_agent_from_env(
  "configs/robot_sim.yaml",
  planner_mode="llm",       # 启用 DeepSeek
)

task = bundle.agent.run_task("把滚柱放到 bin_cell_3")

print(task.plan.to_dict())
# {
#   "target_kind": "actionlist",
#   "target": "industrial.pick_place_actionlist",
#   "input": {"object_query": "滚柱", "target": "bin_cell_3"},
#   "reason": "intent={\"object\":\"滚柱\",\"action\":\"pick_place\",\"target\":\"bin_cell_3\"}; ..."
# }
print(task.status, task.error)
print(task.result["grasp_check"])   # {"held": True/False, "opening": ...}
print(task.result["place_check"])   # {"released": True/False, "opening": ...}
```

### 3.3 直接跑 ActionList（跳过 LLM）

```python
from sensoragent.agent import build_agent_from_env
from sensoragent.schemas import AgentRequest, TraceContext

bundle = build_agent_from_env("configs/robot_sim.yaml")
resp = bundle.agent.handle(
  AgentRequest(
    actionlist="industrial.pick_place_actionlist",
    input={"object_query": "silver roller", "target": "bin_cell_3"},
    trace=TraceContext(),
  )
)
print(resp.success, resp.error, resp.result)
```

### 3.4 事件流与 trace

`AgentRuntime.run_task` 会向 `event_stream` 依次广播：

```
task_created → task_started → task_planned
  → actionlist_started
    → action_step_started/finished ×8
  → actionlist_finished
→ task_succeeded | task_failed
```

`task_planned` 事件里包含完整 `plan.reason`（含 intent JSON 字符串），trace 全流程可复盘。

### 3.5 跑测试

```bash
.venv/bin/python -m unittest \
  tests.unit.test_verify_and_place_targets \
  tests.unit.test_industrial_actionlist \
  tests.unit.test_llm_planner -v
# → Ran 15 tests, OK
```

---

## 四、后续可选（如果你要继续推进）

1. 把 `bin_cell_*` 坐标搬到 `configs/robot_sim.yaml` 的 `place_targets:` 段，`bootstrap._build_tool` 里注入。
2. 加 `industrial.pick_only_actionlist` / `industrial.place_only_actionlist`，Prompt 里让 LLM 按 `intent.action` 选择。
3. 挂 `industrial.retry_pick_place_tree`（DecisionTree），`verify_grasp.failure → retry` 一次。
4. `AgentPlan` 加 `intent: dict | None` 字段，让 intent 从 `reason` 字符串升级为一等公民。
