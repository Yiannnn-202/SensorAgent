cmake_minimum_required(VERSION 3.8)
project(op_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(op_control_interfaces REQUIRED)

# -----------------------------------------------------------------------------
# op_control driver library (serial + protocol + driver; no ROS dependency).
# -----------------------------------------------------------------------------
add_library(op_control_driver STATIC
  src/detail/serial_port.cpp
  src/detail/protocol.cpp
  src/driver.cpp
)

target_include_directories(op_control_driver PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
  $<INSTALL_INTERFACE:include>
)

# -----------------------------------------------------------------------------
# ROS 2 node.
# -----------------------------------------------------------------------------
add_executable(op_control_node
  src/op_control_node.cpp
)

target_include_directories(op_control_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
)

target_link_libraries(op_control_node op_control_driver)
ament_target_dependencies(op_control_node rclcpp op_control_interfaces)

# -----------------------------------------------------------------------------
# ROS 2 blocking commander library.
# -----------------------------------------------------------------------------
add_library(op_commander STATIC
  src/op_commander.cpp
)

target_include_directories(op_commander PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(op_commander op_control_driver)
ament_target_dependencies(op_commander rclcpp op_control_interfaces)

# -----------------------------------------------------------------------------
# Install.
# -----------------------------------------------------------------------------
install(TARGETS op_control_node
  DESTINATION lib/${PROJECT_NAME}
)

install(TARGETS op_control_driver op_commander
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

# -----------------------------------------------------------------------------
# Export targets for downstream packages.
# -----------------------------------------------------------------------------
ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_include_directories(include)
ament_export_dependencies(rclcpp op_control_interfaces)

# -----------------------------------------------------------------------------
# Standalone C++ test client.
# -----------------------------------------------------------------------------
add_executable(op_test_client src/op_test_client.cpp)
target_include_directories(op_test_client PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
target_link_libraries(op_test_client op_commander)
ament_target_dependencies(op_test_client rclcpp op_control_interfaces)

install(TARGETS op_test_client
  DESTINATION lib/${PROJECT_NAME}
)

# -----------------------------------------------------------------------------
# Tests.
# -----------------------------------------------------------------------------
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
