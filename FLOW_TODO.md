# 流程闭环改进 TODO

本文只跟踪流程层面的高分补强任务，不覆盖视觉检测指标、模型训练指标或实机硬件调试细节。

## 目标

把当前系统从“能串起一次任务链”提升为：

```text
感知更新状态 -> 状态驱动决策 -> 决策改变动作 -> 执行后再感知验证 -> 失败后有针对性恢复
```

## P0 - 恢复策略真实生效

### 1. 消费 `recovery.plan.updated_input`

- [ ] 设计统一的 recovery context 合并规则，明确 `updated_input` 如何覆盖或补充后续节点输入。
- [ ] 让 `RETRY_WITH_EXPANDED_VISION` 影响下一次 detect：如 `recapture_frame`、`depth_window_delta`、`min_confidence_delta`。
- [ ] 让 `RETRY_PICK_ORIENTED` 真实切换到 `robot.plan_oriented_pick`，或在缺少点云时明确降级并记录原因。
- [ ] 让 `RETRY_PICK_ADJUSTED_GRASP` 影响下一次 pick：如 `close_opening_delta`、`position_offset_candidates`。
- [ ] 让 `RETRY_PLACE_CANDIDATES` 影响下一次 place：如候选 release pose、clearance delta。
- [ ] 让 `REPICK_FROM_OBSERVED_POSE` 使用实际观测到的错误位置或掉落位置，而不是重新使用原始配置位姿。

**验收标准：**

- [ ] 每类 recovery strategy 至少有一个测试证明 `updated_input` 改变了后续 Tool/Skill 的实际输入。
- [ ] 日志中能看到 recovery 前后的输入差异。
- [ ] 对同一失败注入场景，恢复后执行路径和普通重跑路径不同。

## P0 - 统一世界状态成为闭环中枢

### 2. 定义并接入流程状态更新点

- [x] 在 `DecisionTreeRuntime` 中接入轻量 run-local `world_state`，记录 objects、bins、current_task、history。
- [x] detect 成功后写入 object pose、confidence、source、timestamp。
- [x] pick / verify_grasp 成功后写入 held object 状态。
- [x] verify_place / verify_object_in_bin 后写入 released / placed / bin occupancy 状态。
- [x] recovery classify / plan 后写入 failure type、strategy、applied overrides。
- [ ] 扩展持久化 `CompetitionWorldState`，让 session/world state 与 DecisionTree run-local state 合并。
- [ ] recovery 后写入 observed new pose，并让掉落/放错格重抓使用该 pose。

**验收标准：**

- [ ] 一次完整任务的 `world_state.history` 能还原 detect -> pick -> place -> verify -> recovery 的状态变化。
- [ ] 后续 plan 使用 world state 中的最新 pose/bin occupancy，而不是只使用初始配置输入。
- [ ] 放错格、掉落、未抓住三类失败能在 world state 中留下不同状态。

## P1 - 多实例与批量任务进入主流程

### 3. 打通 `quantity == all` 和多实例任务队列

- [ ] 将 `grounding.py` 中 `BATCH_TASK_NOT_ENABLED` 改为生成可执行的 batch intent，或新增专门 batch workflow。
- [ ] 支持“所有某类零件依次入格”。
- [ ] 支持“第 N 个 / 左侧 / 右侧 / 最近 / 最远”实例选择。
- [ ] 支持自动选择下一个空格。
- [ ] 支持已放置实例从候选集中排除。

**验收标准：**

- [ ] “把所有滚轮依次放入空格”能生成多步任务队列。
- [ ] 每个子任务执行后 world state 更新，下一子任务不会重复选择已放置零件。
- [ ] 任务中途失败时能记录剩余队列和失败对象。

### 4. 支持“最多区域装箱”的最小版本

- [ ] 定义区域表达，例如 `left_area`、`right_area`、`front_area`、`back_area` 或网格区域。
- [ ] 根据当前感知/配置统计每个区域的可抓取实例数量。
- [ ] 选择数量最多区域并生成装箱子任务队列。

