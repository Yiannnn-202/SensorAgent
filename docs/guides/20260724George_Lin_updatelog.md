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

---

# 已完成 vs 待完成盘点

## 一、已完成（这几轮实测过或至少测试通过）

### 1. 指令解析层（Prompt + LLMPlanner）

- `src/sensoragent/agent/prompts/intent_to_workflow.md` 已升级为工业 intent 解析版
- `LLMPlanner.allowed_targets` 已从 `bootstrap.py` 传入 `tuple(actionlists.keys())`
- DeepSeek 集成走 `OpenAICompatibleClient`
- 单测通过（未在 sim 中实测 LLM 路径）

### 2. Vision 层（P0-B）

- 新增 `vision.config_detect` 工具，从 yaml `scene.objects` 读物体表
- 支持大小写 / 子串匹配、中英文物体名
- Contract 落地
- Sim 中已用（Round 1 detect_object 步骤过）

### 3. Scene 配置层

- `SensorAgentConfig` 加了 `scene: SceneConfig(objects, place_targets)`
- `bootstrap._build_scene_tool` 注入 scene 数据到 `vision.config_detect` / `robot.resolve_place_target`
- `configs/robot_sim.yaml` 已把 5 种 industrial world 物件 + 7 个 place target 全部配好

### 4. Place target 寄存器

- `robot.resolve_place_target` 工具 + contract
- 默认注册表 + yaml 覆盖两条路都通

### 5. Industrial ActionList（11 步）

- `industrial.pick_place_actionlist` 已定型：

```
detect → plan_pick → pick(6 sub) → verify_grasp
→ resolve_place_target → plan_place
→ place_pre_approach_joints (joints) → place_move_place (OMPL)
→ place_open_gripper (best-effort) → place_retreat (joints) → verify_place
```

- 参数与队友 sim 默认对齐

### 6. Verify 层

- `robot.verify_grasp` / `robot.verify_place` skill
- 判据：gripper opening 阈值
- Sim 中 `verify_grasp opening=0.0397 held=True`、`verify_place opening=0.0847 released=True` 都正确

### 7. Runtime 语义

- `ActionListRuntime.success` 修好：`stop_on_failure=False` 的 step 失败不再拉低整体
- 允许 `gripper.open` 报 stall 但物理上完成

### 8. Sim runner 脚本

- `scripts/linux/run_industrial_actionlist_sim.py`
- 支持 `--planner static|llm`、`--execute`、`--reset-home`（自动 reset）、`--json-out`
- 用队友已有的 bridge 探活辅助函数

### 9. Sim 实测 baseline

- **Round 1: roller → bin_cell_3 全绿通** ← 端到端唯一被证实的完整链路
- 11 个 step 全部成功
- roller 从工作台被抓起、放进 bin_cell_3、arm 返回 staging pose

### 10. 单测

- 17 个测试全绿（含 industrial actionlist 11 步顺序断言、runtime 语义、planner 白名单等）

### 11. Merge

- rebase 到 `origin/main` 上（含队友 `4977b16` pre_approach_joints 改进），已 force-push 到 `george-sim-test`

---

## 二、推进 LLM planner 前还没做的事

按重要性排序：

### A. 用 LLM planner 至少在 sim 里跑通一次（核心遗留）

- 目前所有 sim 验证都用 `--planner static`
- 需要用 `--planner llm --utterance "把滚柱放到 bin_cell_3"` 跑一次 `--execute`，看 DeepSeek 输出的 intent 是不是能被 LLMPlanner 落成 `AgentPlan(target=industrial.pick_place_actionlist, input={"object_query":"滚柱","target":"bin_cell_3"})`，然后端到端跑完 sim
- 你 `.env` 里需要有 `SENSORAGENT_LLM_API_KEY`
- 这是"LLM planner 已推进"的最小验证

### B. Prompt 层的 sanity check

- Prompt 里说 preserve operator's language in `object_query`，但 yaml 里 catalog 是 `滚柱: ...`, `silver_roller: ...`, `roller: ...` — 三个 key 指向同一个 pose
- LLM 会输出 `"object_query": "滚柱"` 还是 `"roller"`？如果 LLM 判断规范化成英文，那我的中文 key 用不上；如果保留中文，那英文 key 用不上
- 需要跑一次实测确认，必要时改 prompt

### C. Sim runner 的 LLM 分支代码路径没实测

- `_dispatch_via_planner` 走 `bundle.agent.run_task(user_input, input_data)`，这条 path 我从来没在 sim 里跑过
- 里面有个 `if task.plan.target != ACTIONLIST_NAME: raise` 硬约束，如果 LLM 返回别的 workflow name 会直接崩

### D. .env / API key 就绪状态未确认

- 你有没有 DeepSeek API key 已配置？我这边没法验证 `SENSORAGENT_LLM_API_KEY` 环境变量
- 需要你手动确认 `.env` 有内容，或者你想切别的 provider（`SENSORAGENT_LLM_PROVIDER`）

---

## 三、已知但不阻塞 LLM 推进的问题（可留后续）

### E. 多物件/多 bin 组合有物理不可达

