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
3D pick position + 3D place position
→ robot.plan_top_down_pick
→ robot.pick
→ robot.plan_place
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
2. The arm moves above the pick position.
3. The arm descends and closes the gripper.
4. The arm lifts.
5. The arm moves above the place position.
6. The arm descends and opens the gripper.
7. The arm retreats.

## 4. Coordinate options

Use world coordinates from Gazebo:

```bash
--pick-world-position X Y Z
--place-world-position X Y Z
```

The scripts subtract `--robot-mount-z` from Z to convert world coordinates to
`base_link` coordinates. The default mount height is `0.18 m`.

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

## 6. Common options

```bash
--execute                     # actually move the robot and gripper
--speed 2                     # motion speed, default 2
--pick-offset 0 0 0.02        # offset added to pick point
--place-offset 0 0 0.02       # offset added to place point
--close-opening 0.02          # gripper opening after close command, metres
--json-out logs/tasks/pick_place_test.json
```

## 7. Emergency stop

```bash
curl -X POST http://127.0.0.1:8765/stop \
  -H 'Content-Type: application/json' \
  -d '{}'
```
