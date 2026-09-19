# Vision Model Training and Evaluation Guide

This guide covers the offline vision pipeline: dataset validation, evaluation
runs, COCO export conversion, and Grounding DINO fine-tuning. The
competition-facing detection path is `vision.dual_branch_detect`; see the
[industrial agent reproduction guide](competition-agent.md) for how the agent
uses it at runtime.

Dataset images, model weights, caches, and `runs/` outputs stay local and out
of Git. The repository keeps only code, contracts, configuration templates,
and reproducible scripts.

## Dual-branch routing recap

`vision.dual_branch_detect` routes common industrial classes such as bolts,
nuts, rollers, gears, flanges, and wrenches to the fixed-class YOLO11-seg
branch, then falls back to the GroundingDINO + SAM2 branch when needed. Queries
outside the fixed industrial ontology start from GroundingDINO to preserve
open-vocabulary behavior. The fixed industrial-class branch uses YOLO11-seg
checkpoints through `vision.yolo11_seg_detect`; the competition-facing router
is `vision.dual_branch_detect`.

## Validate a dataset manifest

Validate a portable dataset manifest before running a long evaluation:

```powershell
python scripts\vision_eval.py validate `
  --manifest configs\vision_dataset.example.jsonl `
  --allow-missing-files
```

## Run an evaluation

Run a labeled local dataset with one persistent model instance:

```powershell
python scripts\vision_eval.py run `
  --manifest data\vision\competition_test.jsonl `
  --config configs\vision_dual_branch.example.yaml `
  --tool vision.dual_branch_detect `
  --output-dir runs\vision\competition_test `
  --device 0 `
  --require-masks `
  --save-overlays
```

The runner saves per-sample JSONL, aggregate metrics, Tool logs, and optional
overlays.

## Convert reviewed COCO exports

Reviewed COCO segmentation exports can be converted without adding a runtime
dependency on `pycocotools`:

```powershell
python scripts\vision_coco_segmentation_to_eval.py `
  --source-root data\vision\raw_coco `
  --output-root data\vision\competition_eval `
  --sample-prefix industrial_part `
  --query "industrial part" `
  --category-name "industrial-part" `
  --dataset-name "SensorAgent competition dataset" `
  --source-license "internal-reviewed"
```

## Fine-tune Grounding DINO

The current first training target is Grounding DINO itself. Its JSONL manifest
keeps text class names, absolute `bbox_xyxy` targets, provenance, and
scene-level splits. Validate the complete dataset before allocating GPU time:

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino.example.yaml `
  --manifest data\vision\competition_train.jsonl `
  --dry-run
```

After the prompt order, scene-level splits, and detection boxes are reviewed,
start direct full-parameter fine-tuning with:

```powershell
python scripts\vision_train_grounding_dino.py `
  --config configs\vision_train_grounding_dino.example.yaml `
  --manifest data\vision\competition_train.jsonl `
  --device cuda:0
```

`configs/vision_train_grounding_dino.example.yaml` records the proposed prompt
order and reproducible training parameters. `class_labels` are indexes into
that exact text list; they are not an independent YOLO class map. SAM 2 masks
remain useful annotations, but Grounding DINO is optimized on text-grounded
boxes.

The templates are not checked-in training data. Checkpoints, datasets, caches,
and run outputs stay outside Git.
