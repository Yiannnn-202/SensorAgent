# 指令解析 → intent → ActionList 落地方案

## 0. 背景

SensorAgent 已经具备：

- `LLMPlanner`（`src/sensoragent/agent/llm_planner.py`）：把 LLM 返回的 JSON 校验成 `AgentPlan`。
- `OpenAICompatibleClient`（`src/sensoragent/integrations/llm.py`）：DeepSeek 接入完成，`SENSORAGENT_LLM_*` 环境变量已生效，`temperature=0`、`response_format={"type":"json_object"}`。
- `ActionListRuntime`（`src/sensoragent/workflows/actionlists/runtime.py`）：顺序执行、支持 `{{ path.field }}` 模板、`save_as` 上下文注入、`stop_on_failure` 短路。
- `AgentRuntime.run_task`（`src/sensoragent/agent/runtime.py:199`）：`user_input → planner.plan → selector.select → dispatch(actionlist)` 已经串通。
- 现成 skill：`robot.pick`、`robot.place`；现成 tool：`vision.mock_detect`、`robot.plan_top_down_pick`、`robot.plan_place`、`gripper.get_state` 等。

**目标**：让操作员说一句「把滚柱放到 bin_cell_3」，DeepSeek 输出结构化 intent，Runtime 落到工业场景的 ActionList
（`pick → verify_grasp → place → verify_place`），每一步都能被 trace 到，失败时短路返回。

---

## 1. 全链路时序

```
operator utterance
      │
      ▼
AgentRuntime.run_task(user_input, input_data)
      │
      ▼
LLMPlanner.plan()                       # llm_planner.py:34
      │  system_prompt = intent_to_workflow.md
      │  user_prompt   = {user_input, initial_input, allowed_targets}
      │  temperature=0, response_format=json_object
      ▼
DeepSeek returns JSON:
{
  "target_kind": "actionlist",
  "target": "industrial.pick_place_actionlist",
  "input":  {"object_query": "滚柱", "target": "bin_cell_3"},
  "reason": "intent={\"object\":\"滚柱\",\"action\":\"pick_place\",\"target\":\"bin_cell_3\"}; ..."
}
      │
      ▼
AgentPlan(target_kind=ACTIONLIST, target=..., input=..., reason=...)
      │  → allowed_targets 白名单校验 (llm_planner.py:47)
      │  → event_stream.publish("task_planned", trace, {"plan": ...})
      ▼
AgentRuntime._handle_actionlist()       # runtime.py:64
      ▼
ActionListRuntime.run(industrial.pick_place_actionlist, input, trace)
      │
      ├── detect_object    (tool  vision.mock_detect)      → object
      ├── plan_pick        (tool  robot.plan_top_down_pick)→ pick_plan
      ├── pick             (skill robot.pick)              → pick_result
      ├── verify_grasp     (skill robot.verify_grasp)      → grasp_check  ← 新增
      ├── plan_place       (tool  robot.plan_place)        → place_plan
      ├── place            (skill robot.place)             → place_result
      └── verify_place     (skill robot.verify_place)      → place_check  ← 新增
      │
      ▼
ActionListResult(success, steps=[...], output={...上下文...})
      │
      ▼
task.mark(SUCCEEDED|FAILED), event_stream.publish(...)
```

---

## 2. 结构化 intent 定义

不改 `AgentPlan` 的 schema，把 intent 作为 planner 的中间产物：LLM 内部解析出 intent，
再由 intent 决定填给哪个 workflow、参数如何映射。intent 结构以字符串形式塞进 `AgentPlan.reason`
供 trace 记录，`ActionList` 只吃**扁平化后的执行参数**。

**intent schema（约定，不落到代码）**：

```json
{
  "object": "滚柱",
  "action": "pick" | "place" | "pick_place",
  "target": "bin_cell_3"
}
```

**映射规则**：

