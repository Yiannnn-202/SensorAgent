# 指令解析 → intent → ActionList 落地方案

_最近更新_：2026-07-26（同步当前 `main` 文档）

## 0. 现状 TL;DR

- 端到端管道当前默认使用稳定方块：`block → target_area_3`。
- `AgentPlan.intent` 已是一等字段，LLM 输出优先读取顶层 `intent`。
- `industrial.pick_only_actionlist`、`industrial.place_only_actionlist` 和
  `industrial.vision_pick_place_actionlist` 已注册。
- 已知硬件边界：部分物件位置和 bin 位置对 RM65-B top-down 抓取超出可达域，需要 workspace 内的组合。

## 1. 全链路时序

```
operator utterance
  │
  ▼ AgentRuntime.run_task(user_input, input_data)
  │
  ▼ LLMPlanner.plan()                              # llm_planner.py
  │  system_prompt = intent_to_workflow.md
  │  user_prompt   = {user_input, initial_input, allowed_targets}
  │  DeepSeek 返回 JSON: target_kind/target/input/reason
  │
  ▼ AgentPlan → allowed_targets 白名单校验
  │  event_stream.publish("task_planned", ...)
  │
  ▼ AgentRuntime._handle_actionlist()
  │
  ▼ ActionListRuntime.run(industrial.pick_place_actionlist, input, trace)
    │
    ├─ detect_object        (tool  vision.config_detect)      → object
    ├─ plan_pick            (tool  robot.plan_top_down_pick)  → pick_plan
    ├─ pick                 (skill robot.pick, 6 sub-steps)   → pick_result
    ├─ verify_grasp         (skill robot.verify_grasp)        → grasp_check
    ├─ resolve_place_target (tool  robot.resolve_place_target)→ place_target
    ├─ plan_place           (tool  robot.plan_place)          → place_plan
    ├─ place_pre_approach_joints (tool robot.move_joints)     # 中转关节位
    ├─ place_move_place     (tool  robot.move_pose OMPL)      # 到目标区释放位姿
    ├─ place_open_gripper   (tool  gripper.open)              # stop_on_failure=False
    ├─ place_retreat        (tool  robot.move_joints)         # 关节退位
    └─ verify_place         (skill robot.verify_place)        → place_check
    │
    ▼ ActionListResult(success, steps=[...], output={context})
  │
  ▼ task.mark(SUCCEEDED|FAILED), event_stream.publish(...)
```

Sim baseline 记录：`logs/tasks/industrial_sim_run_v8.json` — success=true。

## 2. Intent Schema

`AgentPlan` 有 `intent: dict | None` 一等字段（默认 `None`；`StaticPlanner` 保持 `None`
不影响旧路径）。`LLMPlanner` 优先从 LLM 输出的顶级 `intent` 字段读取；如果没有则 fallback
到 `reason` 字符串里正则解析 `intent={...}`（兼容 prompt v2 遗留输出）。

```python
plan.intent = {
  "object": "方块",            # 保留操作员用词
  "action": "pick" | "place" | "pick_place",
  "target": "target_area_3"    # 目的地 id 或空字符串
}
plan.reason = "operator wants ... pick-and-place workflow selected."  # 纯自然语言，不再夹 JSON
```

映射规则（一期只做 pick_place）：

| action | target workflow | ActionList input |
|--------|-----------------|------------------|
| `pick_place` | `industrial.pick_place_actionlist` | `{object_query, target}` |

## 3. 落地组件详解

### 3.1 Planner Prompt

`src/sensoragent/agent/prompts/intent_to_workflow.md`。要求 LLM：
- 解析 utterance 到 `{object, action, target}` intent
- 从 `allowed_targets` 白名单选一个 workflow
- 保留操作员语言在 `object_query`（vision 层做匹配）
- 组合 pick-and-place 时 `action="pick_place"`

### 3.2 LLMPlanner 集成

- `src/sensoragent/agent/llm_planner.py`：LLM 输出 → `AgentPlan` 校验
- `src/sensoragent/integrations/llm.py`：`OpenAICompatibleClient` 走 DeepSeek
- `bootstrap.py:LLMPlanner(..., allowed_targets=tuple(actionlists.keys()))` 白名单已就位
- 环境变量：`SENSORAGENT_LLM_API_KEY` / `SENSORAGENT_LLM_BASE_URL` / `SENSORAGENT_LLM_MODEL`

