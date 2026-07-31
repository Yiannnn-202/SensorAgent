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

---

## 五、The remaining SIM tasks

### 一、需要补的功能（按优先级）

#### P0：视觉层要能拿到 Gazebo 里的真实位姿

现状：`vision.mock_detect` 返回硬编码 `[0.42, -0.13, 0.08, 0, 0, 1.57]`，跟 Gazebo 世界里的物体位置无关。

为什么必须：ActionList 的 step 2 `plan_pick` 完全依赖 `object.pose_3d`，如果这个不对，抓的位置永远是错的。

队友那边怎么绕过的：`test_gazebo_pick_place_pipeline.py` 直接从 CLI 传 `--pick-world-position`，跳过了视觉层。这个路径 LLM 走不通。

有两种落地方案：

| 方案 | 工作量 | 特点 |
|------|--------|------|
| A：`vision.world_lookup` — 从 Gazebo 的 `/gazebo/get_entity_state` 或 tf 拿实体位姿，按 `object_query` 匹配实体名 | 中 | 真闭环，检测层可复用到真机换掉即可 |
| B：`vision.config_detect` — 从 yaml 里读一张 `{object_query: pose}` 表，返回固定位姿 | 小 | 一小时能跑通端到端，但物体不能移动 |

建议先做 B，把 ActionList 端到端跑通；后面再把 B 换成 A。

#### P1：place target 寄存器要匹配 Gazebo 世界的工作台

现状：我给的 `bin_cell_*` 用了占位坐标（z=0.05），队友文档明确说工作台在 world z = 0.30 m、robot_mount_z = 0.18，所以 base_link 下 z 应该 ≈ 0.12（还得加 `--place-offset 0 0 0.08` 让 TCP 悬在工作台上方）。

要做：把 `default_place_target_registry` 的坐标改成跟 industrial world 一致；或者更好，从 `configs/robot_sim.yaml` 的一个 `place_targets:` 段读。

顺带：orientation 也要跟队友脚本一致 `[0, 1, 0, 0]`（这个我已经设了）。

#### P2：Industrial ActionList 需要传 position_offset 和其他参数给 plan_pick / plan_place

现状：`robot.plan_top_down_pick` 支持 `position_offset`、`approach_distance`、`pregrasp_distance`、`lift_height`；`robot.plan_place` 支持 `clearance`。队友脚本默认值：`pick-offset 0 0 0.03`、`approach 0.10`、`pregrasp 0.04`、`lift 0.12`、`place-clearance 0.15`、`place-offset 0 0 0.08`。

要做：ActionList step 里把这些参数填上，否则用 `plan_top_down_pick` 默认（approach=0.10, pregrasp=0.03, lift=0.10, offset=0），会跟 sim 里已验证的默认差一截。

#### P3：需要一个端到端 sim runner 脚本

现状：没有走 `industrial.pick_place_actionlist` 的入口脚本。

要做：写 `scripts/linux/run_industrial_actionlist_sim.py`，形态类似：

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py \
  --utterance "把滚柱放到 bin_cell_3" \
  --config configs/robot_sim.yaml \
  --planner llm \
  --execute
```

内部就是 `build_agent_from_env(..., planner_mode="llm")` + `bundle.agent.run_task(utterance)`，加上 bridge 探活（复用 `_check_bridge` / `_wait_for_ready`）。

#### P4：verify 判据阈值要匹配 Robotiq 2f_85

现状：`verify_grasp` 用 `[0.002, 0.08]`，`verify_place` 用 `≥ 0.05`。Robotiq 2f_85 全开 0.0848，队友脚本 `--close-opening 0.02`。判据应该 OK，但真机上物体宽度决定 opening，需要跑一次 sim 看实际值。

要做：跑一次 pipeline，把 `gripper.get_state` 的返回值打出来对齐阈值；必要时在 ActionList 里通过 `min_opening`/`max_opening`/`open_threshold` 覆盖。

#### P5：Industrial world 目前是空的

现状：`simulation/gazebo/worlds/industrial/` 只有 `.gitkeep`。队友的 sim 依赖 `run_rm65_b_sim.sh` 启动的默认 world 里已经有测试物体（`--pick-world-position 0.24 0.23 0.322` 是有效的）。

要做：确认默认 world 里的物体命名（供 P0-A 的 `vision.world_lookup` 用），并在文档里写清楚 `object_query="roller"` 对应哪个 Gazebo entity。这个是 nice-to-have，做完 B 方案后再决定要不要升到 A。

---

### 二、建议的推进顺序

1. **P1 + P0-B（半天）**：把 bin 坐标改对 + 加 `vision.config_detect`（配一张物体表）→ 用 static planner 直接跑 `industrial.pick_place_actionlist` 到 sim，验证 8 步链路能过。
2. **P2（半小时）**：往 ActionList 的 plan step 里补参数，跟队友已调好的 sim 默认对齐。
3. **P3（一小时）**：写 sim runner 脚本，跑 `planner_mode="static"`，再切 `"llm"` 用 DeepSeek。
4. **P4（跑一次记 log）**：真跑一遍看 `gripper.get_state` 数字调阈值。
5. **P0-A（后续）**：等 B 通了再考虑接 Gazebo 实体查询。
