# RealMan RM65-B upstream source

The RM65-B ROS 2 simulation files are imported locally from:

- Repository: <https://github.com/RealManRobot/ros2_rm_robot>
- Branch: `humble`
- Commit: `c941b565e4f9174afa36561f143ef5fbbb744750`
- Upstream version: `1.7.0`
- Target environment: Ubuntu 22.04 and ROS 2 Humble

The project identifier `rm65_b` maps to the upstream standard RM65 model named
`rm_65`. The `rm_65_6f` and `rm_65_6fb` variants are not imported.

Run the following command on Ubuntu:

```bash
bash scripts/linux/fetch_rm65_b_upstream.sh
```

It populates:

- `ros2_ws/src/rm_description`
- `ros2_ws/src/rm_gazebo`
- `ros2_ws/src/rm_65_config`

For build and launch instructions, see
[`docs/robotics/rm65_b_gazebo_quickstart_cn.md`](../docs/robotics/rm65_b_gazebo_quickstart_cn.md).

Only the standard RM65 description, meshes, Gazebo integration, and MoveIt 2
simulation configuration are selected. Drivers, examples, force-sensor
variants, documentation assets, and other robot models are excluded.

## License note

At the pinned commit, the upstream repository does not declare a top-level
GitHub license and `rm_description/package.xml` contains `TODO: License
declaration`. The imported files are therefore kept as ignored local
dependencies rather than redistributed by this repository. Confirm
redistribution permission with RealMan before committing any imported model or
source file.
