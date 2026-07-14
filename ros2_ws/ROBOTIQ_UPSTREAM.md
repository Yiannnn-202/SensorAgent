# Robotiq 2F-85 upstream source

The Robotiq 2F-85 simulation description is vendored from:

- Repository: <https://github.com/PickNikRobotics/ros2_robotiq_gripper>
- Branch: `humble`
- Commit: `a29c69b7516b7a97737b5e43e118e6598ace0832`
- License: BSD-3-Clause
- Target environment: Ubuntu 22.04 and ROS 2 Humble

The repository keeps only the files needed to describe and simulate a 2F-85:

- the 2F-85 Xacro model and ros2_control macro;
- 2F-85 visual and collision meshes;
- the upstream changelog and BSD-3-Clause license.

The 2F-140, Hand-E, Universal Robots adapter, physical serial driver, hardware
activation controller, examples, and hardware tests are intentionally omitted.
The integrated simulation replaces the upstream contact-bearing mimic linkage
with two rigid, independently effort-controlled prismatic finger assemblies.
A small ROS 2 action bridge preserves the standard `GripperCommand` interface
while allowing either finger to stop safely on object contact.

The vendored macro defaults `include_ros2_control` to `false`. The combined
bringup package supplies the simulation control interfaces in the same
`gz_ros2_control` system as the RM65-B instead of loading the omitted physical
driver.

The integrated robot description is in
`sensoragent_rm65_b_bringup`. It attaches `robotiq_85_base_link` to the RM65-B
`Link6` flange and lets one `gz_ros2_control` system manage both the arm and
gripper.
