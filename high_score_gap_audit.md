# SensorAgent 冲高分差距审阅报告

时间：2026-08-13 18:15:54 +08:00

## 审阅范围

本轮按模块审阅了仓库核心源码、配置、脚本、测试和本地结果产物：

- `src\sensoragent\**\*.py`：Agent、Planner、Grounding、Tool/Skill、Workflow、Recovery、Evaluation、Audio、Robot、Vision、State、CLI。
- `configs\*.yaml`：mock、robot sim、sorting sim、audio、vision、training/eval 配置。
- `scripts\**\*.py`：Gazebo、RGB-D capture、sorting session、dataset collection、vision train/eval。
- `tests\**\*.py`：unit/e2e/ros2 覆盖面。
- `ros2_ws\src\**`：HTTP bridge、MoveIt/Gazebo bringup、gripper bridge、planning scene。
- `runs\vision\train\...` 代表性训练/评测摘要。
- 根目录 README/TODO/architecture 与赛题文件理解稿。

验证结果：

```text
python -m unittest discover -s tests -p 'test_*.py'
Ran 308 tests in 5.697s
OK (skipped=1)
```

另运行当前 competition batch：

```text
run_count=5
end_to_end_success_rate=1.0
recovery.success_rate=1.0
branch_coverage=4/19 = 0.210526
planner.parse_accuracy=0.0
planner.sequence_validity=0.0
```

解释：batch 是 fake-backend + 注入故障，不是 Gazebo/实机验收；指标框架可用，但当前样本集太小、planner 没纳入 batch。

## 总体判断

仓库目前已经不是“概念 demo”，而是一个比较完整的 **仿真导向工业交互智能体框架**。最强的部分是：Agent/Tool/Skill/ActionList/DecisionTree 架构、失败分类与恢复、机器人执行抽象、Gazebo/MoveIt bridge、视觉训练/评测工具链。

距离 90 分的主要差距不在“没有代码”，而在 **证据不足与闭环验收不足**：

1. 真实/仿真工业感知指标还不够高，且数据集规模偏小。
2. 端到端 Gazebo/实机批量成功率还没有形成正式报告。
3. 世界状态主要是 oracle/config 级别，尚未和 live perception 持久融合。
4. 多实例、高阶任务、倒放/倾倒姿态调整还没有成为稳定主链。
5. 多 Agent 协同尚未形成可展示能力；当前是单 Agent 编排 Tool/Skill/Workflow，最终需要体现多任务/多区域/多执行体协同调度能力。
6. 实机实施如果已经在做，需要把相机标定、接口、成功率、失败案例和视频证据回填到仓库/报告体系。

## 按赛题评分项的差距

### 1. 方案创新性与完整性：当前约 28-31 / 35

强项：

- `src\sensoragent\agent\runtime.py` 已有任务生命周期、Planner、workflow dispatch。
- `src\sensoragent\workflows\actionlists\runtime.py` 和 `decision_trees\runtime.py` 实现可执行 ActionList/DecisionTree。
- `src\sensoragent\workflows\decision_trees\industrial.py` 的恢复树覆盖 detect、plan-pick、pick、verify-grasp、place、verify-place、vision verification、failure classification、recovery planning。
- `src\sensoragent\recovery\detector.py` 和 `planner.py` 定义 19 类失败与策略。
- `src\sensoragent\grounding.py` 支持中文/英文类别别名、格子解析、空间选择、oracle instance resolver。

差距：

- 多智能体协同目前基本没有代码实现。
- “所有零件/最多区域装箱”被显式拒绝：`grounding.py` 对 `quantity == "all"` 返回 `BATCH_TASK_NOT_ENABLED`。
- 高阶任务的“区域数量判断、循环装箱、箱满搬运、倒放姿态纠正”没有成为系统主链。
- 多 Agent 最终需要体现，但不一定第一步就上多个物理机械臂；更现实的前置形态是把 A 区/B 区/搬运/装箱拆成可分配的子任务队列，再展示这些子任务可以由不同 Agent 或执行体承接。
- DecisionTree 恢复很完整，但 `RecoveryPlanner.updated_input` 多数只是报告性策略，真实恢复树并没有完全消费所有 updated_input 参数，例如 oriented pick 切换、candidate offsets、observed dropped pose 等还没有完整落地。

90 分需要：

- 至少支持一个高阶任务闭环：如“把左侧/最多区域的三个零件依次放入指定格/空格”。
- 把“批量/多实例任务”从 `BATCH_TASK_NOT_ENABLED` 提升到可运行，哪怕先是 oracle/config + Gazebo。
- 增加一个轻量多 Agent/多执行体调度演示：例如把“所有零件装箱”拆为区域拣选 Agent、装箱执行 Agent、搬运/复核 Agent 的任务分工，并用日志证明调度、状态交接和冲突避免。
- 将恢复计划里的策略真正影响下一次 detect/plan/pick/place，而不是只作为日志。

### 2. 技术实现质量：当前约 22-27 / 35

#### 2.1 视觉感知与定位

强项：

