// Copyright 2025 op_control authors
// Minimal C++ client that exercises /task/op/open and /task/op/close.

#include "op_control/op_commander.hpp"

#include <rclcpp/rclcpp.hpp>

#include <chrono>
#include <cstdlib>

namespace {

const char* ResultStr(op_control::Result r) {
  switch (r) {
    case op_control::Result::kSuccess:
      return "SUCCESS";
    case op_control::Result::kGrasped:
      return "GRASPED";
    case op_control::Result::kDropped:
      return "DROPPED";
    case op_control::Result::kTimeout:
      return "TIMEOUT";
    case op_control::Result::kSerialError:
      return "SERIAL_ERROR";
    case op_control::Result::kBusy:
      return "BUSY";
    case op_control::Result::kInvalidParam:
      return "INVALID_PARAM";
    case op_control::Result::kNotInitialized:
      return "NOT_INITIALIZED";
    default:
      return "UNKNOWN";
  }
}

}  // namespace

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);

  auto node = rclcpp::Node::make_shared("op_test_client");
  op_control::OpCommander commander(node);

  RCLCPP_INFO(node->get_logger(), "Waiting for /task/op/open and /task/op/close ...");

  // Give the services a moment to appear.
  std::this_thread::sleep_for(std::chrono::seconds(2));

  RCLCPP_INFO(node->get_logger(), "Calling /task/op/open (speed=0.8)");
  op_control::Result r = commander.Open(0.8f);
  RCLCPP_INFO(node->get_logger(), "Open result: %s", ResultStr(r));

  std::this_thread::sleep_for(std::chrono::seconds(1));

  RCLCPP_INFO(node->get_logger(), "Calling /task/op/close (force=0.6, speed=0.8)");
  r = commander.Close(0.6f, 0.8f);
  RCLCPP_INFO(node->get_logger(), "Close result: %s", ResultStr(r));

  rclcpp::shutdown();
  return (r == op_control::Result::kSuccess || r == op_control::Result::kGrasped)
             ? EXIT_SUCCESS
             : EXIT_FAILURE;
}
