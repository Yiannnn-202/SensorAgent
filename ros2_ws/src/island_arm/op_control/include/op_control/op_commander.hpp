// Copyright 2025 op_control authors
// Blocking ROS 2 client for the OmniPicker gripper services.

#ifndef OP_CONTROL_OP_COMMANDER_HPP_
#define OP_CONTROL_OP_COMMANDER_HPP_

#include "op_control/types.hpp"

#include <op_control_interfaces/srv/close.hpp>
#include <op_control_interfaces/srv/open.hpp>

#include <rclcpp/rclcpp.hpp>

#include <memory>
#include <string>

namespace op_control {

/// Blocking client for `/task/op/open` and `/task/op/close`.
///
/// The node passed to the constructor must be spinning (directly or through
/// an executor) for service responses to arrive. Open() and Close() block the
/// calling thread until the response is received or the timeout expires.
class OpCommander {
 public:
  explicit OpCommander(std::shared_ptr<rclcpp::Node> node);

  /// Opens the gripper at the requested normalized speed.
  Result Open(float speed);

  /// Closes the gripper with the requested normalized force and speed.
  Result Close(float force, float speed);

  void SetTimeoutSec(float timeout_sec);

 private:
  std::shared_ptr<rclcpp::Node> node_;
  std::shared_ptr<rclcpp::Client<op_control_interfaces::srv::Open>> open_client_;
  std::shared_ptr<rclcpp::Client<op_control_interfaces::srv::Close>> close_client_;
  float timeout_sec_ = 10.0f;
};

}  // namespace op_control

#endif  // OP_CONTROL_OP_COMMANDER_HPP_