- `src\sensoragent\tools\vision\open_vocab.py` 实现开放词汇检测、Grounding DINO/YOLOE 后端、SAM2 mask refinement、RGB-D 深度反投影、`T_base_camera` 到 `base_link`。
- `vision.grounded_sam2` strict tool 已实现。
- `scripts\vision_dataset_audit.py`、`scripts\vision_train_grounding_dino.py`、`scripts\vision_eval.py`、`src\sensoragent\evaluation\vision.py` 构成较完整的训练/评测链。
- 本地有多类零件训练/评测产物。

当前视觉结果证据：

Grounding DINO unified v1 test：

```text
image_count=10
gt_instances=42
precision=0.400000
recall=0.285714
f1=0.333333
mean_box_iou_matched=0.892727
mean_mask_iou_matched=0.855164
mean_center_error_px_matched=1.527242
latency mean≈361ms, p95≈484ms
```

YOLOE object_mask_2_v0 test：

```text
image_count=10
gt_instances=42
precision=0.176471
recall=0.071429
f1=0.101695
mean_box_iou_matched=0.770706
mean_mask_iou_matched=0.691378
```

结论：

- 匹配上的 box/mask 质量不错，但 recall 太低，不足以支撑 90 分。
- 数据规模偏小：train 70 / val 20 / test 10，test 42 instances。
- 没有负样本，泛化和误检控制证据不足。
- RGB-D 3D 位置误差和 `base_link` 标定误差还没有形成正式指标。

90 分需要：

- 固定比赛 test set，至少覆盖 3-5 类工业零件、正常/倒放/倾倒、密集/反光/遮挡、多实例、负样本。
- 目标建议：检测/分割层面至少 `recall >= 0.75`，`precision >= 0.75`，mask IoU/box IoU 可维持高水平；如果用 scene-aware/候选过滤，要报告过滤前后。
- RGB-D 坐标误差：报告相机坐标和 base_link 坐标误差，建议至少给出平均/中位/P95，目标可先定 `mean <= 2cm`、`P95 <= 5cm`。
- 每个模型版本要有 checksum、数据 split、阈值选择依据、失败样例。

#### 2.2 抓取与执行

强项：

- `robot.plan_top_down_pick`、`robot.plan_oriented_pick`、`robot.pick`、`robot.place` 完整。
- `ros2_ws\src\sensoragent_robot_bridge\bridge_node.py` 实现 HTTP 到 MoveIt/Cartesian/GripperCommand。
- `scene_obstacles.py` 已把相机架、工作台、3x3 料箱加入 MoveIt planning scene。
- sorting config 有 3 类 9 个实例、3x3 bin、类别抓取开口/姿态。

差距：

- 主链仍以配置位姿和 top-down grasp 为主；任意姿态抓取还不是视觉估计。
- `robot.plan_oriented_pick` 需要 base-frame point cloud，但视觉 mask/depth -> point cloud -> oriented pick 未接入主链。
- Gazebo 接触/摩擦/抓取稳定性验收还未形成默认自动测试。
- 实机如果已实施，需要把控制接口、坐标系、急停/限速/安全边界、成功率写成可审查材料。

90 分需要：

- 给出 30-100 次 Gazebo 抓放统计，按类别和失败类型分布。
- 至少演示并统计：滚轮/螺母/短螺栓三类各若干次。
- 对倒放/倾倒任务，至少实现“状态识别 + 放置姿态调整”的可解释策略。
- 实机链路要有相机标定与坐标对齐报告，不能只有视频。

#### 2.3 决策与恢复

强项：

- 失败类型和恢复策略设计明显贴合赛题。
- 当前 fake competition batch 能跑出 recovery metrics。
- `industrial.recovery_pick_place_tree` 支持 live capture/live verify 模式。

差距：

- 当前 batch fixture 只有 5 个场景、4 种失败，branch coverage 只有 21%。
- batch 没纳入 planner；`planner.parse_accuracy=0`，因为直接跑 tree。
- skill-level 注入还留在代码注释中“later stage”，如 GRASP_EMPTY via `robot.verify_grasp`。
- `terminal_failure_distribution` 对 recovered runs 仍显示 failure_type，报告语义需修正，否则评审会看混。

90 分需要：

- 固定任务集：标准指令、同义表达、缺目标、歧义、多实例、非法目标、错误类别。
- 固定失败集：目标缺失、低置信度、pose invalid、pick plan failed、未抓住、途中掉落、放错格、释放失败、bridge not ready。
- 指标：指令槽位准确率、序列有效率、端到端成功率、恢复触发率、恢复成功率、恢复收益、平均恢复成本。
- 把 batch 从 fake injection 扩展到 Gazebo reset + real execution + log reducer。

### 3. 系统集成与工程可用性：当前约 13-16 / 20

强项：

- 308 个测试通过，说明基础工程质量不错。
- configs/contracts/logging/CLI/scripts 完整。
- ROS bridge 和 Gazebo/MoveIt 结构清晰。
- `requirements.txt`、`requirements-vision.txt`、pyproject 明确。

差距：