**验收标准：**

- [ ] “把零件最多的区域装箱”不再被拒绝。
- [ ] 日志中记录区域计数、被选区域和任务队列。

## P1 - live RGB-D 链路成为主流程可选模式

### 5. 统一 config-detect 与 live-perception 流程接口

- [ ] 统一 `vision.config_detect` 与 `vision.open_vocab_detect` 的输出字段，使下游不关心来源。
- [ ] 为 `industrial.sorting_config_pick_place_actionlist` 增加 live perception 对应版本或参数化 detect tool。
- [ ] 在 recovery tree 中确保 live detect、live verify、world state 更新三者一致。

**验收标准：**

- [ ] 同一条 pick/place workflow 可在 config-detect 和 live RGB-D 两种模式下运行。
- [ ] 两种模式输出相同结构的 object state 和 task log。
- [ ] live 模式下 post-place verify 使用真实观测，不使用 commanded pose 伪验证。

## P1 - 高阶恢复动作落地

### 6. 让典型失败恢复有实际动作差异

- [ ] 未抓住：调整抓取高度、夹爪闭合宽度或抓取偏移后重试。
- [ ] 掉落：重新检测掉落位置，从新 pose 重新 pick。
- [ ] 放错格：从错误格观测位置重抓，保持原目标格不变。
- [ ] 释放失败：低速重开夹爪，必要时 retreat 后再验证。
- [ ] pose invalid：重新采集 RGB-D，扩大 depth window 或换候选。

**验收标准：**

- [ ] 每类失败有一个单元测试或脚本注入场景。
- [ ] 每类恢复后的动作输入与失败前不同。
- [ ] 恢复过程在报告日志中可解释。

## P2 - 轻量多 Agent / 多执行体协同展示

### 7. 先实现任务分工，不急于多机械臂

- [ ] 定义多 Agent 角色：如 `planner_agent`、`picker_agent`、`placer_agent`、`verifier_agent`，或 `area_a_agent`、`area_b_agent`、`carrier_agent`。
- [ ] 定义共享任务队列和状态锁，避免两个角色选择同一零件或同一格子。
- [ ] 支持把“所有零件装箱”拆成多个角色可执行的子任务。
- [ ] 日志记录任务分配、状态交接、冲突避免和完成情况。

**验收标准：**

- [ ] 有一个无需多机械臂的多 Agent 调度演示：多个角色串行/模拟并行处理同一任务队列。
- [ ] 日志中能看到不同角色的输入、输出和状态交接。
- [ ] 报告中能清楚说明这是多 Agent 协同接口/调度层验证，而不是多物理机械臂验收。

## P2 - 流程指标自动汇总

### 8. 从真实运行日志生成流程指标

- [ ] 将 ActionList / DecisionTree / session logs 自动转换为 `RunRecord`。
- [ ] 支持 planner 指标：parse accuracy、sequence validity、missing slot、ambiguity rejection。
- [ ] 支持 workflow 指标：end-to-end success、recovery triggered rate、recovery success rate、avg recovery cost。
- [ ] 支持 failure 指标：failure type distribution、strategy distribution、branch coverage。

**验收标准：**

- [ ] 一条命令能从一批任务日志生成 `results.jsonl` 和 `summary.json`。
- [ ] summary 中不再出现 planner 指标恒为 0 的情况，除非明确是 bypass-planner batch。
- [ ] 报告可直接引用 summary 表格。

## 建议实施顺序

1. P0-1：让 `recovery.plan.updated_input` 真实生效。
2. P0-2：统一世界状态更新点。
3. P1-3：支持多实例任务队列。
4. P1-6：补典型失败恢复动作差异。
5. P1-5：统一 config 与 live RGB-D 流程接口。
6. P2-8：从真实日志自动汇总流程指标。
7. P2-7：补轻量多 Agent 调度展示。
