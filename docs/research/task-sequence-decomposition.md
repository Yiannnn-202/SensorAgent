# 任务序列分解调研简稿

## 1. 现状简述：Introduction

赛题 `XH-202607_工业环境下物体感知识别与指令交互型智能体研发` 中的任务序列分解，不是简单把自然语言改写成文字步骤，而是要把“把某个工业零件放到指定位置”转化为机器人可执行、可验证、可恢复的作业流程。

核心评分点之一是：

```text
任务序列分解的合理性与执行成功率（是否符合机器人作业逻辑）（10 分）
```

因此方案需要同时证明：

1. 分解出的步骤是否符合机器人作业逻辑；
2. 分解结果是否能真实驱动识别、抓取、放置和验证；
3. 摆放失败后是否能自主检测并重新处理。

## 2. 各方法代表方案：Related Work

| 方法类别 | 具体代表方案 | 团队/组织与引用情况 | 可作为基线的原因 |
| --- | --- | --- | --- |
| Plan-and-Execute Agent | LangGraph Plan-and-Execute | LangChain / LangGraph 官方开源框架与官方示例 | 通用 LLM 任务分解和执行框架，可作为“通用 Agent 分解”基线 |
| LLM + 可执行性评分 | SayCan | Google Research / Everyday Robots，CoRL 2022，论文 *Do As I Can, Not As I Say* | 用语言模型生成候选动作，再用 affordance 判断动作能否执行，适合机器人任务规划基线 |
| LLM + PDDL + 行为树 | H-AIM / EmboTeam | 中国科学院等团队，2026 arXiv，*Orchestrating LLMs, PDDL, and Behavior Trees for Hierarchical Multi-Robot Planning* | 级联使用 LLM、PDDL 和行为树，和本赛题“语言理解-任务分解-可恢复执行”最接近 |
| HTN 层级任务规划 | ChatHTN | Munoz-Avila、Aha、Rizzo，PMLR / NeuS 2025，官方 GitHub 开源 | 将 LLM 与 HTN 符号规划结合，强调层级分解、方法复用和计划验证 |
| LLM 生成行为树 | BTGenBot | AIRLab, Politecnico di Milano，IROS 2024，官方 GitHub 开源 | 将自然语言任务转换为机器人行为树，适合作为“LLM + 行为树”可复现基线 |
| 行为树执行框架 | BehaviorTree.CPP / ROS 2 Nav2 | BehaviorTree.CPP 开源项目；ROS 2 Nav2 使用其作为导航行为树执行引擎 | 行为树在机器人中广泛用于条件检查、重试和失败恢复 |

这些方案各有侧重：LangGraph 适合通用任务编排，SayCan 强调动作可执行性，ChatHTN 强调层级分解的理论严谨性，H-AIM/EmboTeam 和 BTGenBot 更接近“LLM + 形式化规划 + 行为树执行”的机器人任务分解路线。

## 3. 我们的方案

我们的方案在包装上建议主要基于 **H-AIM / EmboTeam 所代表的“LLM + PDDL + Behavior Tree”级联式具身任务规划框架**，同时以 **BTGenBot** 作为可复现的“LLM 生成行为树”工程参考。

这样选择更有说服力：

```text
H-AIM / EmboTeam 是 2026 年提出的 LLM + PDDL + 行为树级联框架；
SayCan 是 Google Research / Everyday Robots 的机器人可执行性规划代表方案；
ChatHTN 是 2025 年发表并开源的 LLM + HTN 层级任务规划方案；
BTGenBot 是 IROS 2024 的开源 LLM 行为树生成方案；
BehaviorTree.CPP / Nav2 是机器人行为树执行与恢复的成熟工程基座。
```

也就是说，我们不是单独声称“基于某个小众项目”，而是将方案表述为：

```text
以 H-AIM 类 LLM-PDDL-BT 级联规划为理论主参考，
以 BTGenBot / BehaviorTree.CPP 为行为树生成与执行参考，
以 SayCan 和 ChatHTN 分别补充可执行性约束与层级分解依据。
```

基础方法选择理由：

```text
赛题明确要求失败检测和重新处理；
行为树 / DecisionTree 天然支持条件节点、恢复分支和重试；
H-AIM / EmboTeam 已展示 LLM、PDDL 和行为树级联用于具身多机器人任务规划；
BTGenBot 已证明 LLM 可用于从自然语言生成机器人行为树；
因此本项目以受约束 LLM + 层级任务分解 + 行为树式执行图作为主线。
```

针对本赛题，我们做以下定制优化：

| 定制点 | 说明 |
| --- | --- |
| 受约束 LLM 输出 | LLM 不直接控制机器人，只能生成符合 Schema 和能力白名单的任务结构 |
| HTN 风格层级分解 | 将“放入指定格”拆成感知、目标选择、抓取、抓取验证、放置、放置验证、恢复 |
| SayCan 式可执行性检查 | 每一步执行前检查目标是否存在、位姿是否可用、机器人是否可达、技能是否注册 |
| DecisionTree/BT 恢复执行 | 将任务表达为带条件和失败分支的执行图，而不是一次性 ActionList |
| 视觉验证闭环 | 抓取后验证是否抓住，放置后验证是否进入指定格，不能只相信控制器返回成功 |
| 分类恢复策略 | 区分目标不存在、规划失败、未抓住、途中掉落、放错格等失败类型并采取不同恢复动作 |

最终任务流程：

```text
自然语言指令
→ 结构化解析
→ 感知与世界状态更新
→ 受约束层级任务分解
→ DecisionTree / BehaviorTree 执行
→ 抓取与放置验证
→ 失败分类恢复
→ 输出任务结果和日志
```