- README 仍写 physical robot not connected、batch simulation not implemented，和你说“实机已实施”之间需要同步。
- `src\sensoragent\services\api\__init__.py` 为空，线上/前端/API 服务不是重点但会影响“系统感”。
- 没有 Docker 或统一一键复现实验包。
- ROS/Gazebo 自动验收没有进默认 suite。
- 本地模型/数据在 `models/`、`runs/`、`data/`，但许多产物没有形成正式提交/报告引用路径。

90 分需要：

- 一个顶层 `make`/脚本式流程：启动仿真、采集、运行任务、导出 metrics。
- 最终报告能引用固定路径的 `summary.json`、`results.jsonl`、视频片段和日志。
- 如果实机已做，把“实机运行说明、硬件拓扑、相机外参、真实运行日志、失败处理”补进 docs。

### 4. 文档与展示：当前约 7-8 / 10

强项：

- README、architecture、competition-plan、vision docs 很多。
- 已经有赛题理解和视频文案。
- 文档对边界比较诚实，避免夸大。

差距：

- 技术报告还缺最终指标表。
- 视频文案有一些“待补充”和可能过度表述，例如真实工厂试用/实机完整闭环，需要根据证据校准。
- 高分展示需要“同一任务成功、失败、恢复”的连贯证据，而不仅是功能介绍。

90 分需要：

- 最终报告按赛题评分项组织，而不是按代码模块堆叠。
- 每个创新点后面必须跟代码路径、实验编号、指标或视频时间戳。
- 给出失败案例分析：为什么失败、系统如何分类、如何恢复、恢复是否成功。

## 分方向成熟度判断

| 方向 | 当前等级 | 冲 90 分差距 |
| --- | --- | --- |
| Agent 架构与工作流 | L2+ | 需要高阶任务和 planner batch 指标 |
| 指令理解/语音交互 | L2- | 需要固定指令集准确率、歧义/缺参评测、真实语音噪声测试 |
| 视觉检测/分割 | L2- | 当前 recall 不足，数据规模小，负样本和复杂场景不足 |
| RGB-D 三维定位 | L1+~L2- | 代码有，缺相机/实机标定误差报告 |
| 抓取位姿与规划 | L2- | top-down 配置强，视觉任意姿态/点云抓取未接主链 |
| Gazebo/MoveIt 执行 | L2- | bridge 与脚本完整，缺 repeatable reset + batch acceptance |
| 失败恢复 | L2+ 设计，L2- 实证 | tree 完整，batch 覆盖少，部分 recovery strategy 未真实消费 |
| 世界状态 | L1+ | oracle task-local；缺 live perception durable fusion |
| 多 Agent 协同 | L0~L1 | 目前是单 Agent 编排；最终需展示多区域/多任务分工、状态交接和冲突避免 |
| 实机迁移 | 仓库证据 L0~L1 | 你们若已实施，需要把接口、标定、日志、视频、指标回仓 |
| 工程复现 | L2- | 测试强，但 Docker/一键验收/ROS acceptance 还缺 |

## 最关键的 10 个补强任务

1. **把实机证据回填仓库**：新增 docs/real_robot 或 reports，记录硬件、相机、外参、接口、实机视频、成功/失败日志。
2. **冻结比赛任务集**：至少 20-50 条文本/语音指令，覆盖标准、同义、空间关系、缺参、歧义、错误类别。
3. **把 planner 纳入 batch**：不要只直接跑 tree；要统计 parse accuracy、sequence validity。
4. **扩展 competition scenarios**：从 5 个扩到 20+，覆盖至少 10 类失败/恢复。
5. **Gazebo 自动重置与批量执行**：让 `collect_randomized_sorting_dataset.py` / reset 能服务端到端任务，不只是数据采集。
6. **视觉 recall 补强**：当前 Grounding DINO test recall 0.286，不够高分；继续数据增强/阈值/模型训练/候选选择。
7. **RGB-D 标定误差报告**：对真实/仿真样本输出 camera/base 坐标误差。
8. **mask/depth 到 oriented pick**：打通 `mask -> point cloud -> robot.plan_oriented_pick`，支撑“抓取位姿”加分。
9. **真实恢复闭环视频**：至少一个放错格/未抓住/掉落后重新感知并修正的完整视频。
10. **补一个轻量多 Agent 协同展示**：先不追求复杂多机械臂，可实现任务分解为多个角色队列，例如区域拣选、装箱执行、搬运/复核，并通过世界状态避免同一零件/同一格子冲突。
11. **最终报告证据矩阵**：每个评分点对应代码路径、实验结果、视频、日志，不留“口头说明”。

## 当前最适合冲高分的路线

短期不要再扩新框架，应该把已有框架变成可评分证据：

```text
固定任务集
-> 固定 Gazebo/实机场景
-> 固定视觉 test set
-> 批量运行
-> 导出 summary.json/results.jsonl
-> 技术报告表格
-> 视频按“正常任务 + 失败恢复 + 实机迁移”剪辑
```

如果只按现仓库证据评分，我会认为已经有 75-82 分的工程基础；若补齐上面的量化闭环和实机证据，有机会冲 88-92。最大扣分风险是视觉 recall、批量验收和实机证据没有沉淀成可复查材料。
