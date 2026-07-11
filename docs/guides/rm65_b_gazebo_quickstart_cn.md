# RM65-B + Robotiq 2F-85 Gazebo 仿真启动指引

本文说明如何在 **Ubuntu 22.04 + ROS 2 Humble** 环境中启动本项目的
RM65-B、Robotiq 2F-85、Gazebo 与 MoveIt 2 仿真控制栈。

> 当前可以启动 Gazebo、机械臂/夹爪 `ros2_control`、MoveIt 2 和 RViz。项目中的
> `sensoragent_robot_bridge` 尚未实现，因此 SensorAgent 还不能直接向
> ROS 2 下发机械臂任务。

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
```

其中 `sensoragent_rm65_b_bringup` 将 2F-85 通过固定关节安装到 RM65-B
末端 `Link6`，并使用一个 `gz_ros2_control` 系统统一管理机械臂和夹爪。

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

该命令会启动：

- Gazebo 空场景；
- RM65-B 模型；
- 固定在 `Link6` 末端的 Robotiq 2F-85；
- `robot_state_publisher`；
- `joint_state_broadcaster`；
- `rm_group_controller`；
- `robotiq_gripper_controller`。

等待 Gazebo 中出现机械臂，并确认终端没有控制器加载错误。

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
  '{command: {position: 0.0, max_effort: 30.0}}'
```

关闭夹爪：

```bash
ros2 action send_goal \
  /robotiq_gripper_controller/gripper_cmd \
  control_msgs/action/GripperCommand \
  '{command: {position: 0.7929, max_effort: 30.0}}'
```

## 7. 检查运行状态

在第三个已加载工作区环境的终端执行：

```bash
ros2 pkg prefix rm_description
ros2 pkg prefix rm_gazebo
ros2 pkg prefix rm_65_config
ros2 pkg prefix robotiq_description
ros2 pkg prefix sensoragent_rm65_b_bringup

ros2 control list_controllers
ros2 topic echo /joint_states --once
ros2 action list | grep robotiq
```

控制器正常时应至少看到：

```text
joint_state_broadcaster  active
rm_group_controller     active
robotiq_gripper_controller active
```

## 8. 校准夹爪安装位姿

当前组合模型按 `Link6` 与 `robotiq_85_base_link` 原点同轴、零偏置安装：

```xml
gripper_mount_xyz="0 0 0"
gripper_mount_rpy="0 0 0"
```

这足以建立运动学和控制链，但最终法兰适配器厚度与朝向仍需在 Ubuntu 的
Gazebo/RViz 中核对。若夹爪与法兰重叠或朝向不正确，请修改：

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
ros2 control load_controller --set-state active robotiq_gripper_controller
```

### Gazebo 已启动但 MoveIt 不能执行

确认机械臂和夹爪控制器均为 `active`，并检查 Action 是否存在：

```bash
ros2 action list | grep follow_joint_trajectory
ros2 action list | grep gripper_cmd
```

停止服务时，在运行 Gazebo 和 MoveIt 2 的终端分别按 `Ctrl+C`。

### Gazebo 中看不到机械臂

先确认终端中出现：

```text
Created entity [...] named [rm_65_description]
```

如果同时出现 `Entity named [rm_65_description] already exists`，说明上一次
Gazebo 实例或启动进程仍在运行。先在原终端按 `Ctrl+C` 完整停止，再重新执行
启动命令；不要在同一个 Gazebo 世界中重复启动该 launch 文件。

如果 Gazebo 的按钮和文字正常，但三维视口完全为白色，通常是虚拟机中的
Ogre 2 / OpenGL 兼容问题。先改用 Ogre 1：

```bash
ros2 launch sensoragent_rm65_b_bringup \
  gazebo_robotiq_demo.launch.py render_engine:=ogre
```

如果 Ogre 1 仍然无法显示，再尝试 Mesa 软件渲染：

```bash
LIBGL_ALWAYS_SOFTWARE=1 \
ros2 launch sensoragent_rm65_b_bringup \
  gazebo_robotiq_demo.launch.py render_engine:=ogre
```

如果软件渲染导致整个三维视口闪烁，应取消 `LIBGL_ALWAYS_SOFTWARE`，并优先
在虚拟机设置中启用三维加速。

模型和控制器仍可正常生成时，这个问题与 ROS 2 或 RM65-B 文件无关。
