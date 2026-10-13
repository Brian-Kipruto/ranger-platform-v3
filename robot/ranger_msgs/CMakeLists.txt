# ─── RANGER V3 START: 13-ranger-msgs ───
# Interface-only package (ADR-0020). Nodes stay plain rclpy scripts in
# ~/ranger/ (ADR-0014); only the message definitions need a colcon build.
cmake_minimum_required(VERSION 3.8)
project(ranger_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Radiation.msg"
  "msg/AirQuality.msg"
  "msg/ImuBaro.msg"
  DEPENDENCIES std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
# ─── RANGER V3 END: 13-ranger-msgs ───
