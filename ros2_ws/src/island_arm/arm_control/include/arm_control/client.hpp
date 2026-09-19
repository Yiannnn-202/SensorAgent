#ifndef ARM_CONTROL__CLIENT_HPP_
#define ARM_CONTROL__CLIENT_HPP_

#include <memory>
#include <string>
#include <vector>

#include "arm_control_interfaces/srv/get_current_pose.hpp"
#include "arm_control_interfaces/srv/init.hpp"
#include "arm_control_interfaces/srv/move_j.hpp"
#include "arm_control_interfaces/srv/move_j_deg.hpp"
#include "arm_control_interfaces/srv/move_j_rlt_deg.hpp"
#include "arm_control_interfaces/srv/move_l.hpp"
#include "arm_control_interfaces/srv/move_to_pose.hpp"
#include "geometry_msgs/msg/pose.hpp"
#include "rclcpp/rclcpp.hpp"

namespace arm_control {

// Simple synchronous client for arm_control services.
// Suitable for C++ nodes or tools that want a blocking call interface.
class ArmControlClient {
 public:
  explicit ArmControlClient(rclcpp::Node::SharedPtr node);

  bool MoveJ(const std::vector<double>& joints_rad, uint8_t speed = 20, bool block = true);
  bool MoveJDeg(const std::vector<double>& joints_deg, uint8_t speed = 20, bool block = true);
  bool MoveJRltDeg(const std::vector<double>& delta_joints_deg, uint8_t speed = 20,
                   bool block = true);
  bool MoveL(const geometry_msgs::msg::Pose& pose, uint8_t speed = 20, bool block = true);
  bool MoveToPose(const geometry_msgs::msg::Pose& pose, uint8_t speed = 20, bool block = true);
  bool Init();
  bool GetCurrentPose(geometry_msgs::msg::Pose& pose);

 private:
  template <typename ServiceT>
  bool CallService(const typename rclcpp::Client<ServiceT>::SharedPtr& client,
                   const std::shared_ptr<typename ServiceT::Request>& request);

  rclcpp::Node::SharedPtr node_;

  rclcpp::Client<arm_control_interfaces::srv::MoveJ>::SharedPtr cli_move_j_;
  rclcpp::Client<arm_control_interfaces::srv::MoveJDeg>::SharedPtr cli_move_j_deg_;
  rclcpp::Client<arm_control_interfaces::srv::MoveJRltDeg>::SharedPtr cli_move_j_rlt_deg_;
  rclcpp::Client<arm_control_interfaces::srv::MoveL>::SharedPtr cli_move_l_;
  rclcpp::Client<arm_control_interfaces::srv::MoveToPose>::SharedPtr cli_move_to_pose_;
  rclcpp::Client<arm_control_interfaces::srv::Init>::SharedPtr cli_init_;
  rclcpp::Client<arm_control_interfaces::srv::GetCurrentPose>::SharedPtr cli_get_current_pose_;
};

}  // namespace arm_control

#endif  // ARM_CONTROL__CLIENT_HPP_
