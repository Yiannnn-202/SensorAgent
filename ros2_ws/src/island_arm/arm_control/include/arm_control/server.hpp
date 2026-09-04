#ifndef ARM_CONTROL__SERVER_HPP_
#define ARM_CONTROL__SERVER_HPP_

#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "arm_control/types.hpp"
#include "arm_control_interfaces/action/execute_trajectory.hpp"
#include "arm_control_interfaces/srv/get_current_pose.hpp"
#include "arm_control_interfaces/srv/init.hpp"
#include "arm_control_interfaces/srv/move_j.hpp"
#include "arm_control_interfaces/srv/move_j_deg.hpp"
#include "arm_control_interfaces/srv/move_j_rlt_deg.hpp"
#include "arm_control_interfaces/srv/move_l.hpp"
#include "arm_control_interfaces/srv/move_to_pose.hpp"
#include "geometry_msgs/msg/pose.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "rm_ros_interfaces/msg/armstate.hpp"
#include "rm_ros_interfaces/msg/movej.hpp"
#include "rm_ros_interfaces/msg/movejp.hpp"
#include "rm_ros_interfaces/msg/movel.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/empty.hpp"

namespace arm_control {

class ArmControlServer : public rclcpp::Node {
 public:
  explicit ArmControlServer(const rclcpp::NodeOptions& options = rclcpp::NodeOptions());

 private:
  using ExecuteTrajectory = arm_control_interfaces::action::ExecuteTrajectory;
  using GoalHandleExecuteTrajectory = rclcpp_action::ServerGoalHandle<ExecuteTrajectory>;

  // Service callbacks.
  void HandleMoveJ(const std::shared_ptr<arm_control_interfaces::srv::MoveJ::Request> request,
                   std::shared_ptr<arm_control_interfaces::srv::MoveJ::Response> response);

  void HandleMoveL(const std::shared_ptr<arm_control_interfaces::srv::MoveL::Request> request,
                   std::shared_ptr<arm_control_interfaces::srv::MoveL::Response> response);

  void HandleMoveToPose(
      const std::shared_ptr<arm_control_interfaces::srv::MoveToPose::Request> request,
      std::shared_ptr<arm_control_interfaces::srv::MoveToPose::Response> response);

  void HandleMoveJDeg(const std::shared_ptr<arm_control_interfaces::srv::MoveJDeg::Request> request,
                      std::shared_ptr<arm_control_interfaces::srv::MoveJDeg::Response> response);

  void HandleMoveJRltDeg(
      const std::shared_ptr<arm_control_interfaces::srv::MoveJRltDeg::Request> request,
      std::shared_ptr<arm_control_interfaces::srv::MoveJRltDeg::Response> response);

  void HandleInit(const std::shared_ptr<arm_control_interfaces::srv::Init::Request> request,
                  std::shared_ptr<arm_control_interfaces::srv::Init::Response> response);

  void HandleGetCurrentPose(
      const std::shared_ptr<arm_control_interfaces::srv::GetCurrentPose::Request> request,
      std::shared_ptr<arm_control_interfaces::srv::GetCurrentPose::Response> response);

  // Action callbacks.
  rclcpp_action::GoalResponse HandleTrajectoryGoal(
      const rclcpp_action::GoalUUID& uuid, std::shared_ptr<const ExecuteTrajectory::Goal> goal);

  rclcpp_action::CancelResponse HandleTrajectoryCancel(
      const std::shared_ptr<GoalHandleExecuteTrajectory> goal_handle);

  void HandleTrajectoryAccepted(const std::shared_ptr<GoalHandleExecuteTrajectory> goal_handle);

  void ExecuteTrajectoryLoop(const std::shared_ptr<GoalHandleExecuteTrajectory> goal_handle);

  // State / result callbacks from rm_driver.
  void OnMoveJResult(const std_msgs::msg::Bool::SharedPtr msg);
  void OnMoveLResult(const std_msgs::msg::Bool::SharedPtr msg);
  void OnMoveJPResult(const std_msgs::msg::Bool::SharedPtr msg);
  void OnArmState(const rm_ros_interfaces::msg::Armstate::SharedPtr msg);

  // Helpers.
  bool WaitForMoveComplete(double timeout_sec);
  bool IsBusy() const;
  void SetState(ArmState state);

  // Parameters.
  std::vector<double> home_joints_rad_;
  int default_speed_;
  double motion_timeout_sec_;
  int arm_dof_;

  // Internal state.
  std::atomic<ArmState> state_{ArmState::kIdle};
  std::mutex pose_mutex_;
  std::condition_variable pose_cv_;
  geometry_msgs::msg::Pose current_pose_;
  std::vector<double> current_joints_rad_;
  bool current_pose_valid_{false};
  bool current_joint_state_valid_{false};

  // Targets for blocking wait.
  std::mutex target_mutex_;
  std::vector<double> target_joints_rad_;
  geometry_msgs::msg::Pose target_pose_;
  bool has_joint_target_{false};
  bool has_pose_target_{false};

  // Service callbacks wait for driver feedback, so feedback subscriptions must
  // execute in a separate callback group.
  rclcpp::CallbackGroup::SharedPtr callback_group_services_;
  rclcpp::CallbackGroup::SharedPtr callback_group_subscriptions_;

  // Service servers.
  rclcpp::Service<arm_control_interfaces::srv::MoveJ>::SharedPtr srv_move_j_;
  rclcpp::Service<arm_control_interfaces::srv::MoveL>::SharedPtr srv_move_l_;
  rclcpp::Service<arm_control_interfaces::srv::MoveToPose>::SharedPtr srv_move_to_pose_;
  rclcpp::Service<arm_control_interfaces::srv::MoveJDeg>::SharedPtr srv_move_j_deg_;
  rclcpp::Service<arm_control_interfaces::srv::MoveJRltDeg>::SharedPtr srv_move_j_rlt_deg_;
  rclcpp::Service<arm_control_interfaces::srv::Init>::SharedPtr srv_init_;
  rclcpp::Service<arm_control_interfaces::srv::GetCurrentPose>::SharedPtr srv_get_current_pose_;

  // Action server.
  rclcpp_action::Server<ExecuteTrajectory>::SharedPtr action_server_;

  // Publishers to rm_driver.
  rclcpp::Publisher<rm_ros_interfaces::msg::Movej>::SharedPtr pub_move_j_;
  rclcpp::Publisher<rm_ros_interfaces::msg::Movel>::SharedPtr pub_move_l_;
  rclcpp::Publisher<rm_ros_interfaces::msg::Movejp>::SharedPtr pub_move_j_p_;
  rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr pub_get_state_cmd_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr pub_current_joint_states_;

  // Subscribers from rm_driver.
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_move_l_result_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_move_j_result_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_move_j_p_result_;
  rclcpp::Subscription<rm_ros_interfaces::msg::Armstate>::SharedPtr sub_arm_state_;

  rclcpp::TimerBase::SharedPtr current_state_timer_;

  // Synchronization primitives for blocking motion.
  std::mutex result_mutex_;
  std::condition_variable result_cv_;
  bool move_j_done_{false};
  bool move_j_success_{false};
  bool move_l_done_{false};
  bool move_l_success_{false};
  bool move_j_p_done_{false};
  bool move_j_p_success_{false};
};

}  // namespace arm_control

#endif  // ARM_CONTROL__SERVER_HPP_
