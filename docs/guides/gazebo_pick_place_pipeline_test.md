# Gazebo Pick and Place Pipeline Test Scripts

This guide covers:

```text
scripts/linux/test_gazebo_place_pipeline.py
scripts/linux/test_gazebo_pick_place_pipeline.py
```

They test these SensorAgent paths:

```text
3D place position
→ robot.plan_place
→ robot.place
→ HTTP robot bridge
→ MoveIt / ros2_control / Gazebo
```

and:

```text
3D pick position + 3D place area center
→ robot.plan_top_down_pick
→ robot.pick
→ generate candidate place poses in the area
→ robot.plan_place for candidates
→ robot.place
→ HTTP robot bridge
→ MoveIt / ros2_control / Gazebo
```

## 1. Start Gazebo, MoveIt, and the robot bridge

In the first terminal:

```bash
cd ~/SensorAgent
bash scripts/linux/run_rm65_b_sim.sh
```

In another terminal:

```bash
cd ~/SensorAgent
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/ready
```

For execution, `/ready` should show these interfaces as `true`:

```text
move_action
execute_trajectory
cartesian_path
gripper_cmd
```

## 2. Plan a place only

Plan only; nothing moves:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_place_pipeline.py \
  --world-position 0.50 0.10 0.32
```

Execute the place sequence:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_place_pipeline.py \
  --world-position 0.50 0.10 0.32 \
  --execute
```

Expected Gazebo behavior:

1. The arm moves above the target place position.
2. The arm descends to the place pose.
3. The gripper opens.
4. The arm retreats upward.

## 3. One-command pick then place

Plan both pick and place; nothing moves:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_place_pipeline.py \
  --pick-world-position 0.24 0.23 0.322 \
  --place-world-position 0.50 0.10 0.32
```

Execute the full pipeline:

```bash
PYTHONPATH=src .venv312/bin/python scripts/linux/test_gazebo_pick_place_pipeline.py \
  --pick-world-position 0.24 0.23 0.322 \
  --place-world-position 0.50 0.10 0.32 \
  --execute
```

Expected Gazebo behavior:

1. The gripper opens.
2. The arm moves to a high safe pose above the pick position.
3. The arm descends vertically and closes the gripper.
4. The arm lifts.
5. The script chooses a reachable place candidate inside the place area.
6. The arm moves above the selected place position.
7. The arm descends and opens the gripper.
8. The arm retreats.

## 4. Coordinate options

Use world coordinates from Gazebo. In `test_gazebo_pick_place_pipeline.py`,
`--place-world-position` is an area center by default:

```bash
--pick-world-position X Y Z
--place-world-position X Y Z
```

The scripts apply the 180-degree robot mount yaw and subtract `--robot-mount-z`
from Z to convert world coordinates to `base_link` coordinates. The default
mount height is `0.18 m`.

Use `base_link` coordinates directly:

```bash
--pick-position X Y Z
--place-position X Y Z
```

## 5. Useful defaults

The default industrial world includes approximate object positions listed in
the pick pipeline guide. A safe starting pair is:

```bash
--pick-world-position 0.24 0.23 0.322
--place-world-position 0.50 0.10 0.32
```

By default, the pick-place script places near the pick area because that is more
reachable for the current RM65-B tabletop demo:

```bash
--place-mode near_pick
--near-pick-place-offset 0.10 -0.12 0
--place-area-size 0.24 0.18
--place-area-samples 3 3
```

With `near_pick`, `--place-world-position` is still accepted but is ignored for
candidate generation; the area center is computed from the pick point. Use
`--place-mode area` when you want `--place-world-position` to be the area center.
The script sorts candidates by a simple reachability heuristic and tries easier
positions closer to the robot first. This is intended for missions where the
object can be placed anywhere in an acceptable area, not at one exact point.

The workbench top is around `world z = 0.30 m`. The robot bridge commands the
virtual `robotiq_85_tcp` frame at the gripper fingertips, not the arm flange.
This lets MoveIt plan around the gripper position instead of letting the fingers
hang below a `Link6` target and touch the table. The scripts use these safe
defaults:

```bash
--pick-offset 0 0 0.02
--place-offset 0 0 0.08
--place-clearance 0.15
```

These values keep the gripper TCP and held object above the table while moving
to the place approach pose. If placement succeeds, lower
`--place-offset` gradually.

## 6. Common options

```bash
--execute                     # actually move the robot and gripper
--speed 1.2                   # motion speed, default 1.2
--pick-descent-speed 1.2      # vertical descent from pick approach to grasp
--pick-offset 0 0 0.02        # visual object XYZ to gripper TCP grasp pose
--approach-distance 0.10      # vertical approach distance above pick grasp
--pregrasp-distance 0.04      # vertical pregrasp distance above pick grasp
--place-offset 0 0 0.08       # place target to gripper TCP place pose
--place-clearance 0.15        # approach/retreat clearance, default 0.15
--pre-place-joints 0.2 0 0 0 0 0  # optional staging before place
--place-mode near_pick        # default: place near the grasp area
--near-pick-place-offset 0.10 -0.12 0
--place-mode area             # use requested place point as area center
--place-mode exact            # require the requested place point first
--place-area-size 0.24 0.18   # area dimensions in metres
--place-area-samples 3 3      # candidate grid resolution
--no-place-fallbacks          # disable nearby fallback place positions
--close-opening 0.032         # gripper opening after close command, metres
--json-out logs/tasks/pick_place_test.json
```

The pre-place joint staging move is disabled by default. Enable it only when you
want to deliberately move through a known joint-space staging pose before
placing.

If the requested place approach is still rejected by MoveIt, the script tries
nearby fallback positions closer to the robot base. The default fallback offsets
from the requested place point are:

```text
-0.08  0.00  0.00
-0.14  0.00  0.00
-0.08 -0.08  0.00
-0.14 -0.08  0.00
```

These are intended for debugging reachability. Use `--no-place-fallbacks` if the
object must only be released at the exact requested place position.

## 7. Emergency stop

```bash
curl -X POST http://127.0.0.1:8765/stop \
  -H 'Content-Type: application/json' \
  -d '{}'
```