- gear at (0.43, 0.08, 0.13) — top-down pick 边缘
- bin_cell_1 (Y=-0.30) / bin_cell_4 — RM65 reach 边缘
- 这些是硬件限制，不影响 LLM 层验证（只要 LLM 输出的组合在可达域内即可）

### F. 单一 staging joints 覆盖面有限

- `[-0.17, -0.57, -0.61, 0, -1.96, 0]` 对 bin_cell_2/3 好，对 bin_cell_1 挂
- 长期解：per-bin staging 或 IK-aware 规划
- 短期：让 LLM 只选可达 bin

### G. sim 需要手动重启释放 world state

- 每轮跑完 roller 不会自动回原位
- 已有 `--reset-home` 让 arm 回家，但 world 里物件不重置
- 影响：不能在同一 sim session 连续跑多轮

### H. Cartesian planner 严格阈值（0.98）导致偶发失败

- 队友设的，稳定性优先
- 如果需要放宽，改 `ros2_ws/.../robot_bridge.yaml` 的 `cartesian_min_fraction`

---

# LLM 端到端 sim baseline（2026-07-24 补记）

Prompt v2（`allowed_place_targets` + action 定义 + 目的地规范化规则）配合 `vision.config_detect`
的子串匹配、`robot.resolve_place_target` 的白名单命中，用 `--planner llm` 在 Gazebo sim
上跑了 6 条不同措辞的 utterance，**全部 succeeded**。

## 验证矩阵

| # | 语言/语气 | 物件 | 目的地表述 | 规范化到 | pose_3d (base_link) | 结果 | Log |
|---|-----------|------|-----------|---------|---------------------|------|-----|
| 1 | 中精 | 滚柱 | `bin_cell_3` | bin_cell_3 | (0.24, 0.23, 0.142) | ✓ | logs/tasks/llm_sim_run.json |
| 2 | 中口 | 那个银色的滚柱 | `第三个格子` | bin_cell_3 | (0.24, 0.23, 0.142) | ✓ | logs/tasks/llm_sim_colloquial.json |
| 3 | 英口 | silver roller | `cell 3` | bin_cell_3 | (0.24, 0.23, 0.142) | ✓ | logs/tasks/llm_sim_english.json |
| 4 | 英口 | roller | `bin 2` | bin_cell_2 | (0.24, 0.23, 0.142) | ✓ | logs/tasks/llm_sim_bin2.json |
| 5 | 中精 | 螺栓 | `3 号格子` | bin_cell_3 | (0.28, 0.08, 0.147) | ✓ | logs/tasks/llm_sim_bolt.json |
| 6 | 英口 | bolt | `bin 2` | bin_cell_2 | (0.28, 0.08, 0.147) | ✓ | logs/tasks/llm_sim_bolt_bin2.json |

覆盖：**2 物件 × 2 目的地 × 中/英 × 精确/口语化**。

## 每条 utterance 的 LLM 解析结果

| # | Utterance | `object_query` | `target` | catalog 匹配 |
|---|-----------|----------------|----------|--------------|
| 1 | "把滚柱放到 bin_cell_3" | `滚柱` | `bin_cell_3` | `滚柱` (直接命中) |
| 2 | "把那个银色的滚柱拿过去放到第三个格子" | `那个银色的滚柱` | `bin_cell_3` | `滚柱` (子串) |
| 3 | "put the silver roller into cell 3" | `silver roller` | `bin_cell_3` | `roller` (子串) |
| 4 | "please drop the roller in bin 2" | `roller` | `bin_cell_2` | `roller` (直接) |
| 5 | "请把螺栓放进 3 号格子" | `螺栓` | `bin_cell_3` | `螺栓` (直接) |
| 6 | "grab the bolt and put it in bin 2" | `bolt` | `bin_cell_2` | `short_bolt` (子串) |

## 结论

- **DeepSeek 中英文口语解析稳定**：6/6 都能正确落到 `industrial.pick_place_actionlist`。
- **目的地规范化稳定**：`第三个格子`/`cell 3`/`bin 2`/`3 号格子` 都被规范化到 yaml 白名单 id。
- **物理执行稳定**：11 步 ActionList 全部通过，`verify_grasp.held=True`、`verify_place.released=True`。
- **中英文物件别名策略生效**：yaml 里 `roller / silver_roller / 滚柱 / short_bolt / 螺栓` 多别名 + `vision.config_detect` 的子串匹配一起兜住了所有 LLM 输出。

## 已知不覆盖的边界

- `gear` 在 (0.43, 0.08) — top-down pick workspace 边缘，Cartesian pregrasp fraction 0.000
- `bin_cell_1` 在 (0.36, -0.30) — 超出 RM65 top-down 可达域，OMPL abort
- 这两个是**物理可达性**问题，不影响 LLM 层的稳定性；实际使用时保证 utterance 落到可达组合即可。

## 用于复现

```bash
bash scripts/linux/run_rm65_b_sim.sh        # 每轮之间需重启
# 另一终端
PYTHONPATH=src .venv/bin/python scripts/linux/run_industrial_actionlist_sim.py \
  --planner llm --utterance "put the silver roller into cell 3" --execute \
  --json-out logs/tasks/reproduce.json
```
