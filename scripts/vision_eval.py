"""Validate or evaluate a SensorAgent vision JSONL dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPOSITORY_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
  sys.path.insert(0, str(SRC_ROOT))

from sensoragent.agent.bootstrap import build_agent_from_env  # noqa: E402
from sensoragent.evaluation.vision import (  # noqa: E402
  AcceptanceThresholds,
  evaluate_manifest,
  validate_manifest,
)
from sensoragent.schemas import TraceContext  # noqa: E402


class SensorAgentVisionRunner:
  """Reuse one configured ToolRuntime across a complete evaluation run."""

  def __init__(self, config: Path, log_path: Path, tool_name: str) -> None:
    self._bundle = build_agent_from_env(config, log_path=log_path)
    self.tool_name = tool_name

  def __call__(self, input_data: dict[str, object]):
    return self._bundle.tool_runtime.invoke(
      self.tool_name,
      input_data,
      trace=TraceContext(),
    )


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Validate a vision dataset or run repeatable model evaluation."
  )
  subparsers = parser.add_subparsers(dest="command", required=True)
  validate = subparsers.add_parser("validate", help="Validate a JSONL manifest.")
  validate.add_argument("--manifest", type=Path, required=True)
  validate.add_argument(
    "--allow-missing-files",
    action="store_true",
    help="Check the schema only; useful for the example manifest.",
  )

  run = subparsers.add_parser("run", help="Run inference and save evaluation JSON.")
  run.add_argument("--manifest", type=Path, required=True)
  run.add_argument(
    "--config", type=Path, default=Path("configs/vision_grounding_dino.yaml")
  )
  run.add_argument(
    "--tool",
    choices=("vision.open_vocab_detect", "vision.grounded_sam2"),
    default="vision.open_vocab_detect",
    help="Vision Tool to evaluate. vision.grounded_sam2 always requires masks.",
  )
  run.add_argument("--output-dir", type=Path, default=Path("runs/vision/eval"))
  run.add_argument("--device", default=None)
  run.add_argument("--no-refine", action="store_true")
  run.add_argument("--require-masks", action="store_true")
  run.add_argument("--save-overlays", action="store_true")
  run.add_argument("--box-threshold", type=float, default=None)
  run.add_argument("--text-threshold", type=float, default=None)
  run.add_argument(
    "--candidate-policy",
    choices=("baseline", "scene_aware"),
    default=None,
    help="Optional candidate policy override for tabletop scene evaluation.",
  )
  run.add_argument(
    "--scene-profile",
    type=Path,
    default=None,
    help="YAML or JSON scene-profile file used with --candidate-policy scene_aware.",
  )
  run.add_argument("--warmup-runs", type=int, default=1)
  run.add_argument("--min-precision", type=float, default=None)
  run.add_argument("--min-recall", type=float, default=None)
  run.add_argument("--min-box-iou", type=float, default=None)
  run.add_argument("--min-mask-iou", type=float, default=None)
  run.add_argument("--min-map50-95", type=float, default=None)
  run.add_argument("--max-center-error-px", type=float, default=None)
  run.add_argument("--max-warm-p95-ms", type=float, default=None)
  run.add_argument("--max-scene-rejection-rate", type=float, default=None)
  run.add_argument("--max-ambiguity-rate", type=float, default=None)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  if args.command == "validate":
    validation = validate_manifest(
      args.manifest,
      check_files=not args.allow_missing_files,
    )
    print(json.dumps(validation.to_dict(), ensure_ascii=False, indent=2))
    return 0 if validation.valid else 2

  if args.warmup_runs < 0:
    raise SystemExit("--warmup-runs must be >= 0")
  args.output_dir.mkdir(parents=True, exist_ok=True)
  runner = SensorAgentVisionRunner(
    args.config,
    args.output_dir / "tool_calls.jsonl",
    args.tool,
  )
  thresholds = AcceptanceThresholds(
    min_precision=args.min_precision,
    min_recall=args.min_recall,
    min_box_iou=args.min_box_iou,
    min_mask_iou=args.min_mask_iou,
    min_map50_95=args.min_map50_95,
    max_center_error_px=args.max_center_error_px,
    max_warm_p95_ms=args.max_warm_p95_ms,
    max_scene_rejection_rate=args.max_scene_rejection_rate,
    max_ambiguity_rate=args.max_ambiguity_rate,
  )
  scene_profile = None
  if args.scene_profile is not None:
    try:
      raw_profile = args.scene_profile.read_text(encoding="utf-8")
      try:
        scene_profile = json.loads(raw_profile)
      except json.JSONDecodeError:
        import yaml

        scene_profile = yaml.safe_load(raw_profile)
      if isinstance(scene_profile, dict) and "scene_profile" not in scene_profile:
        nested = (
          scene_profile.get("integrations", {})
          .get("vision", {})
          if isinstance(scene_profile.get("integrations"), dict)
          else {}
        )
        if isinstance(nested, dict) and isinstance(nested.get("scene_profile"), dict):
          scene_profile = nested["scene_profile"]
      if not isinstance(scene_profile, dict):
        raise ValueError("scene profile must contain a mapping/object")
    except (OSError, ValueError, ImportError) as exc:
      print(f"invalid --scene-profile: {exc}", file=sys.stderr)
      return 2
  try:
    evaluation = evaluate_manifest(
      args.manifest,
      runner=runner,
      output_dir=args.output_dir,
      device=args.device,
      refine_masks=not args.no_refine,
      require_masks=args.require_masks,
      box_threshold=args.box_threshold,
      text_threshold=args.text_threshold,
      save_overlays=args.save_overlays,
      warmup_runs=args.warmup_runs,
      thresholds=thresholds,
      tool_name=args.tool,
      candidate_policy=args.candidate_policy,
      scene_profile=scene_profile,
    )
  except ValueError as exc:
    print(str(exc), file=sys.stderr)
    return 2
  print(json.dumps(evaluation.summary, ensure_ascii=False, indent=2))
  return 0 if evaluation.passed else 1


if __name__ == "__main__":
  raise SystemExit(main())
