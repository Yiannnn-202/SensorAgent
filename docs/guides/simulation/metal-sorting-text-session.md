# Gazebo 金属分拣文本会话全流程指引（跳过语音与视觉模型）

本文整理在 Gazebo 仿真中跑通金属零件分拣全流程的完整过程：
**跳过语音模块（文本输入代替）+ 跳过视觉模型（仿真物件坐标代替）**，
机械臂经 MoveIt 真实执行抓取与放置。

适用场景：没有麦克风/ASR 模型、没有视觉模型权重时验证整条任务链路；
也是当前最稳定的 config-detect sorting 基线。

对应 actionlist：`industrial.sorting_config_pick_place_actionlist`
对应配置：`configs/robot_sorting_sim.yaml`

## 快速开始（终端可直接执行）

```bash
# 0. 首次使用或仿真资源更新后，构建一次 ROS 工作区（只需一次）
cd ~/2026Summer/SensorAgent && bash scripts/linux/prepare_rm65_b_sim.sh

# 1. 后台启动 Gazebo metal 分拣仿真栈（Gazebo + MoveIt + robot bridge）
cd ~/2026Summer/SensorAgent
bash scripts/linux/run_industrial_sorting_metal_sim.sh > /tmp/gazebo_sim.log 2>&1 &

# 2. 等待 bridge 就绪（返回 {"success": true, ...} 即就绪，约 30-90 秒）
curl http://127.0.0.1:8765/health

# 3. 启动文本模式分拣会话（--execute 表示真实驱动机器人）
cd ~/2026Summer/SensorAgent
.venv/bin/python scripts/linux/run_industrial_sorting_session.py \
  --mode text --execute

# 4. 在会话提示符 `> ` 后输入中文指令，例如：
#    把滚轮放到2号格
#    把六角螺母放到5号格
#    把短螺栓放到3号格
#    （每轮执行约 1-3 分钟，期间 Gazebo 低于实时率属正常）

# 5. 结束会话
退出

# 6. 停止仿真栈
kill %1   # 或: pkill -f "ros2 launch"
```

**重要：每轮会话之间必须重启仿真栈。** 详见下文「已知限制」。

## 1. 系统组成

```text
终端输入（代替语音 ASR）
   │
   ▼
run_industrial_sorting_session.py  ── 解析中文指令（parse_sorting_command）
   │                                  别名归一（滚柱→滚轮、螺母→六角螺母等）
   ▼
AgentRuntime → actionlist（detect → plan_pick → pick → verify_grasp
   │            → resolve_place_target → plan_place → place → verify_place）
   ▼
vision.config_detect   ← 用配置文件里的仿真坐标代替视觉模型输出
robot.* / gripper.*    ← 经 HTTP bridge 驱动 MoveIt + Gazebo 真实执行
```

### 语音被替换的方式

- `--mode text` 会话从 **stdin 读中文指令**，替代麦克风 VAD/ASR
- 文本模式下 `audio.*` 工具与技能自动从注册表中移除
  （`prepare_session_config`），无需本地语音模型资产

### 视觉被替换的方式

- `vision.config_detect` 工具直接返回 `configs/robot_sorting_sim.yaml`
  中 `scene.objects` 预配置的物件位姿（即 Gazebo 场景中的真实坐标）
- 每类金属零件有 3 个实例（如 `metal_roller_01/02/03`），指令中的
  类别名（滚轮/六角螺母/短螺栓）映射到中心实例坐标
- 抓取参数（开度、朝向、放置高度）同样来自 `release_profiles` 配置

## 2. 前置条件

- Ubuntu 22.04 + ROS 2 Humble，已运行过 `prepare_rm65_b_sim.sh`
- 项目 `.venv`（Python 3.12），见仓库根 README
- Gazebo classic（ogre 渲染），WSL 下亦可运行但实时率较低
- bridge 默认监听 `http://127.0.0.1:8765`

## 3. 指令格式

支持的中文指令模式（`run_industrial_sorting_voice_sim.py` 中的
`parse_sorting_command`）：

| 指令示例 | 解析结果 |
|---|---|
| 把滚轮放到2号格 | object=滚轮, target=bin_cell_2 |
| 把螺母放到5号格 | 别名归一 → 六角螺母 |
| 把短螺栓放到三号格 | 中文数字自动转阿拉伯数字 |
| 状态 | 查看已注册工具/机器人状态（不动作） |
| 退出 / exit / q | 结束会话 |

