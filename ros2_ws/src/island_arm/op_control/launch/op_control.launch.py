from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='op_control',
            executable='op_control_node',
            name='op_control_node',
            output='screen',
            parameters=[
                {'port': '/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0'},
                {'baudrate': 115200},
                {'timeout_sec': 8.0},
            ],
        ),
    ])
