"""Integration with DashScope/Qwen-VL via OpenAI-compatible API."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence
from dotenv import load_dotenv

from loguru import logger
from openai import OpenAI

from algo.llm.prompts import DANGEROUS_DRIVING_PROMPT

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
                self._client = OpenAI(api_key=api_key, base_url=config.base_url)
            except Exception as exc:  # pragma: no cover - client init failure
                logger.error("Failed to initialise OpenAI-compatible client: %s", exc)
                self.enabled = False

        self._last_call_ts: float = 0.0

    def should_analyze(self, detections: Sequence[Dict], groups: Sequence[Dict]) -> bool:
        if not self.enabled or not self._client:
            return False
        if time.time() - self._last_call_ts < self.config.cooldown_seconds:
            return False
        if len(detections) >= 2:
            return True
        if groups:
            return True
        return False

    def analyze(
        self,
        image_data_url: str,
        detections: Sequence[Dict],
        groups: Sequence[Dict],
    ) -> Dict[str, Any]:
        start_time = time.time()
        if not self.enabled or not self._client:
            return self._empty_result(latency=0.0)

        prompt = self._build_prompt(detections, groups)
        messages = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "You are a professional traffic safety analyst."},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": prompt},
                ],
            },
        ]

        attempt = 0
        while attempt <= self.config.max_retry:
            attempt += 1
            try:
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    timeout=self.config.timeout,
                )
            except Exception as exc:  # pragma: no cover - network failure
                logger.error("DashScope(OpenAI) call failed: %s", exc)
                time.sleep(1.0)
                continue

            choices = response.choices or []
            if not choices:
                logger.warning("DashScope(OpenAI) returned empty choices: %s", response)
                time.sleep(1.0)
                continue

            raw_text = self._extract_text(choices[0].message)
            parsed = self._parse_llm_output(raw_text)
            parsed["rawText"] = raw_text
            parsed["latency"] = time.time() - start_time
            parsed["model"] = self.config.model
            self._last_call_ts = time.time()
            return parsed

        logger.error("DashScope(OpenAI) call failed after %s attempts", self.config.max_retry + 1)
        return self._empty_result(latency=time.time() - start_time)

    def _build_prompt(self, detections: Sequence[Dict], groups: Sequence[Dict]) -> str:
        obj_lines = []
        for det in detections:
            bbox = det.get("bbox", [])
            obj_lines.append(
                f"- class={det.get('class')} conf={det.get('confidence', 0):.2f} bbox={bbox}"
            )

        group_lines = []
        for group in groups:
            group_lines.append(
                f"- groupId={group.get('groupId')} count={group.get('objectCount')} classes={group.get('classes')} bbox={group.get('bbox')}"
            )

        summary = "\n".join(obj_lines) or "无检测目标"
        group_summary = "\n".join(group_lines) or "无对象聚集"

        return (
            f"{DANGEROUS_DRIVING_PROMPT}\n"
            f"[检测对象]\n{summary}\n"
            f"[对象群组]\n{group_summary}\n"
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
        normalized_results = []
        max_risk = "none"
        for item in results:
            risk = str(item.get("riskLevel", "none")).lower()
            confidence = float(item.get("confidence", 0.0))
            if risk not in {"none", "low", "medium", "high"}:
                risk = self._risk_from_confidence(confidence)
            normalized_results.append(
                {
                    "type": item.get("type", "unknown"),
                    "description": item.get("description", ""),
                    "riskLevel": risk,
                    "confidence": confidence,
                }
            )
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
            logger.debug("Failed to parse LLM JSON from candidate: %s", candidate)
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
