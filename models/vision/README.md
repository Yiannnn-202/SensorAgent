# Vision model weights

Keep local detector and segmentation weights in this directory when a fixed
offline path is needed. Git ignores the weight files and retains only this
README and `.gitkeep`.

The existing Gazebo configuration expects:

```text
models/vision/yoloe.pt
```

The Grounding DINO configuration accepts either a Hugging Face model ID or a
local `from_pretrained` directory. SAM 2 accepts a local Ultralytics weight
path; the default `models/vision/sam2_t.pt` file may be downloaded by
Ultralytics at runtime.

Configure the references under `integrations.vision`:

```yaml
integrations:
  vision:
    backend: grounding_dino
    grounding_dino_model: IDEA-Research/grounding-dino-tiny
    sam2_model_path: models/vision/sam2_t.pt
```

Never commit model weights, partial downloads, framework caches, or inference
outputs.
