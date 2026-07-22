# Gazebo Pick Pipeline Test Script

This guide shows how to use:

```text
scripts/linux/test_gazebo_pick_pipeline.py
```

The script tests the SensorAgent planning and grasping path:

```text
3D position
→ robot.plan_top_down_pick
→ robot.pick
→ HTTP robot bridge
→ MoveIt / ros2_control / Gazebo
```

## 1. Start Gazebo, MoveIt, and the robot bridge

In the first terminal:

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

Wait until Gazebo shows the RM65-B arm and the launch output has settled.

## 2. Check bridge readiness

In a second terminal:

```bash
cd ~/SensorAgent
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

For a full pick, `/ready` should show these interfaces as `true`:

```text
move_action
execute_trajectory
cartesian_path
gripper_cmd
```

For arm-only motion, `move_action: true` is enough.

## 3. Test arm movement only

Run:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_pipeline.py \
  --diagnose-only
```

Expected Gazebo behavior:

- joint 1 rotates slightly;
- no pick or gripper sequence runs.

Expected terminal result:

```text
=== arm diagnostic joint check ===
...
"within_tolerance": true
```

If this passes, the arm controller and MoveIt path are working.

## 4. Test planning only

Run:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_pipeline.py \
  --world-position 0.24 0.23 0.322
```

Expected Gazebo behavior:

- nothing moves.

Expected terminal output:

- `planning input`;
- `top-down pick plan`;
- planned `approach`, `pregrasp`, `grasp`, and `lift` poses.

Use this mode first to confirm the target point and generated waypoints look
safe.

## 5. Run the full planning and grasping pipeline

Run:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_pipeline.py \
  --world-position 0.24 0.23 0.322 \
  --execute
```

Expected Gazebo behavior:

1. The gripper opens.
2. The arm moves to a high safe pose above the target.
3. The arm descends vertically through approach and pregrasp poses.
4. The gripper closes.
5. The arm lifts.

Expected terminal result:

```text
=== pick execution ===
...
"success": true
```

## Coordinate options

Use `--world-position` when the XYZ comes from Gazebo/world coordinates:

```bash
--world-position X Y Z
```

The script subtracts the default robot mount height, `0.18 m`, from world Z to
convert into `base_link`.

Use `--position` when your detector already returns `base_link` coordinates:

```bash
--position X Y Z
```

Do not pass both options in the same command.

## Useful default object positions

The default industrial world includes these approximate Gazebo/world positions:

| Object | Command argument |
| --- | --- |
| Roller | `--world-position 0.24 0.23 0.322` |
| Stepped shaft | `--world-position 0.38 0.23 0.326` |
| Flange | `--world-position 0.51 0.22 0.317` |
| Hex nut | `--world-position 0.63 0.20 0.313` |
| Short bolt | `--world-position 0.28 0.08 0.327` |
| Gear | `--world-position 0.43 0.08 0.310` |

## Common options

```bash
--execute                  # actually move the robot and gripper
--diagnose-only            # only test arm motion
--arm-diagnostic           # run arm diagnostic before the pick
--speed 2                  # motion speed; default is 2
--pick-descent-speed 1.5   # vertical descent from approach to grasp
--position-offset 0 0 0.03 # visual object XYZ to gripper TCP grasp pose
--approach-distance 0.10   # vertical approach distance above grasp
--pregrasp-distance 0.04   # vertical pregrasp distance above grasp
--close-opening 0.02       # gripper opening after close command, in metres
--json-out logs/tasks/gazebo_pick_test.json
```

The robot bridge commands the virtual `robotiq_85_tcp` frame at the gripper
fingertips, not the arm flange. This lets MoveIt plan with the gripper TCP
instead of letting the fingers hang below a `Link6` target and touch the table.

Example with diagnostic and JSON output:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_pipeline.py \
  --world-position 0.24 0.23 0.322 \
  --arm-diagnostic \
  --execute \
  --json-out logs/tasks/gazebo_pick_test.json
```

## Troubleshooting

### The arm does not move

Run:

```bash
ros2 control list_controllers
```

At minimum, these should be active:

```text
joint_state_broadcaster active
rm_group_controller active
```

Then run:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_pipeline.py \
  --diagnose-only
```

If `--diagnose-only` fails, the issue is below the pick pipeline: controller,
MoveIt, Gazebo, or bridge readiness.

### The gripper does not move

Check:

```bash
curl http://127.0.0.1:8765/ready
ros2 action list | grep gripper
ros2 control list_controllers
```

For full pick execution, `/ready` needs:

```text
gripper_cmd: true
```

and `ros2 control list_controllers` should show:

```text
robotiq_gripper_effort_controller active
```

### Plan-only runs but nothing moves

That is expected. Without `--execute`, the script only prints the plan.

### Emergency stop

Use:

```bash
curl -X POST http://127.0.0.1:8765/stop \
  -H 'Content-Type: application/json' \
  -d '{}'
```