可用目标格：`bin_cell_1` ~ `bin_cell_9`（3×3 料格）。

## 4. 会话输出与日志

每轮指令以 JSON 输出到 stdout（含 trace、command、result、error），
同时写入任务日志：

```text
logs/tasks/sorting_session_<UTC时间戳>.jsonl
```

指定日志路径：`--log-path logs/tasks/my_run.jsonl`

检查某轮是否真实夹住（看 `gripper.get_state` 的物理判定，而不是
verify_grasp 的结论）：

```bash
.venv/bin/python - <<'EOF'
import json, sys
path = sys.argv[1] if len(sys.argv) > 1 else "logs/tasks/sorting_session_latest.jsonl"
for line in open(path):
    r = json.loads(line)
    p = r.get("payload", {})
    if not isinstance(p, dict):
        continue
    if r.get("event") == "agent_request_finished":
        res = p.get("result") or {}
        print("TURN:", p.get("success"), "| err:", p.get("error"))
    if r.get("event") == "tool_call_finished" and p.get("tool") == "gripper.get_state":
        st = (p.get("output") or {}).get("state", {})
        print("  gripper物理: grasped=%s status=%s opening=%.4f" % (
            st.get("grasped"), st.get("status"), st.get("opening", 0)))
EOF
```

`grasped=True` 表示 Gazebo 物理层确认夹爪被物件顶住（真空抓）；
`grasped=False, status=closed` 表示夹爪无阻挡合到位（空抓）。

## 5. 机械臂复位（会话中途失败后）

某轮 MoveIt 规划失败可能让 arm 停在 `error` 状态，下轮开始前先复位：

```bash
# 取消可能残留的 active goal，再回 home
curl -s -X POST http://127.0.0.1:8765/stop -H 'Content-Type: application/json' -d '{}'
sleep 3
curl -s -X POST http://127.0.0.1:8765/move-joints \
  -H 'Content-Type: application/json' \
  -d '{"joints":[0,0,0,0,0,0],"speed":0.3,"wait":true}'
curl -s http://127.0.0.1:8765/state   # 确认 "status": "idle"
```

若 home 规划也偶发失败，等几秒重试一次（RRTConnect 随机性，非故障）。

## 6. 已验证结果（2026-08-24）

在重启场景后的新鲜状态下一轮三连指令：

| 指令 | 物理夹持 | 放置 | 结果 |
|---|---|---|---|
| 滚轮→2号格 | grasped=True | 成功 | success |
| 六角螺母→5号格 | grasped=True | 成功 | success |
| 短螺栓→3号格 | grasped=True | 成功（释放后撤退曾被误判，已修复）| success |

## 7. 已知限制与坑

1. **死坐标会过期**：`config_detect` 返回的是配置写死的坐标。物件被
   抓走后再次对同类发指令，会到原坐标空抓。现象与处理：
   - 好消息：`verify_grasp` 以 bridge 物理判定为准，空抓会被
     `grasp not detected (grasped=False, ...)` 拦截，**不会**假成功
   - 正确做法：**每轮会话前重启仿真栈**复位物件位置
2. **MoveIt 规划偶发失败**：OMPL RRTConnect 是随机采样规划器，同样
   请求时成时败。失败重试通常即可；`move_pre_approach_joints` 失败
   多属此类，非代码问题
3. **WSL/低实时率**：Gazebo 低于实时运行时单轮执行时间显著拉长，
   bridge 超时已放宽到 720s，耐心等待即可
4. **渲染**：默认 ogre；如需换渲染引擎在启动命令后加
   `render_engine:=<engine>`

## 8. 本流程验证过程中修复的问题（背景）

全流程联调时发现并修复了三处（均已合入分支并有单测覆盖）：

1. **place 笛卡尔/关节回退容错**：`move_place`/`post_release_lift`/
   `retreat` 遇 `INCOMPLETE_CARTESIAN_PATH` 回退 `move_pose`；
   `retreat_joints` 失败回退 lifted retreat 位姿（对齐 pick 技能既有模式）
2. **释放后撤退失败容忍**：物件已释放进格子后，撤退动作失败不再
   否定放置结果，仅记录 `tolerated_failures`
3. **verify_grasp 空抓假阳性**：bridge 报 `grasped=False` 时不再被
   opening 区间启发式覆盖，空抓当场拦截
