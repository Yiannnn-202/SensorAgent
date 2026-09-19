#include <chrono>

#include "arm_control/client.hpp"

namespace arm_control {

namespace {

constexpr std::chrono::seconds kServiceTimeout{3};
constexpr std::chrono::seconds kCallTimeout{30};

template <typename ServiceT>
bool WaitForService(const typename rclcpp::Client<ServiceT>::SharedPtr& client,
                    rclcpp::Node::SharedPtr node) {
  if (!client->wait_for_service(kServiceTimeout)) {
    RCLCPP_ERROR(node->get_logger(), "Service %s not available.", client->get_service_name());
    return false;
  }
  return true;
}

template <typename ServiceT>
bool CallServiceImpl(const typename rclcpp::Client<ServiceT>::SharedPtr& client,
                     const std::shared_ptr<typename ServiceT::Request>& request,
                     rclcpp::Node::SharedPtr node) {
  if (!WaitForService<ServiceT>(client, node)) {
    return false;
  }
  auto future = client->async_send_request(request);
  if (rclcpp::spin_until_future_complete(node, future, kCallTimeout) !=
      rclcpp::FutureReturnCode::SUCCESS) {
    RCLCPP_ERROR(node->get_logger(), "Service call to %s timed out.", client->get_service_name());
    return false;
  }
  return future.get()->success;
}

}  // namespace

ArmControlClient::ArmControlClient(rclcpp::Node::SharedPtr node) : node_(node) {
  cli_move_j_ = node_->create_client<arm_control_interfaces::srv::MoveJ>("/task/arm/movej");
  cli_move_j_deg_ =
      node_->create_client<arm_control_interfaces::srv::MoveJDeg>("/task/arm/movej_deg");
  cli_move_j_rlt_deg_ =
      node_->create_client<arm_control_interfaces::srv::MoveJRltDeg>("/task/arm/movej_rltdegree");
  cli_move_l_ = node_->create_client<arm_control_interfaces::srv::MoveL>("/task/arm/movel");
  cli_move_to_pose_ =
      node_->create_client<arm_control_interfaces::srv::MoveToPose>("/task/arm/move_to_pose");
  cli_init_ = node_->create_client<arm_control_interfaces::srv::Init>("/task/arm/init");
  cli_get_current_pose_ = node_->create_client<arm_control_interfaces::srv::GetCurrentPose>(
      "/task/arm/get_current_pose");
}

bool ArmControlClient::MoveJ(const std::vector<double>& joints_rad, uint8_t speed, bool block) {
  auto request = std::make_shared<arm_control_interfaces::srv::MoveJ::Request>();
  for (size_t i = 0; i < request->joints.size(); ++i) {
    request->joints[i] = joints_rad[i];
  }
  request->speed = speed;
  request->block = block;
  return CallServiceImpl<arm_control_interfaces::srv::MoveJ>(cli_move_j_, request, node_);
}

bool ArmControlClient::MoveJDeg(const std::vector<double>& joints_deg, uint8_t speed, bool block) {
  auto request = std::make_shared<arm_control_interfaces::srv::MoveJDeg::Request>();
  for (size_t i = 0; i < request->joints.size(); ++i) {
    request->joints[i] = joints_deg[i];
  }
  request->speed = speed;
  request->block = block;
  return CallServiceImpl<arm_control_interfaces::srv::MoveJDeg>(cli_move_j_deg_, request, node_);
}

bool ArmControlClient::MoveJRltDeg(const std::vector<double>& delta_joints_deg, uint8_t speed,
                                   bool block) {
  auto request = std::make_shared<arm_control_interfaces::srv::MoveJRltDeg::Request>();
  for (size_t i = 0; i < request->delta_joints.size(); ++i) {
    request->delta_joints[i] = delta_joints_deg[i];
  }
  request->speed = speed;
  request->block = block;
  return CallServiceImpl<arm_control_interfaces::srv::MoveJRltDeg>(cli_move_j_rlt_deg_, request,
                                                                   node_);
}

bool ArmControlClient::MoveL(const geometry_msgs::msg::Pose& pose, uint8_t speed, bool block) {
  auto request = std::make_shared<arm_control_interfaces::srv::MoveL::Request>();
  request->pose = pose;
  request->speed = speed;
  request->block = block;
  return CallServiceImpl<arm_control_interfaces::srv::MoveL>(cli_move_l_, request, node_);
}

bool ArmControlClient::MoveToPose(const geometry_msgs::msg::Pose& pose, uint8_t speed, bool block) {
  auto request = std::make_shared<arm_control_interfaces::srv::MoveToPose::Request>();
  request->pose = pose;
  request->speed = speed;
  request->block = block;
  return CallServiceImpl<arm_control_interfaces::srv::MoveToPose>(cli_move_to_pose_, request,
                                                                  node_);
}

bool ArmControlClient::Init() {
  auto request = std::make_shared<arm_control_interfaces::srv::Init::Request>();
  return CallServiceImpl<arm_control_interfaces::srv::Init>(cli_init_, request, node_);
}

bool ArmControlClient::GetCurrentPose(geometry_msgs::msg::Pose& pose) {
  if (!WaitForService<arm_control_interfaces::srv::GetCurrentPose>(cli_get_current_pose_, node_)) {
    return false;
  }
  auto request = std::make_shared<arm_control_interfaces::srv::GetCurrentPose::Request>();
  auto future = cli_get_current_pose_->async_send_request(request);
  if (rclcpp::spin_until_future_complete(node_, future, std::chrono::seconds(2)) !=
      rclcpp::FutureReturnCode::SUCCESS) {
    return false;
  }
  auto response = future.get();
  pose = response->pose;
  return response->valid;
}

}  // namespace arm_control
