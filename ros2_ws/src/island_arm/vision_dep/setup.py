from setuptools import find_packages, setup

package_name = 'vision_dep'

setup(
  name=package_name,
  version='0.0.0',
  packages=find_packages(exclude=['test']),
  data_files=[
    ('share/ament_index/resource_index/packages',
      ['resource/' + package_name]),
  ],
  install_requires=['setuptools', 'httpx', 'websockets'],
  zip_safe=False,
  maintainer='nvidia',
  maintainer_email='ashexlv278@gmail.com',
  description='Depth camera (dep_cam), facerec, and object_targets stream',
  license='TODO: License declaration',
)
