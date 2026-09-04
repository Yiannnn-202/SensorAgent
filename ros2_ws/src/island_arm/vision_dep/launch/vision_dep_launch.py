#!/usr/bin/env python3

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import FrontendLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
  """Launch depth camera (dep_cam), facerec, stream node, and rosbridge (port 20011)."""

  rosbridge_dir = get_package_share_directory('rosbridge_server')

  return LaunchDescription([
    Node(
      package='vision_dep',
      executable='dep_cam',
      name='dep_cam',
      output='log',
      parameters=[{
        'raw_topic': '/vision/dep/raw/compressed',
        'raw_image_topic': '/vision/raw',
        'depth_topic': '/vision/dep/depth',
        'cloud_topic': '/vision/dep/cloud',
        'grasp_cloud_topic': '/vision/cloud',
        'frame_id': 'camera_link',
        'queue_size': 10,
        'publish_hz': 30.0,
        'color_width': 1920,
        'color_height': 1080,
        'depth_width': 1280,
        'depth_height': 720,
        'fps': 30,
        'jpeg_quality': 85,
        'camera_start_retries': 6,
        'camera_retry_delay_sec': 0.75,
      }],
    ),
    Node(
      package='vision_dep',
      executable='facerec',
      name='facerec',
      output='log',
      parameters=[{
        'source_topic': '/vision/dep/raw/compressed',
        'arcface_host': '127.0.0.1',
        'arcface_port': 20004,
      }],
    ),
    Node(
      package='vision_dep',
      executable='dep_cam_jpeg_snap',
      name='dep_cam_jpeg_snap',
      output='log',
      parameters=[{
        'source_topic': '/vision/dep/raw/compressed',
        'service_name': '/vision/dep/jpeg_snap',
      }],
    ),
    Node(
      package='vision_dep',
      executable='stream',
      name='stream',
      output='log',
      parameters=[{
        'ws_url': 'ws://127.0.0.1:20012/ws/perception',
        'push_interval_sec': 1.0,
        'pose_timeout_sec': 5.0,
      }],
    ),
    IncludeLaunchDescription(
      FrontendLaunchDescriptionSource(
        os.path.join(rosbridge_dir, 'launch', 'rosbridge_websocket_launch.xml'),
      ),
      launch_arguments={
        'port': '20011',
        'default_call_service_timeout': '5.0',
        'call_services_in_new_thread': 'True',
        'send_action_goals_in_new_thread': 'True',
      }.items(),
    ),
  ])
