"""Integration with DashScope/Qwen-VL via OpenAI-compatible API."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence
import math
from dotenv import load_dotenv

from loguru import logger
from openai import OpenAI

from algo.llm.prompts import DANGEROUS_DRIVING_PROMPT

# Import Prometheus metrics (optional)
try:
    from algo.monitoring.metrics import record_llm_request
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("Prometheus metrics not available for LLM monitoring")

load_dotenv() # take environment variables from .env if available

@dataclass
class DangerousDrivingConfig:
    model: str = "qwen-vl-plus"
    timeout: int = 30
    max_retry: int = 2
    cooldown_seconds: float = 3.0
    risk_threshold_low: float = 0.45
    risk_threshold_medium: float = 0.65
    risk_threshold_high: float = 0.80
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class DangerousDrivingAnalyzer:
    """Call Qwen-VL to judge dangerous driving conditions."""

    def __init__(self, config: DangerousDrivingConfig, enabled: bool = True) -> None:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        self.config = config
        self._client: OpenAI | None = None
        self.enabled = enabled

        if not enabled:
            logger.info("Dangerous driving analysis disabled via configuration.")
        elif not api_key:
            logger.warning("DASHSCOPE_API_KEY not set, LLM analysis disabled.")
            self.enabled = False
        else:
            try:
                self.client = OpenAI(api_key=api_key, base_url=self.config.base_url)
            except Exception as exc:
                logger.error("Failed to initialise OpenAI-compatible client: {}", exc)
                raise

        self._last_call_ts: float = 0.0

    def should_analyze(
        self,
        detections: Sequence[Dict],
        groups: Sequence[Dict],
        group_images: Sequence[Dict],
    ) -> bool:
        if not self.enabled or not self._client:
            return False
        if time.time() - self._last_call_ts < self.config.cooldown_seconds:
            return False
        if not group_images:
            return False
        if len(detections) >= 2:
            return True
        if groups:
            return True
        return False

    def analyze(
        self,
        group_images: Sequence[Dict],
        detections: Sequence[Dict],
        groups: Sequence[Dict],
    ) -> Dict[str, Any]:
        start_time = time.time()
        if not self.enabled or not self._client:
            return self._empty_result(latency=0.0)

        if not group_images:
            return self._empty_result(latency=0.0)

        prompt = self._build_prompt(detections, groups, group_images)

        content: List[Dict[str, Any]] = []
        for position, image in enumerate(group_images, start=1):
            data_uri = image.get("dataUri")
            if not data_uri:
                continue
            group_index = image.get("groupIndex")
            label = group_index if group_index is not None else position
            content.append({"type": "text", "text": f"Group image #{position} (groupIndex={label})"})
            content.append({"type": "image_url", "image_url": {"url": data_uri}})
        content.append({"type": "text", "text": prompt})

        if len(content) <= 1:
            return self._empty_result(latency=0.0)

        messages = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "You are a professional traffic safety analyst."},
                ],
            },
            {
                "role": "user",
                "content": content,
            },
        ]

        attempt = 0
        while attempt <= self.config.max_retry:
            attempt += 1
            try:
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,  # type: ignore[arg-type]
                    timeout=self.config.timeout,
                )
            except Exception as exc:  # pragma: no cover - network failure
                logger.error("DashScope(OpenAI) call failed: {}", exc)
                latency = time.time() - start_time
                # Record failed request to Prometheus
                if METRICS_AVAILABLE:
                    record_llm_request(
                        model=self.config.model,
                        api_key_id='default',
                        latency=latency,
                        status='error'
                    )
                time.sleep(1.0)
                continue

            choices = response.choices or []
            if not choices:
                logger.warning("DashScope(OpenAI) returned empty choices: {}", response)
                latency = time.time() - start_time
                # Record failed request to Prometheus
                if METRICS_AVAILABLE:
                    record_llm_request(
                        model=self.config.model,
                        api_key_id='default',
                        latency=latency,
                        status='empty_response'
                    )
                time.sleep(1.0)
                continue

            raw_text = self._extract_text(choices[0].message)
            parsed = self._parse_llm_output(raw_text)
            parsed["rawText"] = raw_text
            latency = time.time() - start_time
            parsed["latency"] = latency
            parsed["model"] = self.config.model
            self._last_call_ts = time.time()
            
            # Record successful request to Prometheus
            if METRICS_AVAILABLE:
                # Extract token usage if available
                usage = getattr(response, 'usage', None)
                prompt_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
                completion_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
                
                record_llm_request(
                    model=self.config.model,
                    api_key_id='default',
                    latency=latency,
                    status='success',
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens
                )
            
            return parsed

        logger.error("DashScope(OpenAI) call failed after {} attempts", self.config.max_retry + 1)
        final_latency = time.time() - start_time
        
        # Record final failure to Prometheus
        if METRICS_AVAILABLE:
            record_llm_request(
                model=self.config.model,
                api_key_id='default',
                latency=final_latency,
                status='max_retries_exceeded'
            )
        
        return self._empty_result(latency=final_latency)

    def _build_prompt(
        self,
        detections: Sequence[Dict],
        groups: Sequence[Dict],
        group_images: Sequence[Dict],
    ) -> str:
        obj_lines = []
        for det in detections:
            bbox = det.get('bbox', [])
            obj_lines.append(
                f"- class={det.get('class')} confidence={det.get('confidence', 0):.2f} bbox={bbox}"
            )

        def _summarize_group(group: Dict[str, Any]) -> str:
            bbox = group.get('bbox', [0, 0, 0, 0])
            x1, y1, x2, y2 = bbox if len(bbox) == 4 else (0, 0, 0, 0)
            width = max(float(x2) - float(x1), 1.0)
            height = max(float(y2) - float(y1), 1.0)
            area = width * height

            indices = group.get('memberIndices') or []
            selected: List[Dict[str, Any]] = []
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(detections):
                    selected.append(detections[idx])

            if not selected:
                for det in detections:
                    db = det.get('bbox', [])
                    if len(db) != 4:
                        continue
                    cx = (float(db[0]) + float(db[2])) / 2.0
                    cy = (float(db[1]) + float(db[3])) / 2.0
                    if x1 <= cx <= x2 and y1 <= cy <= y2:
                        selected.append(det)

            centers: List[tuple[float, float]] = []
            for det in selected:
                db = det.get('bbox', [])
                if len(db) != 4:
                    continue
                centers.append(
                    ((float(db[0]) + float(db[2])) / 2.0, (float(db[1]) + float(db[3])) / 2.0)
                )

            distances: List[float] = []
            for i in range(len(centers)):
                for j in range(i + 1, len(centers)):
                    dx = centers[i][0] - centers[j][0]
                    dy = centers[i][1] - centers[j][1]
                    distances.append(math.hypot(dx, dy))

            avg_spacing = sum(distances) / len(distances) if distances else None
            min_spacing = min(distances) if distances else None
            density = (len(selected) / area * 10000.0) if area > 0 else None

            vehicle_classes = {'car', 'bus', 'truck', 'motorcycle', 'bicycle'}
            pedestrian_classes = {'person'}

            vehicle_centers: List[tuple[float, float]] = []
            pedestrian_centers: List[tuple[float, float]] = []
            for det, center in zip(selected, centers):
                cls = str(det.get('class'))
                if cls in vehicle_classes:
                    vehicle_centers.append(center)
                if cls in pedestrian_classes:
                    pedestrian_centers.append(center)

            ped_vehicle_min_dist: float | None = None
            if vehicle_centers and pedestrian_centers:
                pv_distances = [
                    math.hypot(vc[0] - pc[0], vc[1] - pc[1])
                    for vc in vehicle_centers
                    for pc in pedestrian_centers
                ]
                if pv_distances:
                    ped_vehicle_min_dist = min(pv_distances)

            summary_parts = [
                f"groupIndex={group.get('groupIndex')}" ,
                f"count={group.get('objectCount')}" ,
                f"classes={group.get('classes')}" ,
                f"bbox={bbox}",
            ]
            if density is not None:
                summary_parts.append(f"density={density:.2f}/1e4px")
            if avg_spacing is not None:
                summary_parts.append(f"avgSpacing={avg_spacing:.1f}px")
            if min_spacing is not None:
                summary_parts.append(f"minSpacing={min_spacing:.1f}px")
            summary_parts.append(f"vehicles={len(vehicle_centers)}")
            summary_parts.append(f"pedestrians={len(pedestrian_centers)}")
            if ped_vehicle_min_dist is not None:
                summary_parts.append(f"pedVehicleMinDist={ped_vehicle_min_dist:.1f}px")
            return "- " + " ".join(summary_parts)

        group_lines = [_summarize_group(group) for group in groups]

        mapping_lines: List[str] = []
        for position, image in enumerate(group_images, start=1):
            mapping_lines.append(
                f"- image#{position} -> groupIndex={image.get('groupIndex')} (objects={image.get('objectCount')}, classes={image.get('classes')})"
            )

        summary = '\n'.join(obj_lines) or 'No detections'
        group_summary = '\n'.join(group_lines) or 'No traffic groups'
        mapping_summary = '\n'.join(mapping_lines) or 'No group images'

        return (
            f"{DANGEROUS_DRIVING_PROMPT}\n"
            f"[Group Image Mapping]\n{mapping_summary}\n"
            f"[Detected Objects]\n{summary}\n"
            f"[Traffic Groups]\n{group_summary}\n"
        )

    @staticmethod
    def _extract_text(message: Any) -> str:
        content = getattr(message, "content", message)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        return str(content)

    def _parse_llm_output(self, raw_text: str) -> Dict[str, Any]:
        json_payload = self._extract_json(raw_text)
        if json_payload is None:
            return self._empty_result(latency=0.0, raw_text=raw_text)

        results = json_payload.get("results", [])
        normalized_results: List[Dict[str, Any]] = []
        max_risk = "none"

        fallback_indices = []
        seen = set()
        for group in json_payload.get("groups", []):
            idx = group.get("groupIndex")
            if idx and idx not in seen:
                fallback_indices.append(int(idx))
                seen.add(idx)

        def _fallback_index(position: int) -> int:
            if position < len(fallback_indices):
                return fallback_indices[position]
            return position + 1

        for position, item in enumerate(results):
            risk = str(item.get("riskLevel", "none")).lower()
            confidence = float(item.get("confidence", 0.0))
            if risk not in {"none", "low", "medium", "high"}:
                risk = self._risk_from_confidence(confidence)

            group_index = item.get("groupIndex")
            try:
                group_index = int(group_index) if group_index is not None else None
            except (TypeError, ValueError):
                group_index = None
            if not group_index:
                group_index = _fallback_index(position)

            risk_types = item.get("riskTypes", [])
            if isinstance(risk_types, str):
                tokens = (
                    risk_types.replace("；", ";")
                    .replace("、", ";")
                    .replace("，", ";")
                    .split(";")
                )
                risk_types = [token.strip() for token in tokens if token.strip()]
            elif isinstance(risk_types, (list, tuple, set)):
                risk_types = [str(token).strip() for token in risk_types if str(token).strip()]
            else:
                fallback_type = item.get("type")
                risk_types = [str(fallback_type).strip()] if fallback_type else []

            trigger_ids = item.get("triggerObjectIds", [])
            parsed_ids: List[int] = []
            if isinstance(trigger_ids, (list, tuple, set)):
                for value in trigger_ids:
                    try:
                        parsed_ids.append(int(value))
                    except (TypeError, ValueError):
                        continue
            elif trigger_ids is None:
                parsed_ids = []
            else:
                for token in str(trigger_ids).replace("，", ",").split(","):
                    token = token.strip()
                    if not token:
                        continue
                    try:
                        parsed_ids.append(int(token))
                    except ValueError:
                        continue
            trigger_ids = parsed_ids

            danger_count = item.get("dangerObjectCount")
            try:
                danger_count = int(danger_count) if danger_count is not None else None
            except (TypeError, ValueError):
                danger_count = None

            description = str(item.get("description", ""))
            soft_keywords = {"交通拥堵", "车流拥堵", "拥堵", "车距过近", "跟车过近", "排队", "缓慢行驶", "慢速行驶"}
            severe_keywords = {"冲突", "碰撞", "追尾", "逆行", "闯红灯", "危险动作", "冲撞", "驶入人行道", "闯入人行道"}
            combined_text = description + "".join(risk_types)
            if risk == "high" and not any(keyword in combined_text for keyword in severe_keywords):
                if risk_types and all(any(keyword in rt for keyword in soft_keywords) for rt in risk_types):
                    risk = "low"
                elif any(keyword in combined_text for keyword in soft_keywords):
                    risk = "medium"
                elif not combined_text:
                    risk = "medium"

            normalized_item = {
                "groupIndex": group_index,
                "type": item.get("type", "unknown"),
                "description": item.get("description", ""),
                "riskLevel": risk,
                "confidence": confidence,
                "riskTypes": risk_types,
                "dangerObjectCount": danger_count,
                "triggerObjectIds": trigger_ids,
            }
            normalized_results.append(normalized_item)

            if self._risk_level_value(risk) > self._risk_level_value(max_risk):
                max_risk = risk

        has_dangerous = bool(json_payload.get("hasDangerousDriving", max_risk != "none"))

        if has_dangerous and max_risk == "none" and normalized_results:
            top_conf = max(normalized_results, key=lambda item: item.get("confidence", 0.0))
            max_risk = top_conf["riskLevel"]

        return {
            "hasDangerousDriving": has_dangerous,
            "maxRiskLevel": max_risk,
            "results": normalized_results,
        }

    def _extract_json(self, text: str) -> Dict[str, Any] | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            logger.debug("Failed to parse LLM JSON from candidate: {}", candidate)
            return None

    def _empty_result(self, latency: float, raw_text: str | None = None) -> Dict[str, Any]:
        return {
            "hasDangerousDriving": False,
            "maxRiskLevel": "none",
            "results": [],
            "latency": latency,
            "model": self.config.model,
            "rawText": raw_text,
        }

    @staticmethod
    def _risk_level_value(level: str) -> int:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        return order.get(level, 0)

    def _risk_from_confidence(self, confidence: float) -> str:
        if confidence >= self.config.risk_threshold_high:
            return "high"
        if confidence >= self.config.risk_threshold_medium:
            return "medium"
        if confidence >= self.config.risk_threshold_low:
            return "low"
        return "none"
