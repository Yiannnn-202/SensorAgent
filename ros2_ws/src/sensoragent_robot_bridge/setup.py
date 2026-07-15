from setuptools import find_packages, setup


package_name = "sensoragent_robot_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", ["config/robot_bridge.yaml"]),
        (f"share/{package_name}/launch", ["launch/robot_bridge.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="SensorAgent maintainers",
    maintainer_email="noreply@example.com",
    description="HTTP-to-ROS 2 bridge for SensorAgent simulation control.",
    license="Proprietary",
    entry_points={
        "console_scripts": [
            "robot_bridge = sensoragent_robot_bridge.bridge_node:main",
        ],
    },
)
