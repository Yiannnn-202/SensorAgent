# RM65-B + Robotiq 2F-85 Gazebo 仿真启动指引

本文说明如何在 **Ubuntu 22.04 + ROS 2 Humble** 环境中启动本项目的
RM65-B、Robotiq 2F-85、Gazebo 与 MoveIt 2 仿真控制栈。

> 当前启动栈包含 Gazebo、机械臂/夹爪 `ros2_control`、MoveIt 2、RViz 和
> 已实现的 `sensoragent_robot_bridge`。HTTP Bridge 默认监听
> `http://127.0.0.1:8765`；可通过 `/health` 和 `/ready` 检查服务与控制接口。
> 接口和配置见
> [SensorAgent 仿真机器人 HTTP Bridge 指引](robot_sim_bridge_cn.md)。

## 最简使用方式

首次克隆仓库，或者 RM65-B/Robotiq 仿真文件发生更新后，运行一次：

```bash
cd ~/SensorAgent
bash scripts/linux/prepare_rm65_b_sim.sh
```

以后每次启动只需要：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

该命令会自动加载 ROS 2 和工作区环境，并启动 Gazebo、RM65-B、Robotiq
2F-85、MoveIt 2 与 RViz。仅启动 Gazebo、不启动 MoveIt/RViz 时使用：

```bash
bash scripts/linux/run_rm65_b_sim.sh start_moveit:=false
```

如果希望在任意目录直接启动，可以配置一次终端别名：

```bash
echo "alias sensoragent-sim='cd ~/SensorAgent && bash scripts/linux/run_rm65_b_sim.sh'" \
  >> ~/.bashrc
source ~/.bashrc
```

以后只需执行：

```bash
sensoragent-sim
```

后续章节保留手动命令，供安装、调试和故障排查使用。

## 1. 进入项目并加载 ROS 2

```bash
cd ~/SensorAgent
source /opt/ros/humble/setup.bash
```

如果仓库不在 `~/SensorAgent`，请将本文中的路径替换为实际克隆路径。

本项目当前导入的是 RealMan 官方 `humble` 分支。其他 ROS 2 版本暂未验证。

## 2. 导入 RM65-B 官方文件

上游模型和仿真文件不会提交到本仓库，需要在每个新环境中执行一次：

```bash
bash scripts/linux/fetch_rm65_b_upstream.sh
```

导入完成后应存在以下 ROS 2 包：

```text
ros2_ws/src/rm_description
ros2_ws/src/rm_gazebo
ros2_ws/src/rm_65_config
```

项目中的 `rm65_b` 对应 RealMan 官方包内的标准 `rm_65` 型号，不使用
`rm_65_6f` 或 `rm_65_6fb` 变体。

Robotiq 文件已经随仓库提供，不需要另行下载：

```text
ros2_ws/src/robotiq_description
ros2_ws/src/sensoragent_rm65_b_bringup
ros2_ws/src/sensoragent_robot_bridge
```

其中 `sensoragent_rm65_b_bringup` 将 2F-85 通过固定关节安装到 RM65-B
末端 `Link6`，并使用一个 `gz_ros2_control` 系统统一管理机械臂和夹爪；
`sensoragent_robot_bridge` 提供默认位于 `http://127.0.0.1:8765` 的
HTTP-to-ROS 2 控制边界。

## 3. 安装构建和运行依赖

```bash
sudo apt update
sudo apt install -y \
  python3-colcon-common-extensions \
  python3-rosdep \
  ros-humble-moveit \
  ros-humble-ros-gz \
  ros-humble-ros2-controllers \
  ros-humble-xacro
```

安装 Gazebo 控制插件：

```bash
sudo apt install -y ros-humble-gz-ros2-control || \
  sudo apt install -y ros-humble-ign-ros2-control
```

如果尚未初始化 `rosdep`：

```bash
sudo rosdep init
rosdep update
```

安装工作区内包的其余依赖：

