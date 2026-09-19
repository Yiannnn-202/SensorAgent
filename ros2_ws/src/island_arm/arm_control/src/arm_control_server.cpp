#include <chrono>
#include <cmath>
#include <thread>

#include "arm_control/server.hpp"
#include "rclcpp/qos.hpp"

namespace arm_control {

namespace {

constexpr double kJointToleranceRad = 0.01;  // ~0.57 deg

}  // namespace

ArmControlServer::ArmControlServer(const rclcpp::NodeOptions& options)
    : Node("arm_control_server", options) {
  callback_group_services_ =
      this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  callback_group_subscriptions_ =
      this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

  // Parameters.
  this->declare_parameter<std::vector<double>>("home_joints_rad", {0.0, 0.0, 0.0, 0.0, 0.0, 0.0});
  this->declare_parameter<int>("default_speed", 20);
  this->declare_parameter<double>("motion_timeout_sec", 10.0);
  this->declare_parameter<int>("arm_dof", 6);

  home_joints_rad_ = this->get_parameter("home_joints_rad").as_double_array();
  default_speed_ = this->get_parameter("default_speed").as_int();
  motion_timeout_sec_ = this->get_parameter("motion_timeout_sec").as_double();
  arm_dof_ = this->get_parameter("arm_dof").as_int();

  if (static_cast<int>(home_joints_rad_.size()) != arm_dof_) {
    RCLCPP_WARN(this->get_logger(), "home_joints_rad size (%zu) does not match arm_dof (%d).",
                home_joints_rad_.size(), arm_dof_);
  }

  // Publishers to rm_driver.
  pub_move_j_ = this->create_publisher<rm_ros_interfaces::msg::Movej>("rm_driver/movej_cmd",
                                                                      rclcpp::ParametersQoS());
  pub_move_l_ = this->create_publisher<rm_ros_interfaces::msg::Movel>("rm_driver/movel_cmd",
                                                                      rclcpp::ParametersQoS());
  pub_move_j_p_ = this->create_publisher<rm_ros_interfaces::msg::Movejp>("rm_driver/movej_p_cmd",
                                                                         rclcpp::ParametersQoS());
  pub_get_state_cmd_ = this->create_publisher<std_msgs::msg::Empty>(
      "rm_driver/get_current_arm_state_cmd", rclcpp::ParametersQoS());
  pub_current_joint_states_ = this->create_publisher<sensor_msgs::msg::JointState>(
      "rm_driver/current_joint_states", rclcpp::ParametersQoS());

  // Subscribers from rm_driver.
  rclcpp::SubscriptionOptions sub_options;
  sub_options.callback_group = callback_group_subscriptions_;
  sub_move_l_result_ = this->create_subscription<std_msgs::msg::Bool>(
      "rm_driver/movel_result", rclcpp::ParametersQoS(),
      std::bind(&ArmControlServer::OnMoveLResult, this, std::placeholders::_1), sub_options);
  sub_move_j_result_ = this->create_subscription<std_msgs::msg::Bool>(
      "rm_driver/movej_result", rclcpp::ParametersQoS(),
      std::bind(&ArmControlServer::OnMoveJResult, this, std::placeholders::_1), sub_options);
  sub_move_j_p_result_ = this->create_subscription<std_msgs::msg::Bool>(
      "rm_driver/movej_p_result", rclcpp::ParametersQoS(),
      std::bind(&ArmControlServer::OnMoveJPResult, this, std::placeholders::_1), sub_options);
  sub_arm_state_ = this->create_subscription<rm_ros_interfaces::msg::Armstate>(
      "rm_driver/get_current_arm_state_result", rclcpp::ParametersQoS(),
      std::bind(&ArmControlServer::OnArmState, this, std::placeholders::_1), sub_options);

  current_state_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(200), [this]() {
        pub_get_state_cmd_->publish(std_msgs::msg::Empty());
      }, callback_group_subscriptions_);
  // Service servers.
  srv_move_j_ = this->create_service<arm_control_interfaces::srv::MoveJ>(
      "/task/arm/movej", std::bind(&ArmControlServer::HandleMoveJ, this, std::placeholders::_1,
                                    std::placeholders::_2),
      rmw_qos_profile_services_default, callback_group_services_);
  srv_move_l_ = this->create_service<arm_control_interfaces::srv::MoveL>(
      "/task/arm/movel", std::bind(&ArmControlServer::HandleMoveL, this, std::placeholders::_1,
                                    std::placeholders::_2),
      rmw_qos_profile_services_default, callback_group_services_);
  srv_move_to_pose_ = this->create_service<arm_control_interfaces::srv::MoveToPose>(
      "/task/arm/move_to_pose", std::bind(&ArmControlServer::HandleMoveToPose, this,
                                           std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, callback_group_services_);
  srv_move_j_deg_ = this->create_service<arm_control_interfaces::srv::MoveJDeg>(
      "/task/arm/movej_deg", std::bind(&ArmControlServer::HandleMoveJDeg, this,
                                        std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, callback_group_services_);
  srv_move_j_rlt_deg_ = this->create_service<arm_control_interfaces::srv::MoveJRltDeg>(
      "/task/arm/movej_rltdegree", std::bind(&ArmControlServer::HandleMoveJRltDeg, this,
                                              std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, callback_group_services_);
  srv_init_ = this->create_service<arm_control_interfaces::srv::Init>(
      "/task/arm/init",
      std::bind(&ArmControlServer::HandleInit, this, std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, callback_group_services_);
  srv_get_current_pose_ = this->create_service<arm_control_interfaces::srv::GetCurrentPose>(
      "/task/arm/get_current_pose", std::bind(&ArmControlServer::HandleGetCurrentPose, this,
                                               std::placeholders::_1, std::placeholders::_2),
      rmw_qos_profile_services_default, callback_group_services_);

  // Action server.
  action_server_ = rclcpp_action::create_server<ExecuteTrajectory>(
      this, "/task/arm/execute_trajectory",
      std::bind(&ArmControlServer::HandleTrajectoryGoal, this, std::placeholders::_1,
                std::placeholders::_2),
      std::bind(&ArmControlServer::HandleTrajectoryCancel, this, std::placeholders::_1),
      std::bind(&ArmControlServer::HandleTrajectoryAccepted, this, std::placeholders::_1));

  RCLCPP_INFO(this->get_logger(), "arm_control_server ready.");
}

void ArmControlServer::HandleMoveJ(
    const std::shared_ptr<arm_control_interfaces::srv::MoveJ::Request> request,
    std::shared_ptr<arm_control_interfaces::srv::MoveJ::Response> response) {
  if (IsBusy()) {
    response->success = false;
    response->error_code = static_cast<int32_t>(ErrorCode::kBusy);
    response->message = "Arm is busy.";
    return;
  }

  if (static_cast<int>(request->joints.size()) != arm_dof_) {
    response->success = false;
    response->error_code = static_cast<int32_t>(ErrorCode::kInvalidRequest);
    response->message = "joints size mismatch.";
    return;
  }

  SetState(ArmState::kMoving);

  {
    std::lock_guard<std::mutex> lock(target_mutex_);
    target_joints_rad_.assign(request->joints.begin(), request->joints.end());
    has_joint_target_ = true;
    has_pose_target_ = false;
  }

  rm_ros_interfaces::msg::Movej cmd;
  cmd.joint.resize(arm_dof_);
  for (int i = 0; i < arm_dof_; ++i) {
    cmd.joint[i] = static_cast<float>(request->joints[i]);
  }
  cmd.speed = request->speed > 0 ? request->speed : static_cast<uint8_t>(default_speed_);
  cmd.block = request->block;
  cmd.trajectory_connect = 0;
  cmd.dof = arm_dof_;

  if (request->block) {
    {
      std::lock_guard<std::mutex> lock(result_mutex_);
      move_j_done_ = false;
      move_j_success_ = false;
    }
    pub_move_j_->publish(cmd);

    std::unique_lock<std::mutex> lock(result_mutex_);
    const bool finished = result_cv_.wait_for(
        lock, std::chrono::duration<double>(motion_timeout_sec_),
        [this]() { return move_j_done_; });
    response->success = finished && move_j_success_;
    response->error_code =
        response->success
            ? static_cast<int32_t>(ErrorCode::kOk)
            : static_cast<int32_t>(finished ? ErrorCode::kArmDriverError : ErrorCode::kTimeout);
    response->message = response->success ? "OK" : (finished ? "Arm driver rejected motion."
                                                               : "Timeout waiting for motion.");
  } else {
    pub_move_j_->publish(cmd);
    response->success = true;
    response->error_code = static_cast<int32_t>(ErrorCode::kOk);
    response->message = "Command accepted (non-blocking).";
  }
}

void ArmControlServer::HandleMoveL(
    const std::shared_ptr<arm_control_interfaces::srv::MoveL::Request> request,
    std::shared_ptr<arm_control_interfaces::srv::MoveL::Response> response) {
  if (IsBusy()) {
    response->success = false;
    response->error_code = static_cast<int32_t>(ErrorCode::kBusy);
    response->message = "Arm is busy.";
    return;
  }

  SetState(ArmState::kMoving);

  {
    std::lock_guard<std::mutex> lock(target_mutex_);
    target_pose_ = request->pose;
    has_joint_target_ = false;
    has_pose_target_ = true;
  }

  rm_ros_interfaces::msg::Movel cmd;
  cmd.pose = request->pose;
  cmd.speed = request->speed > 0 ? request->speed : static_cast<uint8_t>(default_speed_);
  cmd.trajectory_connect = 0;
  cmd.block = request->block;

  if (request->block) {
    {
      std::lock_guard<std::mutex> lock(result_mutex_);
      move_l_done_ = false;
      move_l_success_ = false;
    }
    pub_move_l_->publish(cmd);

    std::unique_lock<std::mutex> lock(result_mutex_);
    const bool finished = result_cv_.wait_for(
        lock, std::chrono::duration<double>(motion_timeout_sec_), [this]() { return move_l_done_; });
    response->success = finished && move_l_success_;
    response->error_code = response->success ? static_cast<int32_t>(ErrorCode::kOk)
                                             : static_cast<int32_t>(ErrorCode::kTimeout);
    response->message = response->success ? "OK" : "Timeout or motion failed.";
  } else {
    pub_move_l_->publish(cmd);
    response->success = true;
    response->error_code = static_cast<int32_t>(ErrorCode::kOk);
    response->message = "Command accepted (non-blocking).";
  }
}

void ArmControlServer::HandleMoveToPose(
    const std::shared_ptr<arm_control_interfaces::srv::MoveToPose::Request> request,
    std::shared_ptr<arm_control_interfaces::srv::MoveToPose::Response> response) {
  if (IsBusy()) {
    response->success = false;
    response->error_code = static_cast<int32_t>(ErrorCode::kBusy);
    response->message = "Arm is busy.";
    return;
  }

  SetState(ArmState::kMoving);

  rm_ros_interfaces::msg::Movejp cmd;
  cmd.pose = request->pose;
  cmd.speed = request->speed > 0 ? request->speed : static_cast<uint8_t>(default_speed_);
  cmd.trajectory_connect = 0;
  cmd.block = request->block;

  {
    std::lock_guard<std::mutex> lock(result_mutex_);
    move_j_p_done_ = false;
    move_j_p_success_ = false;
  }

  pub_move_j_p_->publish(cmd);

  if (request->block) {
    std::unique_lock<std::mutex> lock(result_mutex_);
    bool finished = result_cv_.wait_for(lock, std::chrono::duration<double>(motion_timeout_sec_),
                                        [this]() { return move_j_p_done_; });
    response->success = finished && move_j_p_success_;
    response->error_code = response->success ? static_cast<int32_t>(ErrorCode::kOk)
                                             : static_cast<int32_t>(ErrorCode::kTimeout);
    response->message = response->success ? "OK" : "Timeout or motion failed.";
  } else {
    response->success = true;
    response->error_code = static_cast<int32_t>(ErrorCode::kOk);
    response->message = "Command accepted (non-blocking).";
  }
}

void ArmControlServer::HandleMoveJDeg(
    const std::shared_ptr<arm_control_interfaces::srv::MoveJDeg::Request> request,
    std::shared_ptr<arm_control_interfaces::srv::MoveJDeg::Response> response) {
  auto req_rad = std::make_shared<arm_control_interfaces::srv::MoveJ::Request>();
  for (size_t i = 0; i < request->joints.size(); ++i) {
    req_rad->joints[i] = request->joints[i] * kDegToRad;
  }
  req_rad->speed = request->speed;
  req_rad->block = request->block;

  auto res_rad = std::make_shared<arm_control_interfaces::srv::MoveJ::Response>();
  HandleMoveJ(req_rad, res_rad);

  response->success = res_rad->success;
  response->error_code = res_rad->error_code;
  response->message = res_rad->message;
}

void ArmControlServer::HandleMoveJRltDeg(
    const std::shared_ptr<arm_control_interfaces::srv::MoveJRltDeg::Request> /*request*/,
    std::shared_ptr<arm_control_interfaces::srv::MoveJRltDeg::Response> response) {
  // Query current pose/joints to compute absolute target.
  // For skeleton, we request current state and compute from there.
  pub_get_state_cmd_->publish(std_msgs::msg::Empty());

  // Wait a short while for state update.
  {
    std::unique_lock<std::mutex> lock(pose_mutex_);
    bool got_state = pose_cv_.wait_for(lock, std::chrono::milliseconds(500),
                                       [this]() { return current_pose_valid_; });
    if (!got_state) {
      response->success = false;
      response->error_code = static_cast<int32_t>(ErrorCode::kTimeout);
      response->message = "Failed to get current arm state.";
      return;
    }
  }

  // TODO: current_pose_ only gives Cartesian pose. For relative joint motion we need
  // current joint states. Subscribe to /joint_states to implement this properly.
  response->success = false;
  response->error_code = static_cast<int32_t>(ErrorCode::kInternalError);
  response->message = "MoveJRltDeg not fully implemented in skeleton.";
}

void ArmControlServer::HandleInit(
    const std::shared_ptr<arm_control_interfaces::srv::Init::Request> /*request*/,
    std::shared_ptr<arm_control_interfaces::srv::Init::Response> response) {
  auto req = std::make_shared<arm_control_interfaces::srv::MoveJ::Request>();
  for (size_t i = 0; i < home_joints_rad_.size() && i < req->joints.size(); ++i) {
    req->joints[i] = home_joints_rad_[i];
  }
  req->speed = default_speed_;
  req->block = true;

  auto res = std::make_shared<arm_control_interfaces::srv::MoveJ::Response>();
  HandleMoveJ(req, res);

  response->success = res->success;
  response->error_code = res->error_code;
  response->message = res->message;
}

void ArmControlServer::HandleGetCurrentPose(
    const std::shared_ptr<arm_control_interfaces::srv::GetCurrentPose::Request> /*request*/,
    std::shared_ptr<arm_control_interfaces::srv::GetCurrentPose::Response> response) {
  {
    std::lock_guard<std::mutex> lock(pose_mutex_);
    current_pose_valid_ = false;
  }
  pub_get_state_cmd_->publish(std_msgs::msg::Empty());

  {
    std::unique_lock<std::mutex> lock(pose_mutex_);
    bool got_state = pose_cv_.wait_for(lock, std::chrono::milliseconds(1000),
                                       [this]() { return current_pose_valid_; });
    if (!got_state) {
      response->valid = false;
      response->error_code = static_cast<int32_t>(ErrorCode::kTimeout);
      response->message = "Timeout waiting for arm state.";
      return;
    }
    response->pose = current_pose_;
    response->valid = true;
    response->error_code = static_cast<int32_t>(ErrorCode::kOk);
    response->message = "OK";
  }
}

rclcpp_action::GoalResponse ArmControlServer::HandleTrajectoryGoal(
    const rclcpp_action::GoalUUID& /*uuid*/,
    std::shared_ptr<const ExecuteTrajectory::Goal> /*goal*/) {
  if (IsBusy()) {
    return rclcpp_action::GoalResponse::REJECT;
  }
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

rclcpp_action::CancelResponse ArmControlServer::HandleTrajectoryCancel(
    const std::shared_ptr<GoalHandleExecuteTrajectory> /*goal_handle*/) {
  RCLCPP_INFO(this->get_logger(), "Trajectory cancel requested.");
  return rclcpp_action::CancelResponse::ACCEPT;
}

void ArmControlServer::HandleTrajectoryAccepted(
    const std::shared_ptr<GoalHandleExecuteTrajectory> goal_handle) {
  std::thread{std::bind(&ArmControlServer::ExecuteTrajectoryLoop, this, std::placeholders::_1),
              goal_handle}
      .detach();
}

void ArmControlServer::ExecuteTrajectoryLoop(
    const std::shared_ptr<GoalHandleExecuteTrajectory> goal_handle) {
  const auto goal = goal_handle->get_goal();
  auto result = std::make_shared<ExecuteTrajectory::Result>();

  SetState(ArmState::kMoving);
  uint16_t reached = 0;

  for (size_t i = 0; i < goal->waypoints.size(); ++i) {
    if (goal_handle->is_canceling()) {
      result->success = false;
      result->error_code = static_cast<int32_t>(ErrorCode::kTimeout);
      result->message = "Canceled by user.";
      result->reached_index = reached;
      goal_handle->canceled(result);
      SetState(ArmState::kIdle);
      return;
    }

    auto req = std::make_shared<arm_control_interfaces::srv::MoveToPose::Request>();
    req->pose = goal->waypoints[i];
    req->speed = goal->speed > 0 ? goal->speed : default_speed_;
    req->block = true;

    auto res = std::make_shared<arm_control_interfaces::srv::MoveToPose::Response>();
    HandleMoveToPose(req, res);

    if (!res->success) {
      result->success = false;
      result->error_code = res->error_code;
      result->message = res->message;
      result->reached_index = reached;
      goal_handle->abort(result);
      SetState(ArmState::kIdle);
      return;
    }

    reached = static_cast<uint16_t>(i);
    auto feedback = std::make_shared<ExecuteTrajectory::Feedback>();
    feedback->current_index = reached;
    feedback->current_pose = current_pose_;
    feedback->state = "moving";
    goal_handle->publish_feedback(feedback);
  }

  result->success = true;
  result->error_code = static_cast<int32_t>(ErrorCode::kOk);
  result->message = "Trajectory completed.";
  result->reached_index = reached;
  goal_handle->succeed(result);
  SetState(ArmState::kIdle);
}

void ArmControlServer::OnMoveJResult(const std_msgs::msg::Bool::SharedPtr msg) {
  {
    std::lock_guard<std::mutex> lock(result_mutex_);
    move_j_done_ = true;
    move_j_success_ = msg->data;
  }
  result_cv_.notify_all();
  SetState(msg->data ? ArmState::kIdle : ArmState::kError);
}

void ArmControlServer::OnMoveLResult(const std_msgs::msg::Bool::SharedPtr msg) {
  {
    std::lock_guard<std::mutex> lock(result_mutex_);
    move_l_done_ = true;
    move_l_success_ = msg->data;
  }
  result_cv_.notify_all();

  SetState(msg->data ? ArmState::kIdle : ArmState::kError);
}

void ArmControlServer::OnMoveJPResult(const std_msgs::msg::Bool::SharedPtr msg) {
  {
    std::lock_guard<std::mutex> lock(result_mutex_);
    move_j_p_done_ = true;
    move_j_p_success_ = msg->data;
  }
  result_cv_.notify_all();

  if (msg->data) {
    SetState(ArmState::kIdle);
  } else {
    SetState(ArmState::kError);
  }
}

void ArmControlServer::OnArmState(const rm_ros_interfaces::msg::Armstate::SharedPtr msg) {
  {
    std::lock_guard<std::mutex> lock(pose_mutex_);
    current_pose_ = msg->pose;
    current_joints_rad_.assign(msg->joint.begin(), msg->joint.end());
    current_pose_valid_ = true;
    current_joint_state_valid_ = current_joints_rad_.size() >= static_cast<size_t>(arm_dof_);
  }
  if (msg->joint.size() >= static_cast<size_t>(arm_dof_)) {
    sensor_msgs::msg::JointState joint_state;
    joint_state.header.stamp = this->now();
    joint_state.name = {"joint1", "joint2", "joint3", "joint4", "joint5", "joint6"};
    joint_state.position.assign(msg->joint.begin(), msg->joint.begin() + arm_dof_);
    pub_current_joint_states_->publish(joint_state);
  }
  pose_cv_.notify_all();
}

bool ArmControlServer::WaitForMoveComplete(double timeout_sec) {
  auto start = this->now();
  while (rclcpp::ok() && (this->now() - start).seconds() < timeout_sec) {
    if (state_.load() == ArmState::kError) {
      return false;
    }

    pub_get_state_cmd_->publish(std_msgs::msg::Empty());

    bool reached = false;
    {
      std::lock_guard<std::mutex> target_lock(target_mutex_);
      std::lock_guard<std::mutex> pose_lock(pose_mutex_);
      if (has_joint_target_ && current_joint_state_valid_) {
        reached = true;
        for (int i = 0; i < arm_dof_; ++i) {
          if (std::fabs(current_joints_rad_[i] - target_joints_rad_[i]) > kJointToleranceRad) {
            reached = false;
            break;
          }
        }
      }
    }
    if (reached) {
      SetState(ArmState::kIdle);
      std::lock_guard<std::mutex> lock(target_mutex_);
      has_joint_target_ = false;
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  SetState(ArmState::kIdle);
  {
    std::lock_guard<std::mutex> lock(target_mutex_);
    has_joint_target_ = false;
    has_pose_target_ = false;
  }
  return false;
}

bool ArmControlServer::IsBusy() const { return state_.load() == ArmState::kMoving; }

void ArmControlServer::SetState(ArmState state) { state_.store(state); }

}  // namespace arm_control