### 3.3 Vision 层：`vision.config_detect`

`src/sensoragent/tools/vision/config_detect.py`。替代 `vision.mock_detect`，从
`configs/robot_sim.yaml` 的 `scene.objects` 段读取物体表，支持：
- 中英文物体名（`block`, `cube`, `red_block`, `方块` 都指向同一 pose）
- 大小写 / 子串匹配

Contract：`contracts/tools/vision.config_detect.schema.json`。

### 3.4 Scene 配置层

新增 `SensorAgentConfig.scene: SceneConfig(objects, place_targets)`：

- `src/sensoragent/config/schema.py`：`SceneConfig` dataclass
- `src/sensoragent/config/loader.py`：YAML 加载
- `bootstrap.py:_build_scene_tool`：把 scene 数据注入到 `vision.config_detect` /
  `robot.resolve_place_target`

`configs/robot_sim.yaml` 的 `scene:` 段当前默认配好稳定方块和 2x2
`target_area_*` 目标区；`roller` 等别名暂时映射到同一方块位姿，方便之后切回视觉滚柱验证。

### 3.5 Place target 寄存器：`robot.resolve_place_target`

`src/sensoragent/tools/robot/place_targets.py`。把 `target_area_3` 字符串解析成
具体的 `RobotPose`。默认注册表在代码里；yaml `scene.place_targets` 会覆盖默认。

Contract：`contracts/tools/robot.resolve_place_target.schema.json`。

### 3.6 Industrial ActionList（11 步）

`src/sensoragent/workflows/actionlists/industrial.py`。关键设计决策：

- **place 阶段展开在 ActionList 内**（不用 `robot.place` skill），为了灵活控制每步失败策略。
- **`place_pre_approach_joints`**：关节空间中转位 `[-0.17, -0.57, -0.61, 0, -1.96, 0]`，
  把 arm 摆到 target grid 上方 gripper-down 姿态。避开 pick lift → target approach 的 OMPL 大幅重定向。
- **`place_move_place`**：`robot.move_pose` OMPL 到 target area 释放位姿（不用 Cartesian，避免起点漂移导致的 IK 中断）。
- **`place_open_gripper`**：`stop_on_failure=False`，允许 Robotiq bridge 报 stall 但物件已释放。
- **`place_retreat`**：`robot.move_joints` 回到 staging，不用 Cartesian/OMPL（避免物件释放后 planning scene 变化引起的失败）。

### 3.7 Verify 层

- `robot.verify_grasp`：`gripper.get_state.state.opening` ∈ `[0.002, 0.08]` → 判定夹住
- `robot.verify_place`：`opening ≥ 0.05` → 判定释放

`src/sensoragent/skills/robot/verify.py`。判据可通过 ActionList step 输入覆盖。

### 3.8 ActionListRuntime 语义

`src/sensoragent/workflows/actionlists/runtime.py`。修正：`success` 只由 `stop_on_failure=True`
的 step 决定；best-effort step 失败不拉低整体 success。让 `place_open_gripper` 报 stall 但
verify_place 通过的场景返回 `success=True`。

### 3.9 Sim runner 脚本

`scripts/linux/run_industrial_actionlist_sim.py`：
- `--planner static|llm`
- `--execute` / `--json-out`
- `--reset-home`（默认 True）：跑前先把 arm 移回 all-zeros，避免上次遗留状态干扰 IK

## 4. 关键 sim 参数（`robot_sim.yaml` scene）

### 4.1 Objects catalog（world 坐标 → base_link，mount yaw=180°，减去 mount_z=0.18）

| 名称 | pose_3d（base_link） | 说明 |
|------|---------------------|------|
| block / cube / red_block / 方块 | `[-0.24, -0.18, 0.140]` | 当前默认，可达且不滚动 |
| roller / silver_roller / 滚柱 | `[-0.24, -0.18, 0.140]` | 临时别名，当前也指向方块位姿 |

### 4.2 Place targets（TCP 释放位姿）