| action        | target workflow                          | ActionList input                                        |
|---------------|------------------------------------------|---------------------------------------------------------|
| `pick_place`  | `industrial.pick_place_actionlist`       | `{object_query: intent.object, target: intent.target}`  |
| `pick`        | （后续）`industrial.pick_only_actionlist` | `{object_query: intent.object}`                         |
| `place`       | （后续）`industrial.place_only_actionlist`| `{object_id: ..., target: intent.target}`               |

一期只做 `pick_place`。`pick`/`place` 单独跑的场景后续再补 ActionList，不影响本次改动。

---

## 3. 落地改动清单

按修改幅度从小到大排列。

### 3.1 升级 Planner Prompt

**文件**：`src/sensoragent/agent/prompts/intent_to_workflow.md`（替换）

```markdown
# Intent to Workflow Planner Prompt

You are the SensorAgent planner for an industrial pick-and-place cell.

Input JSON:
- user_input: raw operator utterance (Chinese or English)
- initial_input: {} or task-scope defaults
- allowed_targets: whitelist of workflow ids you may return

Task:
1. Parse the utterance into an intent:
   { "object": "<object phrase, keep operator wording>",
     "action": "pick" | "place" | "pick_place",
     "target": "<bin/location id or empty string>" }
2. Choose one target from allowed_targets that fulfills the intent.
3. Fill the workflow input contract for that target.

Return ONLY this JSON:

{
  "target_kind": "actionlist",
  "target": "<one of allowed_targets>",
  "input": {
    "object_query": "<intent.object>",
    "target": "<intent.target>"
  },
  "reason": "intent=<compact JSON of the parsed intent>; <one short sentence>"
}

Rules:
- Never invent a target outside allowed_targets.
- For combined pick-and-place utterances, always set action="pick_place".
- Preserve the operator's language in object_query; vision handles matching.
- If the destination is missing but the target workflow requires one, leave input.target="" and let downstream validation surface it.
```

### 3.2 显式声明 `allowed_targets`

**文件**：`src/sensoragent/agent/bootstrap.py:257`

```python
if planner_mode == "llm":
  planner = LLMPlanner(
    OpenAICompatibleClient(load_llm_config_from_env()),
    allowed_targets=(
      "industrial.pick_place_actionlist",
      "mock.pick_place_actionlist",
    ),
  )
```

`LLMPlanner.__init__` 早已支持该参数（`llm_planner.py:26`），只是当前 bootstrap 没传，因此 DeepSeek 只会走
`mock.pick_place_actionlist`。

### 3.3 新增两个 verify skill

复用现有 `gripper.get_state`，避免引入新的 contract。真机迁移时把判据换成力矩/视觉即可。

**新文件**：`src/sensoragent/skills/robot/verify.py`

```python
"""Grasp and place verification skills."""

from __future__ import annotations

from sensoragent.schemas import SkillCall, SkillResult, SkillSpec
from sensoragent.skills.base import SkillContext


class RobotVerifyGraspSkill:
  spec = SkillSpec(
    name="robot.verify_grasp",
    description="Confirm an object is held by reading gripper state.",
    tags=("robot", "verify"),
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    min_opening = float(call.input.get("min_opening", 0.002))
    max_opening = float(call.input.get("max_opening", 0.08))
    state = context.tool_runtime.invoke("gripper.get_state", {}, call.trace)
    if not state.success:
      return SkillResult(skill=self.spec.name, success=False, error=state.error)
    opening = float(state.output.get("state", {}).get("opening", 0.0))
    held = min_opening <= opening <= max_opening
    return SkillResult(
      skill=self.spec.name,
      success=held,
      output={"held": held, "opening": opening},
      error=None if held else f"grasp not detected (opening={opening:.4f})",
    )


class RobotVerifyPlaceSkill:
  spec = SkillSpec(
    name="robot.verify_place",
    description="Confirm the object was released by reading gripper state.",
    tags=("robot", "verify"),
  )

  def run(self, call: SkillCall, context: SkillContext) -> SkillResult:
    open_threshold = float(call.input.get("open_threshold", 0.05))
    state = context.tool_runtime.invoke("gripper.get_state", {}, call.trace)
    if not state.success:
      return SkillResult(skill=self.spec.name, success=False, error=state.error)
    opening = float(state.output.get("state", {}).get("opening", 0.0))
    released = opening >= open_threshold
    return SkillResult(
      skill=self.spec.name,
      success=released,
      output={"released": released, "opening": opening},
      error=None if released else f"place not confirmed (opening={opening:.4f})",
    )
```

