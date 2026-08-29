#!/usr/bin/env python3
"""Randomized pick success-rate benchmark for the Gazebo metal sorting scene.

Each trial:
1. Samples a random object (roller / hex_nut / short_bolt) and a random
   reachable tabletop pose inside the configured workspace.
2. Teleports the object in Gazebo via the gz service API and injects the
   matching pose into the scene config consumed by vision.config_detect.
3. Runs the full sorting actionlist (detect -> pick -> place) against the
   live bridge.
4. Records grasp/place success from the physics gripper state and the
   actionlist outcome, then resets the arm home.

Results are written as JSONL (one line per trial) plus a summary printed at
the end. Data dirs stay out of Git; results default to logs/benchmarks/.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
  sys.path.insert(0, str(SCRIPT_DIR))

from sensoragent.agent import AgentBundle, build_agent  # noqa: E402
from sensoragent.config import SensorAgentConfig, load_config  # noqa: E402
from sensoragent.schemas import AgentRequest, TraceContext  # noqa: E402

# Object catalogs: base_link resting z (table_z 0.12 + half height) taken from
# configs/robot_sorting_sim.yaml so the config_detect pose matches the physics.
OBJECTS = {
  "滚轮": {
    "model": "sensoragent_part_roller",
    "entities": ["metal_roller_01", "metal_roller_02", "metal_roller_03"],
    "base_z": 0.14,
    "roll": "0 1.570796 0",
    "release_z": 0.22,
  },
  "六角螺母": {
    "model": "sensoragent_part_hex_nut",
    "entities": ["metal_hex_nut_01", "metal_hex_nut_02", "metal_hex_nut_03"],
    "base_z": 0.1325,
    "roll": "0 0 0",
    "release_z": 0.22,
  },
  "短螺栓": {
    "model": "sensoragent_part_short_bolt",
    "entities": ["metal_short_bolt_01", "metal_short_bolt_02", "metal_short_bolt_03"],
    "base_z": 0.1525,
    "roll": "3.141593 0 0",
    "release_z": 0.24,
  },
}
# Workspace box in base_link (from configs/robot_sorting_sim.yaml), shrunk to
# keep clear of the bin rack on the -y side and the robot column near origin.
SAMPLE_X = (-0.50, -0.20)
SAMPLE_Y = (-0.20, 0.30)
HOME_JOINTS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def _http(method: str, endpoint: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
  data = json.dumps(payload or {}).encode()
  req = urllib.request.Request(
    f"http://127.0.0.1:8765{endpoint}",
    data=data if method == "POST" else None,
    headers={"Content-Type": "application/json"},
    method=method,
  )
  with urllib.request.urlopen(req, timeout=timeout) as resp:
    return json.loads(resp.read())


def wait_for_bridge(timeout: float = 180.0) -> None:
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    try:
      if _http("GET", "/health", timeout=3.0).get("success"):
        time.sleep(45)  # controllers + MoveIt spin-up margin
        return
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
      pass
    time.sleep(5)
  raise RuntimeError(f"bridge not ready within {timeout}s")


def _gz_set_pose(entity: str, world_x: float, world_y: float, world_z: float, quat: tuple[float, float, float, float]) -> bool:
  """Teleport an entity in Gazebo via the ign service API (world 'empty')."""

  cmd = [
    "ign", "service", "-s", "/world/empty/set_pose",
    "--reqtype", "ignition.msgs.Pose",
    "--reptype", "ignition.msgs.Boolean",
    "--timeout", "3000",
    "--req", (
      f"name: '{entity}' "
      f"position: {{x: {world_x}, y: {world_y}, z: {world_z}}} "
      f"orientation: {{x: {quat[0]}, y: {quat[1]}, z: {quat[2]}, w: {quat[3]}}}"
    ),
  ]
  proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
  return proc.returncode == 0 and "true" in proc.stdout.lower()


# Resting orientations in world frame (quaternion x,y,z,w) per part type,
# matching how the world file spawns them.
ORIENTATIONS = {
  "滚轮": (0.0, 0.7071, 0.0, 0.7071),       # lying on side (roll 90deg)
  "六角螺母": (0.0, 0.0, 0.0, 1.0),          # flat
  "短螺栓": (0.0, 0.0, 0.0, 1.0),            # lying (head offset handled by model)
}


def teleport_object(entity: str, object_key: str, base_x: float, base_y: float, base_z: float, *, retry: int = 3) -> bool:
  """base_link -> world: robot mounts at world origin, z +0.18, yaw 180deg."""

  world_x, world_y, world_z = -base_x, -base_y, base_z + 0.18
  # Drop slightly above the resting height so physics settles instead of
  # intersecting the table; a few cm is plenty for these part sizes.
  drop_z = world_z + 0.02
  for attempt in range(retry):
    if _gz_set_pose(entity, world_x, world_y, drop_z, ORIENTATIONS[object_key]):
      return True
    time.sleep(1.0 + attempt)
  return False


def reset_arm_home(*, attempts: int = 4) -> bool:
  """Cancel leftovers and drive home, retrying through planner flakes."""

  for attempt in range(attempts):
    try:
      _http("POST", "/stop", {})
    except Exception:  # noqa: BLE001 - best effort cancel
      pass
    time.sleep(3)
    try:
      resp = _http(
        "POST", "/move-joints",
        {"joints": HOME_JOINTS, "speed": 0.3, "wait": True},
        timeout=300.0,
      )
      if resp.get("success"):
        return True
    except Exception:  # noqa: BLE001 - timeout mid-motion; state may still converge
      pass
    time.sleep(5 + 5 * attempt)
  # Last resort: check whether the arm actually reached home despite errors.
  try:
    state = _http("GET", "/state", timeout=10.0)
    joints = state.get("state", {}).get("arm", {}).get("joints") or []
    return all(abs(j) < 0.05 for j in joints)
  except Exception:  # noqa: BLE001
    return False


def build_trial_config(config: SensorAgentConfig, label: str, object_key: str, pose_base: list[float], release_z: float) -> SensorAgentConfig:
  """Return a config whose config_detect catalog has only the trial object."""

  objects = {label: pose_base + [0.0, 0.0, 0.0]}
  scene = replace(
    config.scene,
    objects=objects,
    release_profiles={
      label: {
        "opening": 0.063,
        "place_z": release_z,
        "pick_offset_z": 0.035 if object_key == "短螺栓" else 0.04,
        "grasp_opening": 0.020 if object_key == "短螺栓" else 0.032,
        "grasp_orientation": (
          [0.70710678, 0.70710678, 0.0, 0.0] if object_key == "滚轮" else [0.0, 1.0, 0.0, 0.0]
        ),
      },
    },
  )
  return replace(config, scene=scene)


def run_trial(
  bundle_factory,
  base_config: SensorAgentConfig,
  rng: random.Random,
  trial_index: int,
) -> dict:
  object_key = rng.choice(list(OBJECTS))
  spec = OBJECTS[object_key]
  entity = rng.choice(spec["entities"])
  base_x = round(rng.uniform(*SAMPLE_X), 4)
  base_y = round(rng.uniform(*SAMPLE_Y), 4)
  pose_base = [base_x, base_y, spec["base_z"]]

  record = {
    "trial": trial_index,
    "object": object_key,
    "entity": entity,
    "pose_base": pose_base,
    "teleported": False,
    "grasp_held": None,
    "placed": None,
    "actionlist_success": None,
    "error": None,
  }

  record["teleported"] = teleport_object(entity, object_key, base_x, base_y, spec["base_z"])
  if not record["teleported"]:
    record["error"] = "teleport_failed"
    return record
  time.sleep(1.5)  # let the object settle

  if not reset_arm_home():
    record["error"] = "arm_reset_failed"
    return record

  label = f"{object_key}_trial{trial_index}"
  trial_config = build_trial_config(base_config, label, object_key, pose_base, spec["release_z"])
  bundle: AgentBundle = bundle_factory(trial_config)
  try:
    response = bundle.agent.handle(
      AgentRequest(
        actionlist="industrial.sorting_config_pick_place_actionlist",
        input={"object_query": label, "target": "bin_cell_2"},
      )
    )
  except Exception as exc:  # noqa: BLE001 - record and continue benchmarking
    record["error"] = f"exception: {exc}"
    return record

  record["actionlist_success"] = bool(response.success)
  record["error"] = response.error

  # Read the physics grasp verdict straight from the bridge gripper state.
  try:
    gripper = _http("GET", "/gripper/state", timeout=5.0)
    state = gripper.get("state") or {}
    record["grasp_held"] = bool(state.get("grasped"))
  except Exception:  # noqa: BLE001 - benchmark should not crash on reads
    record["grasp_held"] = None
  result = response.result if isinstance(response.result, dict) else {}
  place = result.get("place_result") if isinstance(result.get("place_result"), dict) else {}
  record["placed"] = bool(place.get("placed"))
  return record


def strip_audio(config: SensorAgentConfig) -> SensorAgentConfig:
  """Remove audio tools/skills so benchmarking works without VAD/ASR assets."""

  return replace(
    config,
    tools=replace(
      config.tools,
      enabled=[n for n in config.tools.enabled if not str(n).startswith("audio.")],
    ),
    skills=replace(
      config.skills,
      enabled=[n for n in config.skills.enabled if not str(n).startswith("audio.")],
    ),
  )


def main() -> int:
  parser = argparse.ArgumentParser(description="Randomized Gazebo sorting success-rate benchmark.")
  parser.add_argument("--trials", type=int, default=12)
  parser.add_argument("--config", type=Path, default=ROOT / "configs" / "robot_sorting_sim.yaml")
  parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
  parser.add_argument("--out-dir", type=Path, default=ROOT / "logs" / "benchmarks")
  args = parser.parse_args()

  wait_for_bridge()
  base_config = strip_audio(load_config(args.config))

  rng = random.Random(args.seed)
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  args.out_dir.mkdir(parents=True, exist_ok=True)
  out_path = args.out_dir / f"sorting_success_{timestamp}.jsonl"

  def bundle_factory(trial_config: SensorAgentConfig) -> AgentBundle:
    log_path = args.out_dir / f"sorting_success_{timestamp}_trial.jsonl"
    return build_agent(trial_config, log_path=log_path)

  def read_trial_grasp_physics(trial_log: Path) -> bool | None:
    """Read the first physics `grasped` flag logged by gripper.get_state.

    The first get_state call in a sorting turn is pick's close-contact check,
    so its flag reflects whether the gripper actually held the object.
    """

    try:
      with trial_log.open(encoding="utf-8") as fh:
        for line in fh:
          try:
            rec = json.loads(line)
          except json.JSONDecodeError:
            continue
          payload = rec.get("payload") or {}
          if rec.get("event") != "tool_call_finished" or not isinstance(payload, dict):
            continue
          if payload.get("tool") != "gripper.get_state":
            continue
          state = (payload.get("output") or {}).get("state") or {}
          if isinstance(state.get("grasped"), bool):
            return state["grasped"]
    except FileNotFoundError:
      return None
    return None

  results: list[dict] = []
  trial_log = args.out_dir / f"sorting_success_{timestamp}_trial.jsonl"
  for trial_index in range(1, args.trials + 1):
    print(f"[trial {trial_index}/{args.trials}] starting...", flush=True)
    # Truncate the per-trial log so physics reads only see this trial.
    trial_log.write_text("", encoding="utf-8")
    record = run_trial(bundle_factory, base_config, rng, trial_index)
    record["grasp_physics"] = read_trial_grasp_physics(trial_log)
    results.append(record)
    with out_path.open("a", encoding="utf-8") as fh:
      fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(
      f"[trial {trial_index}/{args.trials}] object={record['object']} "
      f"grasp={record['grasp_held']} placed={record['placed']} "
      f"ok={record['actionlist_success']} err={str(record['error'])[:80]}",
      flush=True,
    )

  total = len(results)
  teleported = sum(1 for r in results if r["teleported"])
  grasped_physics = sum(1 for r in results if r.get("grasp_physics") is True)
  placed = sum(1 for r in results if r["placed"] is True)
  full_success = sum(1 for r in results if r["actionlist_success"])
  print("\n=== SUMMARY ===")
  print(f"trials: {total} (teleported ok: {teleported})")
  if total:
    print(f"grasp success (physics): {grasped_physics}/{total} = {grasped_physics / total:.0%}")
    print(f"place success: {placed}/{total} = {placed / total:.0%}")
    print(f"actionlist success: {full_success}/{total} = {full_success / total:.0%}")
  print(f"detail: {out_path}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