## 4. 实验验证

### 4.1 重要验证指标

| 指标 | 含义 |
| --- | --- |
| 任务序列有效率 | 通过 Schema、能力白名单、前置条件和安全约束检查的任务序列比例 |
| 机器人逻辑一致率 | 步骤顺序是否符合“先感知、再规划、再抓取、再验证、再放置”的机器人作业逻辑 |
| 端到端成功率 | 从指令输入到目标物体进入指定格的成功比例 |
| 失败恢复成功率 | 发生抓取失败、放错格等异常后，经恢复最终成功的比例 |
| 平均任务耗时 | 完成一次任务所需时间，用于衡量恢复策略的额外代价 |

### 4.2 对比方案

| 编号 | 对比方案 | 来源 | 对比目的 |
| --- | --- | --- | --- |
| B0 | 固定 ActionList | 本项目已有工作流 | 验证无智能分解、无复杂恢复时的基础表现 |
| B1 | LangGraph Plan-and-Execute | LangChain / LangGraph | 对比通用 LLM 分解框架 |
| B2 | SayCan-style Planner | Google Research / Everyday Robots | 对比“LLM 候选动作 + 可执行性评分”路线 |
| B3 | ChatHTN-style Planner | ChatHTN / PMLR NeuS 2025 | 对比 HTN 层级分解路线 |
| B4 | BTGenBot-style Planner | AIRLab Politecnico di Milano / IROS 2024 | 对比 LLM 生成行为树路线 |
| Ours | 受约束 LLM + HTN 思想 + BT/DecisionTree + 视觉验证恢复 | 本项目定制 | 验证赛题定制优化是否提升合理性和成功率 |

### 4.3 实验方式

实验任务围绕工业分拣入格场景设计：

```text
把滚柱放到第三个格子
把螺母放到第一个格子
把齿轮放到中间格
把指定颜色/形状的零件放入指定料箱格
```

测试维度：

| 维度 | 设计 |
| --- | --- |
| 物体类别 | 滚柱、螺母、齿轮、法兰等 4～6 类工业零件 |
| 目标位置 | 料箱不同格子，覆盖角落、边缘和中心 |
| 场景难度 | 单目标、多目标混杂、遮挡、目标缺失 |
| 失败注入 | 目标不存在、路径规划失败、抓取失败、放错格 |

验证流程：

```text
1. 每个方案接收同一批自然语言任务；
2. 记录其生成的任务序列；
3. 自动检查任务序列有效率和机器人逻辑一致率；
4. 在 mock 或 Gazebo 中执行任务；
5. 注入典型失败并记录恢复情况；
6. 汇总端到端成功率、失败恢复成功率和平均耗时。
```

报告结果表：

| 方案 | 任务序列有效率 | 机器人逻辑一致率 | 端到端成功率 | 失败恢复成功率 | 平均耗时 |
| --- | ---: | ---: | ---: | ---: | ---: |
| B0 固定 ActionList | 待测 | 待测 | 待测 | 待测 | 待测 |
| B1 LangGraph Plan-and-Execute | 待测 | 待测 | 待测 | 待测 | 待测 |
| B2 SayCan-style | 待测 | 待测 | 待测 | 待测 | 待测 |
| B3 ChatHTN-style | 待测 | 待测 | 待测 | 待测 | 待测 |
| B4 BTGenBot-style | 待测 | 待测 | 待测 | 待测 | 待测 |
| Ours | 待测 | 待测 | 待测 | 待测 | 待测 |

## 5. 总结

本项目的任务序列分解方案不采用纯 LLM 直接生成动作序列，而是以 **H-AIM / EmboTeam 所代表的 LLM + PDDL + Behavior Tree 级联路线** 为理论主参考，并融合：

```text
LangGraph 的计划-执行思想
SayCan 的可执行性约束思想
ChatHTN 的层级任务分解思想
BTGenBot 的 LLM 生成行为树思想
BehaviorTree.CPP / Nav2 的行为树恢复执行思想
```

最终形成面向本赛题工业分拣任务的定制方案：

```text
受约束 LLM + HTN 风格分解 + DecisionTree/BehaviorTree 执行图 + 视觉验证恢复
```

该方案的目标是同时提升“任务序列分解合理性”和“执行成功率”，并通过与 LangGraph、SayCan、ChatHTN、BTGenBot 等代表性方案的对比实验，支撑评分表中 10 分得分点的论证。

## 6. 参考来源

| 方案 | 引用或来源 |
| --- | --- |
| LangGraph Plan-and-Execute | LangChain / LangGraph 官方 GitHub 与官方 Plan-and-Execute 示例 |
| SayCan | Brohan et al., *Do As I Can, Not As I Say: Grounding Language in Robotic Affordances*, CoRL 2022 |
| H-AIM / EmboTeam | Zeng and Li, *H-AIM: Orchestrating LLMs, PDDL, and Behavior Trees for Hierarchical Multi-Robot Planning*, arXiv 2026 |
| ChatHTN | Munoz-Avila, Aha, Rizzo, *ChatHTN: Interleaving Approximate (LLM) and Symbolic HTN Planning*, PMLR / NeuS 2025；官方 GitHub: `hhhhmmmmm02/ChatHTN` |
| BTGenBot | Izzo, Bardaro, Matteucci, *BTGenBot: Behavior Tree Generation for Robotic Tasks with Lightweight LLMs*, IROS 2024；官方 GitHub: `AIRLab-POLIMI/BTGenBot` |
| BehaviorTree.CPP / Nav2 | BehaviorTree.CPP 官方开源项目；ROS 2 Navigation2 使用 BehaviorTree.CPP 组织导航与恢复行为 |