**导出**：`src/sensoragent/skills/robot/__init__.py` 加：

```python
from sensoragent.skills.robot.verify import RobotVerifyGraspSkill, RobotVerifyPlaceSkill
```

**注册**：`src/sensoragent/agent/bootstrap.py:75` 的 `AVAILABLE_SKILLS` 增加：

```python
"robot.verify_grasp": RobotVerifyGraspSkill,
"robot.verify_place": RobotVerifyPlaceSkill,
```

### 3.4 新增工业 ActionList

**新文件**：`src/sensoragent/workflows/actionlists/industrial.py`

```python
"""Industrial pick-and-place ActionList."""

from sensoragent.schemas import ActionList, ActionStep, ActionStepKind


def build_industrial_pick_place_actionlist() -> ActionList:
  return ActionList(
    name="industrial.pick_place_actionlist",
    description="Industrial pick → verify_grasp → place → verify_place.",
    inputs={"object_query": "string", "target": "string"},
    tags=("industrial", "pick-place"),
    steps=[
      ActionStep(
        name="detect_object",
        kind=ActionStepKind.TOOL,
        target="vision.mock_detect",
        input={"query": "{{ object_query }}"},
        save_as="object",
      ),
      ActionStep(
        name="plan_pick",
        kind=ActionStepKind.TOOL,
        target="robot.plan_top_down_pick",
        input={"grasp": "{{ object.pose_3d }}"},
        save_as="pick_plan",
      ),
      ActionStep(
        name="pick",
        kind=ActionStepKind.SKILL,
        target="robot.pick",
        input={
          "plan": "{{ pick_plan.plan }}",
          "object_id": "{{ object.object_id }}",
        },
        save_as="pick_result",
      ),
      ActionStep(
        name="verify_grasp",
        kind=ActionStepKind.SKILL,
        target="robot.verify_grasp",
        input={},
        save_as="grasp_check",
      ),
      ActionStep(
        name="plan_place",
        kind=ActionStepKind.TOOL,
        target="robot.plan_place",
        input={"target": "{{ target }}"},
        save_as="place_plan",
      ),
      ActionStep(
        name="place",
        kind=ActionStepKind.SKILL,
        target="robot.place",
        input={
          "plan": "{{ place_plan.plan }}",
          "object_id": "{{ object.object_id }}",
          "target": "{{ target }}",
        },
        save_as="place_result",
      ),
      ActionStep(
        name="verify_place",
        kind=ActionStepKind.SKILL,
        target="robot.verify_place",
        input={},
        save_as="place_check",
      ),
    ],
  )
```

> ActionList 模板只支持 `{{ path.to.field }}` 单值替换（见 `runtime.py:22`），
> 所以 `plan_top_down_pick` / `plan_place` 若返回 `{"plan": {...}}` 结构，用 `{{ pick_plan.plan }}` 取值；
> 如果它们直接返回 pose，请落地时按 contract 校准字段名。

**导出**：
- `src/sensoragent/workflows/actionlists/__init__.py`：`from .industrial import build_industrial_pick_place_actionlist`
- `src/sensoragent/workflows/__init__.py` 的 `__all__` 追加同名符号

**注册**：`src/sensoragent/agent/bootstrap.py:243`

```python
actionlists = {
  "mock.pick_place_actionlist": build_mock_pick_place_actionlist(),
  "audio.voice_command_ack_actionlist": build_voice_command_ack_actionlist(),
  "industrial.pick_place_actionlist": build_industrial_pick_place_actionlist(),
}
```

