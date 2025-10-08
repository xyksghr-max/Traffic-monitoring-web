"""Stateful helper to manage LLM risk alerts and countdown logic."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple, Any


def _normalize_risk_types(raw: Any) -> Tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).replace("；", ";").replace("、", ";").split(";")
    normalized = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        normalized.append(text)
    return tuple(sorted({t for t in normalized if t}))


def _normalize_object_ids(raw: Any) -> Tuple[int, ...]:
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple, set)):
        ids = raw
    else:
        ids = str(raw).replace("，", ",").split(",")
    normalized: List[int] = []
    for item in ids:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(set(normalized)))


@dataclass
class AlertEntry:
    group_index: int
    risk_level: str
    risk_types: Tuple[str, ...] = field(default_factory=tuple)
    danger_object_ids: Tuple[int, ...] = field(default_factory=tuple)
    danger_object_count: int | None = None
    description: str = ""
    confidence: float = 0.0
    started_at: float = field(default_factory=time.time)
    last_updated_at: float = field(default_factory=time.time)
    display_until: float = field(default_factory=time.time)

    def to_payload(self, now: float, *, is_continuation: bool, is_stale: bool) -> Dict[str, Any]:
        remaining = max(self.display_until - now, 0.0)
        return {
            "groupIndex": self.group_index,
            "riskLevel": self.risk_level,
            "riskTypes": list(self.risk_types),
            "dangerObjectIds": list(self.danger_object_ids),
            "dangerObjectCount": self.danger_object_count or len(self.danger_object_ids),
            "description": self.description,
            "confidence": self.confidence,
            "displayDuration": round(remaining, 2),
            "isContinuation": is_continuation,
            "isMerged": len(self.risk_types) > 1,
            "startedAt": self.started_at,
            "lastUpdatedAt": self.last_updated_at,
            "isStale": is_stale,
        }


class RiskAlertManager:
    """Maintain risk alerts with countdown and merge logic."""

    def __init__(self, display_window: float = 3.0) -> None:
        self.display_window = display_window
        self._entries: Dict[int, AlertEntry] = {}

    def update(
        self,
        now: float,
        llm_results: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Update alerts with freshly generated LLM results.

        Parameters
        ----------
        now:
            Current timestamp in seconds.
        llm_results:
            Parsed LLM results aligned with group indices.
        """
        updated_groups: set[int] = set()
        outputs: List[Dict[str, Any]] = []

        for result in llm_results:
            group_index = int(result.get("groupIndex") or 0)
            if group_index <= 0:
                continue

            risk_level = str(result.get("riskLevel", "none")).lower()
            risk_types = _normalize_risk_types(result.get("riskTypes") or result.get("type"))
            object_ids = _normalize_object_ids(result.get("triggerObjectIds"))
            danger_count_raw = result.get("dangerObjectCount")
            try:
                danger_count = int(danger_count_raw) if danger_count_raw is not None else None
            except (TypeError, ValueError):
                danger_count = None
            description = result.get("description", "") or ""
            confidence = float(result.get("confidence", 0.0))

            soft_keywords = {"交通拥堵", "车流拥堵", "拥堵", "车距过近", "跟车过近", "排队", "缓慢行驶", "慢速行驶"}
            severe_keywords = {"冲突", "碰撞", "追尾", "逆行", "闯红灯", "危险动作", "冲撞", "驶入人行道", "闯入人行道"}
            combined_text = str(description) + "".join(risk_types)
            if risk_level == "high" and not any(keyword in combined_text for keyword in severe_keywords):
                if risk_types and all(any(keyword in rt for keyword in soft_keywords) for rt in risk_types):
                    risk_level = "low"
                elif any(keyword in combined_text for keyword in soft_keywords):
                    risk_level = "medium"

            existing = self._entries.get(group_index)
            if existing:
                same_types = risk_types == existing.risk_types or not risk_types
                is_continuation = same_types

                if same_types:
                    # keep the original countdown, only update metadata
                    existing.last_updated_at = now
                    existing.risk_level = risk_level or existing.risk_level
                    existing.description = description or existing.description
                    existing.confidence = confidence or existing.confidence
                    if risk_types:
                        existing.risk_types = risk_types
                    if object_ids:
                        existing.danger_object_ids = object_ids
                    if danger_count:
                        existing.danger_object_count = danger_count
                else:
                    # new risk types -> reset countdown
                    existing.started_at = now
                    existing.last_updated_at = now
                    existing.display_until = now + self.display_window
                    existing.risk_level = risk_level or existing.risk_level
                    existing.risk_types = risk_types or existing.risk_types
                    existing.danger_object_ids = object_ids or existing.danger_object_ids
                    existing.danger_object_count = danger_count or existing.danger_object_count
                    existing.description = description or existing.description
                    existing.confidence = confidence or existing.confidence
                    is_continuation = False
                # ensure countdown exists when first created
                if existing.display_until < now:
                    existing.display_until = now + self.display_window
                payload = existing.to_payload(now, is_continuation=is_continuation, is_stale=False)
            else:
                entry = AlertEntry(
                    group_index=group_index,
                    risk_level=risk_level,
                    risk_types=risk_types,
                    danger_object_ids=object_ids,
                    danger_object_count=danger_count,
                    description=description,
                    confidence=confidence,
                    started_at=now,
                    last_updated_at=now,
                    display_until=now + self.display_window,
                )
                self._entries[group_index] = entry
                payload = entry.to_payload(now, is_continuation=False, is_stale=False)

            updated_groups.add(group_index)
            outputs.append(payload)

        # retain active alerts that were not refreshed this round but are still counting down
        for group_index, entry in list(self._entries.items()):
            if entry.display_until <= now:
                del self._entries[group_index]
                continue
            if group_index in updated_groups:
                continue
            outputs.append(entry.to_payload(now, is_continuation=True, is_stale=True))

        outputs.sort(key=lambda item: item.get("groupIndex", 0))
        return outputs

    def has_high_risk(self) -> bool:
        for entry in self._entries.values():
            if entry.risk_level == "high" and entry.display_until > time.time():
                return True
        return False

    def highest_risk_level(self) -> str:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        highest = "none"
        now = time.time()
        for entry in self._entries.values():
            if entry.display_until <= now:
                continue
            if order.get(entry.risk_level, 0) > order.get(highest, 0):
                highest = entry.risk_level
        return highest
