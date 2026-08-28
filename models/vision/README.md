# Vision model weights

Keep local detector and segmentation weights in this directory when a fixed
offline path is needed. Git ignores the weight files and retains only this
README and `.gitkeep`. Never commit a weight, framework cache, partial download,
training run, exported engine, or inference output.

## Recommended local layout

Use separate paths for each detector family. Do not replace a YOLO11-seg
checkpoint with a Grounding DINO checkpoint or rename different model types to
the same generic filename.

```text
models/vision/
├── yoloe.pt                    # legacy compatibility baseline
├── yolo11-seg/
│   └── industrial-best.pt
├── grounding-dino/
│   ├── grounding-dino-tiny/
│   └── industrial-open-vocab/
├── sam2/
│   └── sam2_t.pt
├── sam2_t.pt
└── metadata/
    ├── grounding-dino-industrial-open-vocab.example.json
    └── yolo11-seg-industrial.example.json
```

`models/vision/yoloe.pt` remains the YOLOE baseline path for compatibility.
`models/vision/sam2_t.pt` also remains supported because existing configs and
docs already reference it. New local SAM 2 weights may use
`models/vision/sam2/` once the corresponding config is updated.

## Stage 1 - YOLO11-seg fixed industrial branch

The fixed-class branch should use a trained YOLO11 segmentation checkpoint at:

```text
models/vision/yolo11-seg/industrial-best.pt
```

This file is not distributed in Git. A contributor who owns an approved copy
must provide its download location and SHA-256 checksum before acceptance can be
repeated. The class names in the checkpoint must match the project industrial
ontology, for example `roller`, `hex_nut`, and `short_bolt`.

Use the dedicated config when you need to force this branch:

```powershell
python -m sensoragent.services.cli.main vision-detect `
  --config configs\vision_yolo11_seg.example.yaml `
  --tool vision.yolo11_seg_detect `
  --image examples\scene.jpg `
  --query "roller"
```

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

For a local industrial fine-tuned Grounding DINO checkpoint, prefer a named
directory:

```yaml
integrations:
  vision:
    backend: grounding_dino
    grounding_dino_model: models/vision/grounding-dino/industrial-open-vocab
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

## Stage 3 - dual-branch competition routing

The competition-facing Tool is `vision.dual_branch_detect`. Known industrial
classes route to YOLO11-seg first, while unknown or long-tail language
references route to the industrial Grounding DINO + SAM 2 branch.

```powershell
python -m sensoragent.services.cli.main vision-detect `
  --config configs\vision_dual_branch.example.yaml `
  --tool vision.dual_branch_detect `
  --image examples\scene.jpg `
  --query "六角螺母"
```

## Stage 4 - Grounding DINO competition fine-tuning

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

After approval, copy or download the selected `from_pretrained` directory into a
stable local path such as:

```text
models/vision/grounding-dino/industrial-open-vocab/
```

Then update a config to point at that directory. Keep YOLO11-seg checkpoints
under `models/vision/yolo11-seg/` so the fixed industrial branch can be
evaluated separately from open-vocabulary Grounding DINO.

Only the small `class_map.json`, model metadata, download URL, license, training
configuration, and checksum may be considered for Git. Keep `.pt`, `.pth`,
`.onnx`, `.engine`, and training output outside version control. Do not replace
the default runtime model until a same-split comparison passes the agreed
acceptance thresholds.
