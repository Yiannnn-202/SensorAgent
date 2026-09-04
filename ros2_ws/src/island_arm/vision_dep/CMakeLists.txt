cmake_minimum_required(VERSION 3.8)
project(vision_dep)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# --- Dependencies ---
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

# --- librealsense2 ---
find_package(realsense2 REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(TURBOJPEG REQUIRED libturbojpeg)

# =========================================================================
# Depth camera node (RealSense D435)
# =========================================================================
add_executable(dep_cam src/dep_cam.cpp)
target_link_libraries(dep_cam
  realsense2::realsense2
  ${TURBOJPEG_LIBRARIES}
)
target_include_directories(dep_cam PRIVATE ${TURBOJPEG_INCLUDE_DIRS})
ament_target_dependencies(dep_cam
  rclcpp
  sensor_msgs
)

# =========================================================================
# Install
# =========================================================================
install(TARGETS
  dep_cam
  DESTINATION lib/${PROJECT_NAME}
)

ament_python_install_package(${PROJECT_NAME})

install(PROGRAMS
  scripts/stream
  scripts/facerec
  scripts/dep_cam_jpeg_snap
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
