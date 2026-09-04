// Copyright 2025 op_control authors
// ROS 2 node that exposes OmniPicker services and publishes state.

#include "op_control/driver.hpp"
#include "op_control_interfaces/msg/omni_picker_state.hpp"
#include "op_control_interfaces/srv/close.hpp"
#include "op_control_interfaces/srv/open.hpp"
#include "op_control_interfaces/srv/set_position.hpp"

#include <rclcpp/rclcpp.hpp>

#include <mutex>
#include <string>

namespace op_control {

class OpControlNode : public rclcpp::Node {
 public:
  OpControlNode() : Node("op_control_node") {
    this->declare_parameter<std::string>("port", kDefaultPort);
    this->declare_parameter<int>("baudrate", kDefaultBaudrate);
    this->declare_parameter<float>("timeout_sec", kDefaultTimeoutSec);
    this->declare_parameter<float>("open_force", 0.4f);
    this->declare_parameter<float>("motion_acc", 0.5f);
    this->declare_parameter<float>("motion_dec", 0.5f);

    port_ = this->get_parameter("port").as_string();
    baudrate_ = this->get_parameter("baudrate").as_int();
    open_force_ = this->get_parameter("open_force").as_double();
    motion_acc_ = this->get_parameter("motion_acc").as_double();
    motion_dec_ = this->get_parameter("motion_dec").as_double();

    state_pub_ = this->create_publisher<op_control_interfaces::msg::OmniPickerState>(
        "/omnipicker_state", 10);

    driver_.SetStateCallback(
        [this](const State& state) { PublishState(state); });

    if (!driver_.Connect(port_, baudrate_)) {
      RCLCPP_ERROR(this->get_logger(), "Failed to connect to %s @ %d", port_.c_str(),
                   baudrate_);
    } else {
      RCLCPP_INFO(this->get_logger(), "Connected to OmniPicker on %s @ %d",
                  port_.c_str(), baudrate_);
    }

    open_srv_ = this->create_service<op_control_interfaces::srv::Open>(
        "/task/op/open",
        [this](const std::shared_ptr<op_control_interfaces::srv::Open::Request> request,
               std::shared_ptr<op_control_interfaces::srv::Open::Response> response) {
          HandleOpen(request, response);
        });

    close_srv_ = this->create_service<op_control_interfaces::srv::Close>(
        "/task/op/close",
        [this](const std::shared_ptr<op_control_interfaces::srv::Close::Request> request,
               std::shared_ptr<op_control_interfaces::srv::Close::Response> response) {
          HandleClose(request, response);
        });
    set_position_srv_ = this->create_service<op_control_interfaces::srv::SetPosition>(
        "/task/op/set_position",
        [this](const std::shared_ptr<op_control_interfaces::srv::SetPosition::Request> request,
               std::shared_ptr<op_control_interfaces::srv::SetPosition::Response> response) {
          HandleSetPosition(request, response);
        });
  }

  ~OpControlNode() override { driver_.Disconnect(); }

 private:
  void PublishState(const State& state) {
    auto msg = op_control_interfaces::msg::OmniPickerState();
    msg.pos = state.pos;
    msg.force = state.force;
    msg.vel = state.vel;
    msg.status = static_cast<std::uint8_t>(state.status);
    msg.raw_frame = state.raw_frame;
    state_pub_->publish(msg);
  }

  void HandleOpen(const std::shared_ptr<op_control_interfaces::srv::Open::Request> request,
                  std::shared_ptr<op_control_interfaces::srv::Open::Response> response) {
    std::lock_guard<std::mutex> lock(motion_mutex_);
    Result result = Execute(1.0f, open_force_, request->speed);
    response->success = (result == Result::kSuccess);
    response->result_code = static_cast<std::int8_t>(result);
  }

  void HandleClose(const std::shared_ptr<op_control_interfaces::srv::Close::Request> request,
                   std::shared_ptr<op_control_interfaces::srv::Close::Response> response) {
    std::lock_guard<std::mutex> lock(motion_mutex_);
    Result result = Execute(0.0f, request->force, request->speed);
    response->success = (result == Result::kSuccess || result == Result::kGrasped);
    response->result_code = static_cast<std::int8_t>(result);
  }

  void HandleSetPosition(
      const std::shared_ptr<op_control_interfaces::srv::SetPosition::Request> request,
      std::shared_ptr<op_control_interfaces::srv::SetPosition::Response> response) {
    std::lock_guard<std::mutex> lock(motion_mutex_);
    if (request->position < 0.0f || request->position > 1.0f || request->speed < 0.0f ||
        request->speed > 1.0f) {
      response->success = false;
      response->result_code = static_cast<std::int8_t>(Result::kInvalidParam);
      return;
    }

    const Result result = Execute(request->position, open_force_, request->speed);
    response->success = (result == Result::kSuccess || result == Result::kGrasped);
    response->result_code = static_cast<std::int8_t>(result);
  }

  Result Execute(float position, float force, float speed) {
    if (!driver_.IsConnected() && !driver_.Connect(port_, baudrate_)) {
      return Result::kSerialError;
    }

    Result result = driver_.Execute(position, force, speed, motion_acc_, motion_dec_);
    if (result != Result::kSerialError) {
      return result;
    }

    driver_.Disconnect();
    if (!driver_.Connect(port_, baudrate_)) {
      return Result::kSerialError;
    }
    return driver_.Execute(position, force, speed, motion_acc_, motion_dec_);
  }

  Driver driver_;
  std::string port_;
  int baudrate_ = kDefaultBaudrate;
  std::mutex motion_mutex_;
  float open_force_ = 0.4f;
  float motion_acc_ = 0.5f;
  float motion_dec_ = 0.5f;
  rclcpp::Publisher<op_control_interfaces::msg::OmniPickerState>::SharedPtr state_pub_;
  rclcpp::Service<op_control_interfaces::srv::Open>::SharedPtr open_srv_;
  rclcpp::Service<op_control_interfaces::srv::Close>::SharedPtr close_srv_;
  rclcpp::Service<op_control_interfaces::srv::SetPosition>::SharedPtr set_position_srv_;
};

}  // namespace op_control

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<op_control::OpControlNode>();
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();
  rclcpp::shutdown();
  return 0;
}
