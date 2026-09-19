// Copyright 2025 op_control authors

#include "op_control/op_commander.hpp"

#include "op_control_interfaces/srv/close.hpp"
#include "op_control_interfaces/srv/open.hpp"

#include <rclcpp/rclcpp.hpp>

#include <chrono>

namespace op_control {

OpCommander::OpCommander(std::shared_ptr<rclcpp::Node> node)
    : node_(std::move(node)),
      open_client_(node_->create_client<op_control_interfaces::srv::Open>(
          "/task/op/open")),
      close_client_(node_->create_client<op_control_interfaces::srv::Close>(
          "/task/op/close")) {}

void OpCommander::SetTimeoutSec(float timeout_sec) {
  timeout_sec_ = std::max(0.0f, timeout_sec);
}

Result OpCommander::Open(float speed) {
  speed = std::max(0.0f, std::min(1.0f, speed));

  auto request =
      std::make_shared<op_control_interfaces::srv::Open::Request>();
  request->speed = speed;

  auto future = open_client_->async_send_request(request);
  auto status = rclcpp::spin_until_future_complete(
      node_, future, std::chrono::milliseconds(
                         static_cast<int>(timeout_sec_ * 1000.0f)));

  if (status != rclcpp::FutureReturnCode::SUCCESS) {
    return Result::kTimeout;
  }

  auto response = future.get();
  return response->success ? Result::kSuccess
                           : static_cast<Result>(response->result_code);
}

Result OpCommander::Close(float force, float speed) {
  force = std::max(0.0f, std::min(1.0f, force));
  speed = std::max(0.0f, std::min(1.0f, speed));

  auto request =
      std::make_shared<op_control_interfaces::srv::Close::Request>();
  request->force = force;
  request->speed = speed;

  auto future = close_client_->async_send_request(request);
  auto status = rclcpp::spin_until_future_complete(
      node_, future, std::chrono::milliseconds(
                         static_cast<int>(timeout_sec_ * 1000.0f)));

  if (status != rclcpp::FutureReturnCode::SUCCESS) {
    return Result::kTimeout;
  }

  auto response = future.get();
  return response->success ? Result::kSuccess
                           : static_cast<Result>(response->result_code);
}

}  // namespace op_control