```bash
rosdep install \
  --from-paths ros2_ws/src \
  --ignore-src \
  --rosdistro humble \
  -r -y
```

本项目导入的最小仿真栈不包含 MoveIt MongoDB 场景仓库，因此不需要
`warehouse_ros_mongo`。如果此前已经导入过上游文件，请重新执行第 2 节的
导入脚本，再运行 `rosdep install`。

## 4. 编译 RM65-B 仿真包

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash

colcon build \
  --symlink-install \
  --packages-select \
    rm_description \
    rm_65_config \
    rm_gazebo \
    robotiq_description \
    sensoragent_robot_bridge \
    sensoragent_rm65_b_bringup

source install/setup.bash
```

每次打开新终端后都需要执行：

```bash
cd ~/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## 5. 启动 Gazebo 和机械臂控制器

在第一个终端执行：

```bash
cd ~/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch sensoragent_rm65_b_bringup gazebo_robotiq_demo.launch.py
```

Ogre 1 下默认不调用 Gazebo 的自动聚焦服务，因为该服务可能在计算组合模型
边界时触发渲染器崩溃。机械臂和夹爪会直接出现在默认视口中。确认使用 Ogre 2
且需要自动聚焦时，可传入 `auto_focus_robot:=true`。

该命令默认加载轻量工业桌面场景，并启动：

- 使用 DART PGS 求解器的 Gazebo 场景；
- 工作台、3×3 料箱、六类基础零件和顶置 RGB-D 相机；
- RM65-B 模型；
- 固定在 `Link6` 末端的 Robotiq 2F-85；
- `robot_state_publisher`；
- `joint_state_broadcaster`；
- `rm_group_controller`；
- `robotiq_gripper_effort_controller`；
- 提供 `/robotiq_gripper_controller/gripper_cmd` 的夹爪 Action bridge。

等待 Gazebo 中出现机械臂，并确认终端没有控制器加载错误。

如需恢复原来的空场景：

```bash
ros2 launch sensoragent_rm65_b_bringup \
  gazebo_robotiq_demo.launch.py \
  world_file:=empty_pgs.sdf \
  bridge_camera:=false
```

工业场景的模型清单、相机话题和自定义模型导入方式见
[`industrial_gazebo_environment_cn.md`](industrial_gazebo_environment_cn.md)。

PGS 求解器用于规避 Ubuntu 22.04 自带 DART 6 Dantzig 求解器的稳定性问题。
Gazebo 中左右夹指使用独立的限力 effort 控制，夹指内部接触部件固定为刚体，
因此任一夹指接触物体后不会与指节脱节。

如需只验证未安装夹爪的 RealMan 上游模型，仍可使用：

```bash
ros2 launch rm_gazebo gazebo_65_demo.launch.py
```

## 6. 启动 MoveIt 2 和 RViz

保持第一个终端运行，在第二个终端执行：

```bash
cd ~/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch sensoragent_rm65_b_bringup moveit_robotiq_demo.launch.py
```

RViz 启动后，可以通过 MotionPlanning 面板设置目标姿态，先执行 `Plan`，
确认轨迹无误后再执行 `Execute`。`rm_group` 用于机械臂规划，`gripper`
用于 2F-85 开合。

也可以直接测试夹爪 Action。打开夹爪：

```bash
ros2 action send_goal \
  /robotiq_gripper_controller/gripper_cmd \
  control_msgs/action/GripperCommand \
  '{command: {position: 0.0, max_effort: 20.0}}'
```

关闭夹爪：

```bash
ros2 action send_goal \
  /robotiq_gripper_controller/gripper_cmd \
  control_msgs/action/GripperCommand \
  '{command: {position: 0.0848, max_effort: 20.0}}'
```

`position` 是左右夹指向内行程之和，单位为米；`0.0` 为完全打开，
`0.0848` 为完全闭合。抓住物体时通常会在二者之间停止并返回
`stalled: true`。

## 7. 检查运行状态

