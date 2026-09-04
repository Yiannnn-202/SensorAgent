cmake_minimum_required(VERSION 3.8)
project(vision_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/FaceRegister.srv"
  "srv/FaceRecognize.srv"
  "srv/DepCamJpegSnap.srv"
  "srv/ObjectDetect.srv"
  "msg/FaceResult.msg"
  "msg/FaceResults.msg"
)

install(
  FILES resource/${PROJECT_NAME}
  DESTINATION share/ament_index/resource_index/packages
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
