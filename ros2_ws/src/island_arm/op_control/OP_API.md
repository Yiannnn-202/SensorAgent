# OmniPicker Control API

ROS 2 C++ driver for the OmniPicker adaptive gripper.

## Public ROS Contract

| Topic/Service | Type | Direction | Description |
|---------------|------|-----------|-------------|
| `/task/op/open` | `op_control_interfaces/srv/Open` | Service | Open the gripper. |
| `/task/op/close` | `op_control_interfaces/srv/Close` | Service | Close the gripper. |
| `/omnipicker_state` | `op_control_interfaces/msg/OmniPickerState` | Topic | Real-time gripper state. |

`OP` in package and namespace names means OmniPicker.

## Messages

### `op_control_interfaces/msg/OmniPickerState`

```text
float32 pos         # 0.0 (closed) ~ 1.0 (open)
float32 force       # 0.0 ~ 1.0
float32 vel         # 0.0 ~ 1.0 (reserved, currently 0)
uint8   status      # 0=ARRIVED, 1=MOVING, 2=STALLED, 3=DROPPED, 255=UNKNOWN
uint8[12] raw_frame # Last valid 12-byte protocol frame
```

### `op_control_interfaces/srv/Open`

Request:
```text
float32 speed  # normalized speed in [0.0, 1.0]
```

Response:
```text
bool   success
int8   result_code  # 0=SUCCESS, see Result enum below
```

### `op_control_interfaces/srv/Close`

Request:
```text
float32 force  # normalized force in [0.0, 1.0]
float32 speed  # normalized speed in [0.0, 1.0]
```

Response: same as `Open`.

Note: `success` is `true` when `result_code` is `SUCCESS` **or** `GRASPED`.
`GRASPED` means the gripper stalled while closing, i.e. an object was grasped.

## Result Codes

| Code | Meaning |
|------|---------|
| 0 | `SUCCESS` |
| 1 | `GRASPED` (close only) |
| 2 | `DROPPED` |
| 3 | `TIMEOUT` |
| 4 | `SERIAL_ERROR` |
| 5 | `BUSY` |
| 6 | `INVALID_PARAM` |
| 7 | `NOT_INITIALIZED` |

## Build

```bash
cd /home/nvidia/Arm
colcon build --packages-select op_control_interfaces op_control
```

## Run

```bash
source install/setup.bash
ros2 run op_control op_control_node --ros-args -p port:=/dev/ttyUSB0 -p baudrate:=115200
```

Or use the launch file:

```bash
ros2 launch op_control op_control.launch.py
```

### Node Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | string | `/dev/ttyUSB0` | Serial port device |
| `baudrate` | int | `115200` | Serial baudrate |
| `timeout_sec` | float | `8.0` | Motion timeout |
| `open_force` | float | `0.4` | Default force used for open |
| `motion_acc` | float | `0.5` | Acceleration used for all motions |
| `motion_dec` | float | `0.5` | Deceleration used for all motions |

## CLI Examples

```bash
# Open
ros2 service call /task/op/open op_control_interfaces/srv/Open '{speed: 0.8}'

# Close
ros2 service call /task/op/close op_control_interfaces/srv/Close '{force: 0.6, speed: 0.8}'

# Watch state
ros2 topic echo /omnipicker_state
```

## C++ Client Example

```cpp
#include "op_control/op_commander.hpp"
#include <rclcpp/rclcpp.hpp>

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("op_client");
  op_control::OpCommander commander(node);

  op_control::Result r = commander.Open(0.8f);
  RCLCPP_INFO(node->get_logger(), "Open result: %d", static_cast<int>(r));

  r = commander.Close(0.6f, 0.8f);
  RCLCPP_INFO(node->get_logger(), "Close result: %d", static_cast<int>(r));

  rclcpp::shutdown();
  return 0;
}
```

A ready-to-run example ships with the package:

```bash
# Terminal 1: start driver
ros2 run op_control op_control_node --ros-args -p port:=/dev/ttyUSB0

# Terminal 2: run C++ test client
ros2 run op_control op_test_client
```

### Linking `op_commander` in another package

```cmake
find_package(op_control REQUIRED)

add_executable(my_client src/my_client.cpp)
ament_target_dependencies(my_client rclcpp op_control_interfaces)
target_link_libraries(my_client op_control::op_commander)
```

```cpp
#include "op_control/op_commander.hpp"
```

## Design Notes

- The serial layer uses raw POSIX `termios` at 115200 8N1.
- A rolling receive buffer preserves fragmented frames and scans for the newest
  valid 12-byte frame.
- Commands are resent every 50 ms because the firmware reports one state frame
  per received command.
- One motion owns the serial stream until completion or the default 8-second
  timeout; the ROS node enforces this with a mutex for multi-threaded executors.
- `DROPPED` takes priority over position tolerance.
- Full-open timeout tolerance is never applied to a closing motion.
- The node adds non-zero acceleration/deceleration (`motion_acc`/`motion_dec`)
  to every motion. Some OmniPicker units will not move from a static position
  if `acc` and `dec` are both zero.