---

## 4. 端到端示例

```python
from sensoragent.agent import build_agent_from_env

bundle = build_agent_from_env("configs/robot_sim.yaml", planner_mode="llm")
task = bundle.agent.run_task("把滚柱放到 bin_cell_3")

print(task.plan.to_dict())
# {
#   "target_kind": "actionlist",
#   "target": "industrial.pick_place_actionlist",
#   "input": {"object_query": "滚柱", "target": "bin_cell_3"},
#   "reason": "intent={\"object\":\"滚柱\",\"action\":\"pick_place\",\"target\":\"bin_cell_3\"}; ..."
# }

for step in task.result.get("place_check", {}), task.result.get("grasp_check", {}):
  print(step)
```

DeepSeek 实际收到的 user_prompt：

```json
{
  "user_input": "把滚柱放到 bin_cell_3",
  "initial_input": {},
  "allowed_targets": ["industrial.pick_place_actionlist", "mock.pick_place_actionlist"]
}
```

事件流会依次出现 `task_created` → `task_started` → `task_planned` →
`actionlist_started` → 每个 `action_step_started/finished` → `actionlist_finished` →
`task_succeeded|task_failed`。intent 字符串在 `task_planned` 的 `plan.reason` 里可查。

---

## 5. 失败处理约定

- `stop_on_failure=True`（`ActionStep` 默认）：任意 step 失败立刻返回 `ActionListResult.success=False`，
  `error` 是失败 step 的 `error`。
- `verify_grasp` 失败 → 直接终止，`error="grasp not detected (opening=...)"`；
  上层业务可以据此触发人工干预或后续重试。
- `verify_place` 失败 → 通常意味着夹爪没打开或物件被卡住，同样立刻返回。
- **自动重试不在一期范围**。已有 `DecisionTreeRuntime` + `build_mock_retry_pick_tree`
  （`workflows/decision_trees/mock.py:12`）可作模板，等主链路稳定再挂
  `industrial.retry_pick_place_tree`。

---

## 6. 测试计划

`tests/unit/`：

1. `test_llm_planner_industrial.py`
   - 用 stub `JsonPlanningClient` 返回工业目标 JSON，断言 `AgentPlan.target == "industrial.pick_place_actionlist"`。
   - LLM 返回不在 `allowed_targets` 的目标 → `ValueError`。
2. `test_verify_skills.py`
   - Stub `ToolRuntime`，`gripper.get_state` 返回不同 `opening`，覆盖成功/失败两支。
3. `test_industrial_actionlist.py`
   - 构造 `ActionListRuntime` + 打桩的 tool/skill runtime，跑一遍完整 7 步。
   - `verify_grasp` 打桩失败 → ActionList 在第 4 步短路，后续 step 不进入。

`tests/e2e/`：

4. `test_industrial_pipeline_llm.py`（可选）
   - `planner_mode="llm"`，使用真实 DeepSeek key（放到 `pytest.mark.integration` 里，CI 默认跳过）。
   - 断言 `task.plan.target == "industrial.pick_place_actionlist"`。

---

## 7. 后续可选

- 把 intent 提升为 `AgentPlan` 的一等字段（`intent: dict | None`），代价是改 schema + 序列化。
- `verify_grasp` 判据插件化：`RobotVerifyGraspSkill(__init__(self, verifier: Verifier))`，
  背后支持 `gripper_opening` / `force_torque` / `vision_recheck` 多种实现。
- 新增 `industrial.retry_pick_place_tree`：`verify_grasp.failure → retry_pick (max_retries=1)`，
  `verify_place.failure → recover`。

---

## 8. 需要确认的两点

