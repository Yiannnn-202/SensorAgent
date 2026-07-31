# Vision model weights

Keep local detector and segmentation weights in this directory when a fixed
offline path is needed. Git ignores the weight files and retains only this
README and `.gitkeep`. Never commit a weight, framework cache, partial download,
training run, exported engine, or inference output.

## Stage 1 - YOLOE baseline

The existing Gazebo configuration expects the temporary baseline at:

```text
models/vision/yoloe.pt
```

This file is not distributed in Git. A contributor who owns an approved copy
must provide its download location and SHA-256 checksum before baseline
acceptance can be repeated.

## Stage 2 - Grounding DINO and SAM 2

The Grounding DINO configuration accepts either a Hugging Face model ID or a
local `from_pretrained` directory. SAM 2 accepts a local Ultralytics weight path.
The default references are:

```text
Grounding DINO: IDEA-Research/grounding-dino-tiny
SAM 2:          models/vision/sam2_t.pt
```

Configure the references under `integrations.vision`:

```yaml
integrations:
  vision:
    backend: grounding_dino
    grounding_dino_model: IDEA-Research/grounding-dino-tiny
    sam2_model_path: models/vision/sam2_t.pt
```

Environment overrides:

```text
SENSORAGENT_GROUNDING_DINO_MODEL
SENSORAGENT_SAM2_WEIGHTS
```

The 2026-07-26 local acceptance used SHA-256
`1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3`
for Grounding DINO Tiny model data and
`94375f988270836169320bd901960c67b5770e8bef3867d70102f01a8b5ca501`
for `sam2_t.pt`. These hashes record that specific acceptance only; re-check the
current local file before reproducing it.

## Stage 3 - Grounding DINO competition fine-tuning

The current primary training task fine-tunes Grounding DINO directly from the
pretrained reference above. Use:

```text
scripts/vision_train_grounding_dino.py
configs/vision_train_grounding_dino.example.yaml
```

The JSONL data stores ordered text classes and absolute detection boxes. SAM 2
masks may be retained beside the boxes for review and later segmentation work,
but they are not Grounding DINO loss targets. Fine-tuned model directories are
written under `runs/vision/train/` and must remain outside Git. Publish the
approved download location, source model ID, prompt order, configuration,
dataset hash, and checkpoint SHA-256 only after same-split evaluation.

## Historical YOLO11n-seg experiment support

YOLO11n-seg is outside the current 2026-08-10 delivery path. The repository
retains its historical experiment runner, and an old local comparison can
initialize from:

```text
models/vision/yolo11n-seg.pt
```

The local 2026-07-30 copy is the official COCO 80-class segmentation checkpoint,
not a competition-trained model. Its size is 6,182,636 bytes and its SHA-256 is
`55ed65c56c91713d23e8402371c6c49a6fd84f257f7dce452e8d70e41dcbe152`.
Do not allocate current simulation data or training time to `scripts/vision_train.py`.
Only reopen this path if the team explicitly defines a later fixed-class comparison
and reviewed polygon labels are ready.

Use this local convention after the class map and export format are approved:

```text
models/vision/industrial_student_best.pt
models/vision/industrial_student_best.onnx
models/vision/class_map.json
```

Only the small `class_map.json`, model metadata, download URL, license, training
configuration, and checksum may be considered for Git. Keep `.pt`, `.pth`,
`.onnx`, `.engine`, and training output outside version control. Do not replace
the default runtime model until a same-split comparison passes the agreed
acceptance thresholds.

## SAM3 research candidate

SAM3 is not installed or distributed from this directory. It uses a gated
checkpoint, a separate SAM License, and a different training stack. Keep any
future SAM3 environment and weights outside Git and follow
`docs/guides/vision_sam3_assessment_cn.md` before adding a runtime adapter.
