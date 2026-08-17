"""Structured command grounding for the industrial sorting scene."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import math
import re
from typing import Mapping


class GroundingStatus(StrEnum):
  READY = "ready"
  NEEDS_CLARIFICATION = "needs_clarification"
  UNSUPPORTED = "unsupported"


class IntentAction(StrEnum):
  PICK = "pick"
  PLACE = "place"
  PICK_PLACE = "pick_place"


@dataclass(frozen=True)
class ObjectClass:
  class_id: str
  display_name: str
  aliases: tuple[str, ...]
  vision_queries: tuple[str, ...]
  instance_ids: tuple[str, ...]
  grasp_opening: float


@dataclass(frozen=True)
class InstanceSelector:
  relation: str
  ordinal: int = 1
  reference_frame: str = "camera"


@dataclass(frozen=True)
class GroundedIntent:
  status: GroundingStatus
  raw_text: str
  action: IntentAction | None = None
  object_class: str | None = None
  selector: InstanceSelector | None = None
  quantity: int | str = 1
  target: str | None = None
  verify: bool = True
  reason: str | None = None
  clarification: str | None = None

  def to_dict(self) -> dict:
    return asdict(self)


@dataclass(frozen=True)
class GroundedInstance:
  instance_id: str
  class_id: str
  display_name: str
  pose_3d: tuple[float, float, float]
  grasp_opening: float
  source: str = "oracle_config"

  def to_dict(self) -> dict:
    return asdict(self)


_RELATIONS = (
  (("离机械臂最近", "最靠近机械臂", "最近", "nearest", "closest"), "nearest", "arm_base"),
  (("离机械臂最远", "最远", "farthest"), "farthest", "arm_base"),
  (("最左边", "左边", "左侧", "leftmost", "left"), "left", "camera"),
  (("最右边", "右边", "右侧", "rightmost", "right"), "right", "camera"),
  (("最前面", "前面", "前侧", "front"), "front", "camera"),
  (("最后面", "后面", "后侧", "back"), "back", "camera"),
  (("最大的", "最大", "largest", "biggest"), "largest", "camera"),
  (("最小的", "最小", "smallest"), "smallest", "camera"),
)
_CN_DIGITS = {
  "一": 1,
  "二": 2,
  "两": 2,
  "三": 3,
  "四": 4,
  "五": 5,
  "六": 6,
  "七": 7,
  "八": 8,
  "九": 9,
}
_ORDINAL_PATTERN = re.compile(r"第?\s*([一二两三四五六七八九1-9])\s*(?:个|号)?")
_TARGET_PATTERN = re.compile(
  r"(?:第?\s*)?([一二两三四五六七八九1-9])\s*(?:号)?(?:格|格子|格位)"
)
_TARGET_EN_PATTERN = re.compile(r"(?:bin_cell_|cell|bin)([1-9])")
_PUNCTUATION = re.compile(r"[\s，。！？,.!?；;：:]+")


class ObjectOntology:
  """Configuration-backed vocabulary shared by language and perception."""

  def __init__(self, classes: Mapping[str, ObjectClass]) -> None:
    if not classes:
      raise ValueError("object ontology must define at least one class")
    self._classes = dict(classes)

  @classmethod
  def from_mapping(cls, value: Mapping[str, object]) -> "ObjectOntology":
    classes: dict[str, ObjectClass] = {}
    for class_id, raw in value.items():
      if not isinstance(raw, Mapping):
        raise ValueError(f"object_ontology.{class_id} must be an object")
      aliases = raw.get("aliases", [])
      queries = raw.get("vision_queries", [])
      instance_ids = raw.get("instance_ids", [])
      if not all(
        isinstance(items, list) and all(isinstance(item, str) and item for item in items)
        for items in (aliases, queries, instance_ids)
      ):
        raise ValueError(
          f"object_ontology.{class_id} aliases, vision_queries, and "
          "instance_ids must be string lists"
        )
      display_name = str(raw.get("display_name", class_id)).strip()
      if not display_name or not aliases or not queries or not instance_ids:
        raise ValueError(f"object_ontology.{class_id} is incomplete")
      classes[class_id] = ObjectClass(
        class_id=class_id,
        display_name=display_name,
        aliases=tuple(aliases),
        vision_queries=tuple(queries),
        instance_ids=tuple(instance_ids),
        grasp_opening=float(raw.get("grasp_opening", 0.032)),
      )
    return cls(classes)

  def get(self, class_id: str) -> ObjectClass:
    try:
      return self._classes[class_id]
    except KeyError as exc:
      raise KeyError(f"unknown object class: {class_id}") from exc

  def classes(self) -> tuple[ObjectClass, ...]:
    return tuple(self._classes.values())

  def match_classes(self, text: str) -> list[ObjectClass]:
    normalized = _normalize(text)
    matches: list[tuple[int, ObjectClass]] = []
    for object_class in self._classes.values():
      matched_lengths = [
        len(_normalize(alias))
        for alias in object_class.aliases
        if _normalize(alias) in normalized
      ]
      if matched_lengths:
        matches.append((max(matched_lengths), object_class))
    if not matches:
      return []
    longest = max(length for length, _ in matches)
    return [object_class for length, object_class in matches if length == longest]


class SortingCommandGrounder:
  """Parse natural language into a bounded industrial sorting intent."""

  def __init__(
    self,
    ontology: ObjectOntology,
    place_targets: Mapping[str, object],
  ) -> None:
    self._ontology = ontology
    self._place_targets = set(place_targets)

  def ground(self, text: str) -> GroundedIntent:
    raw_text = text.strip()
    normalized = _normalize(raw_text)
    if not normalized:
      return self._failure(
        raw_text,
        GroundingStatus.NEEDS_CLARIFICATION,
        "EMPTY_COMMAND",
        "没有听到有效指令，请重新说明要操作的零件和目标格。",
      )

    classes = self._ontology.match_classes(normalized)
    if not classes:
      return self._failure(
        raw_text,
        GroundingStatus.UNSUPPORTED,
        "UNKNOWN_OBJECT_CLASS",
        "没有识别到当前场景支持的零件类别。",
      )
    if len(classes) > 1:
      names = "、".join(item.display_name for item in classes)
      return self._failure(
        raw_text,
        GroundingStatus.NEEDS_CLARIFICATION,
        "AMBIGUOUS_OBJECT_CLASS",
        f"指令同时匹配到 {names}，请只指定一种零件。",
      )
    object_class = classes[0]

    target = self._parse_target(normalized)
    mentions_destination = any(
      token in normalized for token in ("格", "料箱", "放到", "放入", "放进", "put", "place")
    )
    if mentions_destination and target is None:
      return self._failure(
        raw_text,
        GroundingStatus.NEEDS_CLARIFICATION,
        "TARGET_MISSING_OR_INVALID",
        "请说明有效目标格，例如“三号格”。",
        object_class=object_class.class_id,
      )

    action = (
      IntentAction.PICK_PLACE
      if target is not None
      else IntentAction.PICK
    )
    quantity: int | str = (
      "all" if any(token in normalized for token in ("全部", "所有", "都", "all")) else 1
    )
    if quantity == "all":
      # Batch mode: the whole class goes into the bins, one instance per cell,
      # starting from the named target (or the first empty cell). A batch still
      # needs a destination story, so a targetless "pick all" stays ambiguous.
      if target is None:
        return GroundedIntent(
          status=GroundingStatus.NEEDS_CLARIFICATION,
          raw_text=raw_text,
          action=action,
          object_class=object_class.class_id,
          quantity=quantity,
          target=target,
          reason="TARGET_REQUIRED",
          clarification="批量任务请指定起始目标格，例如“把所有滚轮放入一号格”。",
        )
      return GroundedIntent(
        status=GroundingStatus.READY,
        raw_text=raw_text,
        action=action,
        object_class=object_class.class_id,
        quantity=quantity,
        target=target,
        verify=True,
      )

    selector = self._parse_selector(normalized)
    return GroundedIntent(
      status=GroundingStatus.READY,
      raw_text=raw_text,
      action=action,
      object_class=object_class.class_id,
      selector=selector,
      quantity=quantity,
      target=target,
      verify=True,
    )

  def _parse_target(self, text: str) -> str | None:
    match = _TARGET_PATTERN.search(text)
    if match is None:
      match = _TARGET_EN_PATTERN.search(text)
    if match is None:
      return None
    index = _digit(match.group(1))
    target = f"bin_cell_{index}"
    return target if target in self._place_targets else None

  @staticmethod
  def _parse_selector(text: str) -> InstanceSelector | None:
    relation = None
    reference_frame = "camera"
    for aliases, candidate, frame in _RELATIONS:
      if any(_normalize(alias) in text for alias in aliases):
        relation = candidate
        reference_frame = frame
        break
    if relation is None:
      return None
    ordinal = 1
    # Destination ordinals belong to the target slot, not the object selector.
    selector_text = _TARGET_EN_PATTERN.sub("", _TARGET_PATTERN.sub("", text))
    match = _ORDINAL_PATTERN.search(selector_text)
    if match is not None:
      ordinal = _digit(match.group(1))
    return InstanceSelector(
      relation=relation,
      ordinal=ordinal,
      reference_frame=reference_frame,
    )

  @staticmethod
  def _failure(
    text: str,
    status: GroundingStatus,
    reason: str,
    clarification: str,
    *,
    object_class: str | None = None,
  ) -> GroundedIntent:
    return GroundedIntent(
      status=status,
      raw_text=text,
      object_class=object_class,
      reason=reason,
      clarification=clarification,
    )


class OracleInstanceResolver:
  """Resolve a grounded selector against configured Gazebo instance poses."""

  def __init__(
    self,
    ontology: ObjectOntology,
    scene_objects: Mapping[str, object],
  ) -> None:
    self._ontology = ontology
    self._scene_objects = scene_objects

  def candidates(
    self,
    class_id: str,
    *,
    excluded: set[str] | None = None,
  ) -> list[GroundedInstance]:
    object_class = self._ontology.get(class_id)
    excluded = excluded or set()
    candidates: list[GroundedInstance] = []
    for instance_id in object_class.instance_ids:
      if instance_id in excluded:
        continue
      raw_pose = self._scene_objects.get(instance_id)
      if (
        not isinstance(raw_pose, list)
        or len(raw_pose) < 3
        or not all(isinstance(value, (int, float)) for value in raw_pose[:3])
      ):
        raise ValueError(f"scene.objects.{instance_id} must contain XYZ")
      candidates.append(
        GroundedInstance(
          instance_id=instance_id,
          class_id=class_id,
          display_name=object_class.display_name,
          pose_3d=tuple(float(value) for value in raw_pose[:3]),
          grasp_opening=object_class.grasp_opening,
        )
      )
    return candidates

  def resolve(
    self,
    intent: GroundedIntent,
    *,
    excluded: set[str] | None = None,
  ) -> tuple[GroundedInstance | None, str | None]:
    if intent.status != GroundingStatus.READY or intent.object_class is None:
      return None, intent.clarification or intent.reason
    candidates = self.candidates(intent.object_class, excluded=excluded)
    if not candidates:
      return None, "当前场景中没有剩余的该类零件。"
    selector = intent.selector
    if selector is None:
      if len(candidates) == 1:
        return candidates[0], None
      return None, (
        f"检测到 {len(candidates)} 个{candidates[0].display_name}，"
        "请说明左、右、前、后、最近、最远或第几个。"
      )
    if selector.relation in {"largest", "smallest"}:
      return None, "当前同类零件尺寸相同，无法按大小唯一选择。"

    reverse = selector.relation in {"right", "back", "farthest"}
    if selector.relation in {"left", "right"}:
      key = lambda item: item.pose_3d[1]
    elif selector.relation in {"front", "back"}:
      key = lambda item: item.pose_3d[0]
    else:
      key = lambda item: math.hypot(item.pose_3d[0], item.pose_3d[1])
    ordered = sorted(candidates, key=key, reverse=reverse)
    if selector.ordinal > len(ordered):
      return None, (
        f"只检测到 {len(ordered)} 个{ordered[0].display_name}，"
        f"无法选择第 {selector.ordinal} 个。"
      )
    winner = ordered[selector.ordinal - 1]
    if len(ordered) > 1 and abs(key(ordered[0]) - key(ordered[1])) < 1e-6:
      return None, "候选在该空间关系下无法区分，请换一种描述。"
    return winner, None


def _normalize(text: str) -> str:
  return _PUNCTUATION.sub("", text).casefold()


def _digit(value: str) -> int:
  return int(value) if value.isdigit() else _CN_DIGITS[value]
