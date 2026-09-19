#include <gtest/gtest.h>

#include <memory>

#include "arm_control/client.hpp"
#include "rclcpp/rclcpp.hpp"

class ArmControlClientTest : public ::testing::Test {
 protected:
  void SetUp() override {
    rclcpp::init(0, nullptr);
    node_ = std::make_shared<rclcpp::Node>("test_arm_control_client");
  }

  void TearDown() override {
    node_.reset();
    rclcpp::shutdown();
  }

  rclcpp::Node::SharedPtr node_;
};

TEST_F(ArmControlClientTest, ConstructClient) {
  arm_control::ArmControlClient client(node_);
  SUCCEED();
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
