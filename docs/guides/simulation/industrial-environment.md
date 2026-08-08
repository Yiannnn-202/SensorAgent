# 工业桌面 Gazebo 环境

项目提供一个面向感知、抓取、指定格放置和结果验证的轻量工业桌面场景。
场景优先保证物理稳定性、可修改性和较低的渲染开销，不模拟完整厂房。

## 1. 场景内容

默认世界文件：

```text
ros2_ws/src/sensoragent_rm65_b_bringup/worlds/industrial_pgs.sdf
```

包含以下设施：

- 将 RM65-B 安装面抬高至 `0.18 m` 的底座；
- 工业工作台，台面高度为 `0.30 m`；
- 3×3 多格料箱；
- 顶置 RGB 与深度相机及支架；
- 地面、背景墙、方向光和工作灯；
- 六类基础工业零件。

六类零件为：

| 模型目录 | 场景名称 | 主要形状 |
| --- | --- | --- |
| `sensoragent_part_block` | `block_01` | 稳定方块，当前默认抓取物 |
| `sensoragent_part_roller` | 可手动生成 `roller_*` | 圆柱滚柱，视觉管线集成后再切回 |
| `sensoragent_part_stepped_shaft` | `stepped_shaft_01` | 阶梯轴 |
| `sensoragent_part_flange` | `flange_01` | 法兰圆柱 |
| `sensoragent_part_hex_nut` | `hex_nut_01` | 简化六角螺母 |
| `sensoragent_part_short_bolt` | `short_bolt_01` | 无螺纹短螺栓 |
| `sensoragent_part_gear` | `gear_01` | 简化齿轮 |

当前默认只生成一个方块，避免圆柱放置后滚动影响 pick/place bringup。需要验证
视觉空间选择器时，可再手动生成多个滚柱或多个方块实例。详见
[Gazebo RGB-D ActionList test](../vision/gazebo-actionlist-test.md)。

模型使用基础几何体和简化碰撞体，尺寸均控制在 Robotiq 2F-85 的
`84.8 mm` 最大开口范围内。

RM65-B 的基座安装面为 `z=0.18 m`，比 `z=0.30 m` 的工作台顶面低
`0.12 m`。工作台前沿位于机械臂基座前方约 `0.15 m`，为底部关节旋转保留
空间。该安装高度写入组合 URDF 的
`world_to_rm65_b` 固定关节，因此 Gazebo、TF、MoveIt 和 RViz 使用一致的
机器人坐标，不应再通过 Gazebo GUI 单独拖高机器人。

RM65-B 第一关节轴相对基座高约 `0.2405 m`，因此调整后第一关节轴仍比桌面
高约 `0.12 m`。

## 2. 编译并加载场景

首次准备项目：

```bash
cd ~/SensorAgent
bash scripts/linux/prepare_rm65_b_sim.sh
```

已经准备过工作区，但刚拉取了新的场景文件时，可以只重新编译 bringup 包：

```bash
cd ~/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash

colcon build \
  --symlink-install \
  --packages-select sensoragent_rm65_b_bringup

source install/setup.bash
```

启动 Gazebo、机械臂、夹爪和 MoveIt：

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

`industrial_pgs.sdf` 是默认世界，无需额外参数。世界内部名称继续使用
`empty`，以兼容已有控制、生成和服务命令。

如需恢复原来的空场景：

```bash
bash scripts/linux/run_rm65_b_sim.sh \
  world_file:=empty_pgs.sdf \
  bridge_camera:=false
```

空场景仍保留机械臂底座，以匹配组合 URDF 中 `0.18 m` 的安装高度，但不加载
工作台、料箱、零件和相机。

## 3. 相机话题

场景使用同位姿的 RGB 相机和深度相机组成轻量 RGB-D 设备，默认发布：

```text
/industrial_camera/image
/industrial_camera/camera_info
/industrial_camera/depth_image
/industrial_camera/depth_camera_info
```

启动后检查 ROS 2 话题：

```bash
ros2 topic list | grep industrial_camera
```

查看相机参数是否到达 ROS 2：

```bash
ros2 topic echo \
  /industrial_camera/camera_info \
  --once
```

如暂时不需要 ROS 2 相机话题，可关闭 bridge：

```bash
bash scripts/linux/run_rm65_b_sim.sh bridge_camera:=false
```

## 4. 单独生成一个零件

所有模型会随 `sensoragent_rm65_b_bringup` 安装。先取得安装目录：

```bash
package_share="$(
  ros2 pkg prefix sensoragent_rm65_b_bringup
)/share/sensoragent_rm65_b_bringup"
```

在工作台上额外生成一个方块：

```bash
ros2 run ros_gz_sim create \
  -world empty \
  -file "${package_share}/models/sensoragent_part_block/model.sdf" \
  -name block_02 \
  -x 0.34 \
  -y 0.16 \
  -z 0.32
```

台面顶面为 `z=0.30 m`。生成其他零件时，需要根据模型高度设置其中心
`z`，避免模型初始状态悬空或嵌入台面。

## 5. 调整初始布局

编辑：

```text
ros2_ws/src/sensoragent_rm65_b_bringup/worlds/industrial_pgs.sdf
```

每个零件通过 `<include>` 加载：

```xml
<include>
  <uri>model://sensoragent_part_block</uri>
  <name>block_01</name>
  <pose>0.24 0.18 0.320 0 0 0</pose>
</include>
```

`pose` 的顺序为：

```text
x y z roll pitch yaw
```

修改后重新启动 Gazebo。使用 `--symlink-install` 编译时，通常不需要为单纯
SDF 内容修改重新编译；新增模型目录或安装规则后应重新执行 `colcon build`。

## 6. 导入新的模型

在 bringup 包的 `models` 下新增独立目录：

```text
models/
└── my_industrial_part/
    ├── model.config
    ├── model.sdf
    └── meshes/
        ├── visual.dae
        └── collision.stl
```

`model.config` 最小示例：

```xml
<?xml version="1.0"?>
<model>
  <name>My Industrial Part</name>
  <version>1.0</version>
  <sdf version="1.8">model.sdf</sdf>
</model>
```

`model.sdf` 必须至少包含：

```text
质量和惯性
碰撞几何
视觉几何
摩擦参数
唯一模型名称
```

在 `industrial_pgs.sdf` 中加入：

```xml
<include>
  <uri>model://my_industrial_part</uri>
  <name>my_industrial_part_01</name>
  <pose>0.35 0.20 0.34 0 0 0</pose>
</include>
```

然后重新编译并 source 工作区：

```bash
cd ~/SensorAgent/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select sensoragent_rm65_b_bringup
source install/setup.bash
```

动态抓取物体不应直接使用高面数网格作为碰撞体。视觉网格可以保留细节，
碰撞体应使用圆柱、方盒、凸包或单独制作的低面数 STL。

## 7. 当前边界

当前版本提供固定初始布局，还没有实现：

- 随机生成物体位置和朝向；
- 一键重置场景；
- 自动清除并重新生成零件；
- 相机点云桥接；
- 料箱格子的自动占用状态判断。

这些能力应在后续“工业场景与数据”和“结果验证与恢复”模块中接入。
