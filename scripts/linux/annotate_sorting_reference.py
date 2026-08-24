#!/usr/bin/env python3
"""Create a labeled reference image for the initial sorting scene."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "vision" / "sorting_v0" / "roboflow_images" / "sorting_scene_001.png"
OUTPUT = ROOT / "data" / "vision" / "sorting_v0" / "sorting_scene_reference_labeled.png"
LABELS = [
  ("short bolt", (217, 141), (142, 123)),
  ("flange bushing", (267, 141), (238, 102)),
  ("hex nut", (298, 141), (316, 122)),
  ("block", (248, 181), (232, 200)),
  ("roller", (322, 181), (337, 201)),
  ("hollow sleeve", (217, 211), (136, 224)),
  ("stepped shaft", (272, 211), (269, 226)),
]


def main() -> int:
  image = Image.open(SOURCE).convert("RGB")
  draw = ImageDraw.Draw(image)
  font = ImageFont.load_default()
  for label, point, text_origin in LABELS:
    box = draw.textbbox(text_origin, label, font=font)
    padded = (box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2)
    draw.line((point, text_origin), fill="red", width=1)
    draw.ellipse((point[0] - 2, point[1] - 2, point[0] + 2, point[1] + 2), fill="red")
    draw.rectangle(padded, fill="white", outline="red")
    draw.text(text_origin, label, fill="red", font=font)
  image.save(OUTPUT)
  print(OUTPUT)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
