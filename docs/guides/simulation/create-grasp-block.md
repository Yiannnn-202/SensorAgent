# Create a Grasping Block in Gazebo

Create an SDF block with collision geometry, mass, and friction:

```bash
cat >/tmp/grasp_block.sdf <<'EOF'
<?xml version="1.0"?>
<sdf version="1.8">
  <model name="grasp_block">
    <pose>0 0 0 0 0 0</pose>

    <link name="block">
      <inertial>
        <mass>0.2</mass>
        <inertia>
          <ixx>0.0001333</ixx>
          <iyy>0.0001333</iyy>
          <izz>0.0000533</izz>
        </inertia>
      </inertial>

      <collision name="collision">
        <geometry>
          <box>
            <size>0.04 0.04 0.08</size>
          </box>
        </geometry>
        <surface>
          <friction>
            <ode>
              <mu>2.0</mu>
              <mu2>2.0</mu2>
            </ode>
          </friction>
        </surface>
      </collision>

      <visual name="visual">
        <geometry>
          <box>
            <size>0.04 0.04 0.08</size>
          </box>
        </geometry>
        <material>
          <ambient>0.8 0.1 0.1 1</ambient>
          <diffuse>0.8 0.1 0.1 1</diffuse>
        </material>
      </visual>
    </link>
  </model>
</sdf>
EOF
```

Spawn the block:

```bash
ros2 run ros_gz_sim create \
  -world empty \
  -file /tmp/grasp_block.sdf \
  -name grasp_block \
  -x 0.34 \
  -y 0.20 \
  -z 0.34
```

The pose format is:

```text
x y z roll pitch yaw
```

Change the `-x`, `-y`, and `-z` command values to choose the spawn position.

The default industrial workbench surface is at `z=0.30 m`. The block is
8 cm high, so `z=0.34 m` places its bottom on the workbench.

When using `world_file:=empty_pgs.sdf`, use `z=0.04 m` instead to place the
same block on the ground plane.