在第三个已加载工作区环境的终端执行：

```bash
ros2 pkg prefix rm_description
ros2 pkg prefix rm_gazebo
ros2 pkg prefix rm_65_config
ros2 pkg prefix robotiq_description
ros2 pkg prefix sensoragent_robot_bridge
ros2 pkg prefix sensoragent_rm65_b_bringup

ros2 control list_controllers
ros2 topic echo /joint_states --once
ros2 action list | grep robotiq
```

控制器正常时应至少看到：

```text
joint_state_broadcaster  active
rm_group_controller     active
robotiq_gripper_effort_controller active
```

## 8. 夹爪安装位姿状态

当前组合模型按 `Link6` 与 `robotiq_85_base_link` 原点同轴、零偏置安装：

```xml
gripper_mount_xyz="0 0 0"
gripper_mount_rpy="0 0 0"
```

该位姿已经在 Ubuntu 的 Gazebo 中完成视觉检查，当前模型位置和开合方向
正常。它仍是仿真安装参数，不代表真实法兰适配器的精确机械尺寸。

若后续更换法兰、网格或真实安装结构，发现夹爪重叠或朝向不正确，请修改：

```text
ros2_ws/src/sensoragent_rm65_b_bringup/urdf/rm65_b_robotiq_2f85.urdf.xacro
```

中的两个默认安装参数，并重新编译。Gazebo 与 MoveIt 共用该 Xacro，因此只需
校准一处。

## 常见问题

### 找不到 ROS 2 包

重新加载当前工作区：

```bash
source /opt/ros/humble/setup.bash
source ~/SensorAgent/ros2_ws/install/setup.bash
```

### 找不到 `gz_ros2_control`

```bash
sudo apt install -y ros-humble-gz-ros2-control
```

如果该包在当前软件源中不存在，改用：

```bash
sudo apt install -y ros-humble-ign-ros2-control
```

### 控制器没有激活

```bash
ros2 control list_controllers
ros2 control load_controller --set-state active joint_state_broadcaster
ros2 control load_controller --set-state active rm_group_controller
ros2 control load_controller --set-state active robotiq_gripper_effort_controller
ros2 run sensoragent_rm65_b_bringup gripper_action_bridge.py --ros-args \
  -p use_sim_time:=true
```

### Gazebo 已启动但 MoveIt 不能执行

确认机械臂和夹爪控制器均为 `active`，并检查 Action 是否存在：

```bash
ros2 action list | grep follow_joint_trajectory
ros2 action list | grep gripper_cmd
```

停止服务时，在运行 Gazebo 和 MoveIt 2 的终端分别按 `Ctrl+C`。

### Gazebo 中看不到机械臂和夹爪

先确认终端中出现：

```text
Created entity [...] named [rm65_b_robotiq_2f85]
```

如果同时出现 `Entity named [rm65_b_robotiq_2f85] already exists`，说明
上一次 Gazebo 实例或启动进程仍在运行。先在原终端按 `Ctrl+C` 完整停止，
再重新执行启动命令；不要在同一个 Gazebo 世界中重复启动该 launch 文件。

此启动文件默认使用兼容性更好的 Ogre 1。如果 Gazebo 的按钮和文字正常，
但三维视口仍完全为白色，通常是虚拟机中的 OpenGL 兼容问题。尝试 Mesa
软件渲染：

```bash
LIBGL_ALWAYS_SOFTWARE=1 \
ros2 launch sensoragent_rm65_b_bringup \
  gazebo_robotiq_demo.launch.py render_engine:=ogre
```

如果软件渲染导致整个三维视口闪烁，应取消 `LIBGL_ALWAYS_SOFTWARE`，并优先
在虚拟机设置中启用三维加速。确认显卡支持 Ogre 2 后，可使用
`render_engine:=ogre2` 恢复较新的渲染器。

模型和控制器仍可正常生成时，这个问题与 ROS 2 或 RM65-B 文件无关。
