cmake_minimum_required(VERSION 3.8)
project(arm_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(rm_ros_interfaces REQUIRED)
find_package(arm_control_interfaces REQUIRED)

add_executable(arm_control_server
  src/main.cpp
  src/arm_control_server.cpp
  src/arm_control_client.cpp
)

target_include_directories(arm_control_server PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(arm_control_server
  rclcpp
  rclcpp_action
  std_msgs
  geometry_msgs
  sensor_msgs
  rm_ros_interfaces
  arm_control_interfaces
)

install(TARGETS arm_control_server
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_arm_control_client
    tests/test_arm_control_client.cpp
    src/arm_control_client.cpp
  )
  target_include_directories(test_arm_control_client PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  ament_target_dependencies(test_arm_control_client
    rclcpp
    geometry_msgs
    arm_control_interfaces
  )
endif()

ament_package()