1. **verify 判据**：一期先用 `gripper.opening` 阈值。真机是否已有力矩/接近觉数据可以复核？
2. **`plan_top_down_pick` / `plan_place` 的返回结构**：文档里用 `{{ pick_plan.plan }}` 假设它们
   返回 `{"plan": {...}}`。落地前请对齐 `contracts/tools/robot.plan_*.schema.json`。


## 9. 总结

这是一份工程落地方案文档，描述了如何把自然语言指令（「把滚柱放到 bin_cell_3」）接通到工业机器人的完整执行链路。

  ---
  文档做了什么

  背景：SensorAgent 已有 LLM Planner、LLM 接入（DeepSeek）、ActionList Runtime 等基础组件，但它们还没有串成一条完整的工业场景流水线。

  ---
  一共做了 4 件具体的事：

  1. 升级 Planner Prompt（src/sensoragent/agent/prompts/intent_to_workflow.md）
  - 改写 system prompt，让 DeepSeek 把中文/英文自然语言解析成结构化 intent（object + action + target），再映射到对应 workflow，最终返回
  AgentPlan JSON。

  2. 在 bootstrap 里显式传 allowed_targets（bootstrap.py:257）
  - 把 industrial.pick_place_actionlist 和 mock.pick_place_actionlist 加入白名单，防止 LLM 乱选目标；当前缺失这一传参导致只能走 mock。

  3. 新增两个验证 skill（src/sensoragent/skills/robot/verify.py）
  - robot.verify_grasp：抓取后读夹爪开口判断是否夹住物体
  - robot.verify_place：放置后读夹爪开口判断是否已释放
  - 两者都复用现有 gripper.get_state tool，不引入新依赖

  4. 新增工业 ActionList（src/sensoragent/workflows/actionlists/industrial.py）
  - industrial.pick_place_actionlist，完整 7 步流程：detect_object → plan_pick → pick → verify_grasp → plan_place → place → verify_place
  - 任意步失败立刻短路（stop_on_failure=True），上下文通过 {{ path.field }} 模板传递

  ---
  配套内容：
  - 第 5 节定义了失败处理约定（短路策略，一期不做自动重试）
  - 第 6 节给出了 3 个单测 + 1 个可选 e2e 测试的计划
  - 第 7、8 节列出了后续扩展点和两个待确认问题（verify 判据、plan 返回结构）



## 10.logs

2026/7/22 George-Lin-encx做了以下调整：
  、 Let me plan out the changes:

  1. src/sensoragent/agent/prompts/intent_to_workflow.md - replace with new prompt
  2. src/sensoragent/skills/robot/verify.py - new file with verify_grasp, verify_place skills
  3. src/sensoragent/skills/robot/__init__.py - export new skills
  4. src/sensoragent/tools/robot/place_targets.py - new file with resolve_place_target tool
  5. src/sensoragent/tools/robot/__init__.py - export new tool
  6. contracts/tools/robot.resolve_place_target.schema.json - contract
  7. src/sensoragent/workflows/actionlists/industrial.py - new file
  8. src/sensoragent/workflows/actionlists/__init__.py - export
  9. src/sensoragent/workflows/__init__.py - export
  10. src/sensoragent/agent/bootstrap.py - register new tool, skill, actionlist, and pass allowed_targets

  Let me also check what tools init looks like.

  Read 2 files (ctrl+o to expand)

● Now I have a complete picture. Key issue I need to address: robot.plan_place expects a place_pose (RobotPose dict), not a target string. I
  need to add a robot.resolve_place_target tool that resolves a target string (like bin_cell_3) to a place_pose.

  Let me start implementing. Plan of attack:

  1. Update prompt file
  2. Create verify.py skill file with two skills
  3. Update skills/robot/init.py to export
  4. Create resolve_place_target.py tool with a static registry
  5. Update tools/robot/init.py to export
  6. Create contract for the new tool
  7. Create industrial.py actionlist
  8. Update actionlists/init.py
  9. Update workflows/init.py
  10. Update bootstrap.py: register tool, register skill, register actionlist, pass allowed_targets to LLMPlanner