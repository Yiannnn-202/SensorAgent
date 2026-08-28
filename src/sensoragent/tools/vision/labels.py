"""Industrial object labels and query normalization for vision routing."""

from __future__ import annotations


DEFAULT_INDUSTRIAL_LABELS = (
  "screwdriver",
  "screw",
  "wrench",
  "hex_nut",
  "nut",
  "short_bolt",
  "bolt",
  "stepped_shaft",
  "roller",
  "gear",
  "flange",
  "cylinder",
  "washer",
  "bearing",
)

INDUSTRIAL_LABEL_ALIASES = {
  "螺丝刀": "screwdriver",
  "螺丝": "screw",
  "扳手": "wrench",
  "六角螺母": "hex_nut",
  "螺母": "nut",
  "短螺栓": "short_bolt",
  "螺栓": "bolt",
  "阶梯轴": "stepped_shaft",
  "滚柱": "roller",
  "滚筒": "roller",
  "滚轮": "roller",
  "齿轮": "gear",
  "法兰": "flange",
  "圆柱": "cylinder",
  "垫圈": "washer",
  "轴承": "bearing",
}


def normalize_label(value: str) -> str:
  """Normalize a model label or query fragment to a comparable token."""

  return value.strip().casefold().replace("-", "_").replace(" ", "_")


def query_mentions_industrial_label(
  query: str,
  labels: tuple[str, ...] = DEFAULT_INDUSTRIAL_LABELS,
) -> bool:
  """Return True when a natural-language query names a known industrial class."""

  normalized_query = normalize_label(query)
  normalized_labels = {normalize_label(label) for label in labels}
  if any(label in normalized_query for label in normalized_labels):
    return True
  for alias, canonical in INDUSTRIAL_LABEL_ALIASES.items():
    if alias in query and normalize_label(canonical) in normalized_labels:
      return True
  return False