- z=0.24（base_link）：target grid 上方释放高度，避免 gripper 压桌
- orientation `(0.9962, -0.0872, 0, 0)`：匹配 staging pose 到达时的实际姿态，避开 IK 奇异

| 名称 | position | 可达性 |
|------|----------|--------|
| target_area_1 | `[-0.24, 0.10, 0.24]` | 2x2 grid 前左 |
| target_area_2 | `[-0.40, 0.10, 0.24]` | 2x2 grid 前右 |
| target_area_3 | `[-0.24, -0.04, 0.24]` | 当前推荐目标 |
| target_area_4 | `[-0.40, -0.04, 0.24]` | 2x2 grid 后右 |
| bin_cell_1..4 | 同上 | 向后兼容别名 |

## 5. Sim 实测结果

### 5.1 Baseline

当前推荐 baseline：`block → target_area_3`。
- pick 6 步；
- place 采用已调好的 `place_staging_joints`；
- arm 返回 staging，gripper 全开。

### 5.2 边界发现

- `Round 2: gear → bin_cell_2`：pick.move_pregrasp Cartesian fraction 0.000 —
  gear 在 workspace 边缘，approach 找得到 IK 但 descent 一步都走不了。
- `Round 3: short_bolt → bin_cell_1`：pick 成功；place 因 bin_cell_1 Y=-0.30
  超出 top-down 可达域，OMPL 直接 abort。

**结论**：管道机制没问题；失败纯是 RM65 + top-down gripper-down 姿态的物理可达域限制。

## 6. 已知限制与短期对策

| 问题 | 现象 | 短期对策 |
|------|------|----------|
| IK 奇异 `(0, 1, 0, 0)` | OMPL 找不到解 | 用 5° tilt / 微扰动 quaternion |
| Cartesian planner 严格阈值 0.98 | 偶发失败 | Place 阶段改用 OMPL 而非 Cartesian |
| 抓物件时 OMPL 拒绝规划 | 起点判 in-collision | 用 move_joints 中转关节位、Cartesian 到近 target |
| 单 staging pose 覆盖有限 | 极端 target 够不到 | 先用 `target_area_3` 作为主要目的地 |
| gear 位置抓不了 | workspace 边缘 | 后续换 oriented pick 或调 pick offset |
| Sim world 物件不自动 reset | 跑一次后 block 已移动 | 每轮之间重启 sim |

## 7. 使用方式

### 7.1 环境准备

`.env`（`.env.example` 复制）：

```
SENSORAGENT_LLM_API_KEY=<your DeepSeek key>
SENSORAGENT_LLM_BASE_URL=https://api.deepseek.com
SENSORAGENT_LLM_MODEL=deepseek-v4-flash
```

依赖：在 Agent Python 3.12 环境中执行 `python -m pip install -r requirements.txt`。

### 7.2 启 Gazebo sim

```bash
# 一次性
bash scripts/linux/prepare_rm65_b_sim.sh
# 每次跑之前
bash scripts/linux/run_rm65_b_sim.sh
```

`curl http://127.0.0.1:8765/ready` 确认四个 interface 都 true。

### 7.3 跑 baseline（static planner）

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py \
  --planner static --object-query block --target target_area_3 --execute \
  --json-out logs/tasks/baseline.json
```

### 7.4 跑 LLM planner

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/run_industrial_actionlist_sim.py \
  --planner llm --utterance "把方块放到 target_area_3" --execute \
  --json-out logs/tasks/llm_run.json
```

### 7.5 离线 prompt 校验（不用 sim）

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/check_llm_planner_prompt.py
```

## 8. 后续可选项

优先级从高到低：

1. 增加自动化 ROS 2/Gazebo 验收，覆盖 bridge ready、pick、place 和工业 ActionList。
2. 增加场景 reset/物件重生能力，避免每轮手动重启 sim。
3. 扩展 `industrial.retry_pick_place_tree`（DecisionTree），接入失败重试和恢复。
4. 扩展 LLM 中英文 fixture 测试，覆盖歧义、缺目标、非法物件和同义词。
5. 扩展 Vision 层：更稳定的开放词汇模型、mask/点云融合和 bin 占用验证。
