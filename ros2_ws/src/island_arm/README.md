# Integrated Island-Arm ROS 2 packages

This directory contains the Island-Arm ROS 2 packages required by the
SensorAgent physical hardware stack. They are built as part of the SensorAgent
workspace; a separate `~/Island-Arm` checkout or install overlay is not needed.

Imported packages:

- `rm_driver`
- `rm_ros_interfaces`
- `arm_control`
- `arm_control_interfaces`
- `op_control`
- `op_control_interfaces`
- `vision_dep`
- `vision_interfaces`

Source provenance:

- Repository: `https://github.com/Island-Team/Island-Arm.git`
- Commit: `94b32b91a5b8be3c3f58114265b370c192b1b826`

The `arm_control`, `arm_control_interfaces`, `op_control`, and
`op_control_interfaces` package manifests declare Apache-2.0. The
`vision_interfaces` manifest declares MIT. At import time, `rm_driver`,
`rm_ros_interfaces`, and `vision_dep` contained incomplete `TODO` license
declarations. Confirm redistribution permission with the corresponding rights
holders before submitting or publishing this integrated source tree.
