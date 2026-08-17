from setuptools import find_packages, setup
from glob import glob


package_name = "sensoragent_hardware_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", ["config/hardware_bridge.yaml"]),
        (f"share/{package_name}/config", ["config/hardware_bridge_approach.example.yaml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="SensorAgent maintainers",
    maintainer_email="noreply@example.com",
    description="Safety-gated HTTP bridge from SensorAgent to physical ROS 2 hardware.",
    license="Proprietary",
    entry_points={
        "console_scripts": [
            "hardware_bridge = sensoragent_hardware_bridge.bridge_node:main",
        ],
    },
)
