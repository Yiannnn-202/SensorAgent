# Gazebo 随机抓取基准：问题与解决方案总结

本文整理金属分拣随机抓取基准（`run_sorting_success_rate.py`）开发与两轮
12 次试跑中碰到的问题、根因分析和解决方案，作为后续跑正式 100 次基准的
背景资料。

对应脚本：`scripts/linux/run_sorting_success_rate.py`
两轮数据：`logs/benchmarks/sorting_success_20260828_{130903,143407}.jsonl`

## TL;DR

- 两轮 12 次试跑成功率均为 3/12（25%），但**大部分"失败"是基础设施
  问题冤枉的**，不是抓取能力问题
- 三层问题按影响排序：机器负载 > 超时参数 > 脚本鲁棒性
- 跑正式 100 次前必须先降到低负载（load < 核数一半），否则数据失真

## 1. 基准是怎么跑的

每次 trial：

1. 随机选物件（滚轮/六角螺母/短螺栓）+ 随机采样桌面位置
   （base_link 坐标 x∈[-0.50,-0.20]，y∈[-0.20,0.30]）
2. `ign service /world/empty/set_pose` 把物件传送到该位置（抬高 2cm
   落下让其物理稳定）
3. 复位机械臂回 home
4. 注入该 trial 专属 config_detect 坐标，跑完整
   `industrial.sorting_config_pick_place_actionlist`（检测→规划→抓取→
   验证→放置→验证）
5. 从物理层记录 `grasped` 判定与放置结果

```bash
# 启动仿真（注意 motion_timeout 加大）
bash scripts/linux/run_industrial_sorting_metal_sim.sh \
  robot_bridge_motion_timeout:=300.0

# 跑基准
.venv/bin/python scripts/linux/run_sorting_success_rate.py \
  --trials 12 --seed 2026
```

## 2. 问题清单

### P1 机器负载过高 → 仿真实时率骤降 → 大面积超时（最大瓶颈）

**现象**：`uptime` 显示 load average 13.8（8 核机器）；Gazebo 严重
低于实时；`close_gripper` 空载直接测只要 1.4s，但基准里反复
`MOTION_TIMEOUT`。

**根因**：多套仿真栈叠加运行。历史会话启动的 Gazebo/bridge 进程没有
完全退净（`TaskStop` 杀了 launch 父进程，孙进程 `ign gazebo server`、
`robot_bridge`、`gripper_action_bridge` 存活继续吃 CPU 6 小时+）。
CPU 排队让"仿真时间 1.4s"的动作在真实时间里超出超时阈值。

**解决**：
- 事后清理：`pgrep -af "ign gazebo|robot_bridge"` 找残留，
  `kill -9` 清掉，load 从 13.8 → 2.3
- 预防：跑基准前先 `uptime` 确认 load < nproc/2；
  停仿真时用 `pkill -f "ros2 launch"` + `pkill -f "ign gazebo"`
  确认杀干净再开始

**未消解**：换低负载时段/机器前，成功率数字不可信。

### P2 超时参数偏紧（已修）

**现象**：第一轮 4/12 挂在 `close_gripper: MOTION_TIMEOUT`，测量耗时
15.1s 正好卡 `gripper_timeout: 15.0` 边界；长距离移动偶发
`move_pregrasp: MOTION_TIMEOUT`（`motion_timeout: 90.0` 不够）。

**解决**：
- `robot_bridge.yaml`：`gripper_timeout` 15 → 30
- `full_demo.launch.py` / `robot_bridge.launch.py`：新增
  `robot_bridge_motion_timeout` launch 参数透传，启动时传 300.0
- 验证：空载 close 实测 1.4s 通过；参数本身已生效

**注意**：此修复只在负载正常时才有意义——P1 不解决，超时只是被推迟。

### P3 机械臂复位失败级联（部分缓解）

**现象**：某 trial 失败后 arm 处于 error/运动中状态，下一 trial 的
复位 `move-joints` 直接失败 → `arm_reset_failed` → 白白损失 trial
（第二轮 3/12）。

**根因**：超时后 bridge 里可能残留 active goal；单次复位不留重试。

**解决**：脚本 `reset_arm_home()` 改为最多 4 次重试（stop → 等待 →
move-joints → 指数退避），最后兜底读关节角判断是否实际已到位。
第二轮数据说明仍不完美——MoveIt 在异常状态下的规划失败只能靠重试磨。

### P4 运动衔接冲突 CANCEL_PENDING（未处理）

**现象**：2/12 报 `move_grasp: CANCEL_PENDING`——上一个动作的 goal
还没释放，新命令被拒。

**解决方向**：skill 层对 CANCEL_PENDING 做短重试（类似 pick 已有的
"arm is busy" 重试分支）；或 bridge 层在超时后主动 cancel 干净。

### P5 空抓被正确拦截（非问题，防线验证）

**现象**：随机位置下出现夹爪无物合拢（位置偏移/物件被顶走），
`verify_grasp` 以 bridge 物理判定拦截，报
`grasp not detected (grasped=False, ...)`。

**说明**：这是预期行为。之前修的"物理判定优先"在两轮基准中拦下
2-3 次假抓取，没有出现一次空抓被判成功的假阳性。

### P6 位置敏感性（待量化）

**现象**：两轮（同 seed，位置序列一致）成功的全是同 3 个位置
（滚轮 -0.35/0.06、螺母 -0.20/0.06、螺栓 -0.39/0.01），均在
工作空间中部；y>0.23 或 y<-0.18 的边缘位置全军覆没。

**解决方向**：
- 收紧采样范围到验证过可达的区域（会高估真实能力，需在报告注明）
- 或保持全范围，把"边缘不可达"作为真实限制如实统计
- MoveIt 侧可考虑 Pilz PTP/LIN 确定性规划器提升边缘构型成功率

## 3. 跑正式 100 次的检查单

1. `uptime` load < 4（8 核机器），否则换时段/机器
2. 确认无残留仿真进程：`pgrep -af "ign gazebo|robot_bridge"` 为空
3. 启动仿真带 `robot_bridge_motion_timeout:=300.0`
4. `curl /health` 就绪后多等 60s 再开跑
5. `.venv/bin/python scripts/linux/run_sorting_success_rate.py --trials 100 --seed <固定值>`
6. 预计耗时：低负载下单 trial 约 1.5-3 分钟，100 次约 3-5 小时
7. 结果在 `logs/benchmarks/sorting_success_<时间戳>.jsonl`，
   每行一个 trial，失败原因可分类统计

## 4. 当前诚实预期

低负载下（P1 解决后），瓶颈回到真实的位置敏感性 + MoveIt 随机规划
失败，预估成功率 50-70% 区间。这是预判不是承诺——正式数字以
低负载 100 次跑出来为准。
