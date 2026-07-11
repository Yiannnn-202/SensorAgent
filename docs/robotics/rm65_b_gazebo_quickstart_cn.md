# RM65-B Gazebo 仿真启动指引

本文说明如何在 **Ubuntu 22.04 + ROS 2 Humble** 环境中启动本项目的
RM65-B Gazebo 与 MoveIt 2 仿真控制栈。

> 当前可以启动 Gazebo、`ros2_control`、MoveIt 2 和 RViz。项目中的
> `sensoragent_robot_bridge` 尚未实现，因此 SensorAgent 还不能直接向
> ROS 2 下发机械臂任务。

## 1. 进入项目并加载 ROS 2

```bash
cd /path/to/SensorAgent
source /opt/ros/humble/setup.bash
```

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

## 4. 编译 RM65-B 仿真包

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash

colcon build \
  --symlink-install \
  --packages-select rm_description rm_65_config rm_gazebo

source install/setup.bash
```

每次打开新终端后都需要执行：

```bash
cd /path/to/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## 5. 启动 Gazebo 和机械臂控制器

在第一个终端执行：

```bash
cd /path/to/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch rm_gazebo gazebo_65_demo.launch.py
```

该命令会启动：

- Gazebo 空场景；
- RM65-B 模型；
- `robot_state_publisher`；
- `joint_state_broadcaster`；
- `rm_group_controller`。

等待 Gazebo 中出现机械臂，并确认终端没有控制器加载错误。

## 6. 启动 MoveIt 2 和 RViz

保持第一个终端运行，在第二个终端执行：

```bash
cd /path/to/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch rm_65_config gazebo_moveit_demo.launch.py
```

RViz 启动后，可以通过 MotionPlanning 面板设置目标姿态，先执行 `Plan`，
确认轨迹无误后再执行 `Execute`。Gazebo 中的机械臂应同步运动。

## 7. 检查运行状态

在第三个已加载工作区环境的终端执行：

```bash
ros2 pkg prefix rm_description
ros2 pkg prefix rm_gazebo
ros2 pkg prefix rm_65_config

ros2 control list_controllers
ros2 topic echo /joint_states --once
```

控制器正常时应至少看到：

```text
joint_state_broadcaster  active
rm_group_controller     active
```

## 常见问题

### 找不到 ROS 2 包

重新加载当前工作区：

```bash
source /opt/ros/humble/setup.bash
source /path/to/SensorAgent/ros2_ws/install/setup.bash
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
```

### Gazebo 已启动但 MoveIt 不能执行

确认 `rm_group_controller` 为 `active`，并检查轨迹 Action 是否存在：

```bash
ros2 action list | grep follow_joint_trajectory
```

停止服务时，在运行 Gazebo 和 MoveIt 2 的终端分别按 `Ctrl+C`。
