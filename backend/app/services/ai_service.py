"""Groq AI service.

Two capabilities are used by the project:

1. ``analyse_frame`` - sends a camera frame to a Groq vision model and asks it
   to report which of the four tracked traffic violations are present, with a
   confidence score for each. This is the "AI" half of the detection pipeline
   (the OpenCV heuristics in ``detection_service.py`` are the fallback half).
2. ``summarise`` - uses a Groq text model to write the natural-language summary
   shown on the Reports page.

The API key is read from ``GROQ_API_KEY`` on the server only.
"""

from __future__ import annotations

import base64
import json
import logging
import time

import httpx

from ..config import settings
from ..constants import VIOLATION_CATALOGUE, VIOLATION_TYPES
from .base import not_configured, result

logger = logging.getLogger("rto.ai")

PROVIDER = "Groq AI"
BASE_URL = "https://api.groq.com/openai/v1"
INSTRUCTION = "Add GROQ_API_KEY to backend/.env (get it from console.groq.com/keys)."

_VIOLATION_GUIDE = "\n".join(
    f"- {item['code']}: {item['description']}" for item in VIOLATION_CATALOGUE
)

SYSTEM_PROMPT = (
    "You are an automated traffic enforcement vision analyst for an Indian RTO. "
    "You examine a single CCTV frame and report only violations you can actually "
    "see. Be conservative: if the image is unclear, return an empty list.\n\n"
    f"Violations you may report:\n{_VIOLATION_GUIDE}\n\n"
    'Reply with STRICT JSON only, shaped as: {"violations": [{"type": "NO_HELMET", '
    '"confidence": 0.0-1.0, "vehicle_type": "two wheeler", "reason": "short reason", '
    '"plate_text": "readable plate or empty"}], "scene": "one line description", '
    '"vehicle_count": 0}'
)


def is_configured() -> bool:
    return settings.ai_configured


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.groq_api_key.strip()}",
        "Content-Type": "application/json",
    }


async def test_connection() -> dict:
    """Called by the Admin -> API Configuration page."""
    if not is_configured():
        return not_configured(PROVIDER, INSTRUCTION)

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{BASE_URL}/models", headers=_headers())
        latency = int((time.perf_counter() - started) * 1000)

        if response.status_code == 200:
            models = [item.get("id") for item in response.json().get("data", [])]
            return result(
                ok=True,
                provider=PROVIDER,
                message=f"Connected. {len(models)} models available.",
                data={
                    "models_available": len(models),
                    "configured_vision_model": settings.groq_model,
                    "configured_text_model": settings.groq_text_model,
                    "vision_model_present": settings.groq_model in models,
                },
                status_code=response.status_code,
                latency_ms=latency,
            )
        return result(
            ok=False,
            provider=PROVIDER,
            message=f"Groq rejected the key: HTTP {response.status_code} {response.text[:180]}",
            status_code=response.status_code,
            latency_ms=latency,
        )
    except httpx.HTTPError as exc:
        return result(
            ok=False,
            provider=PROVIDER,
            message=f"Could not reach Groq: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


async def analyse_frame(image_bytes: bytes, context: str = "") -> dict:
    """Ask the Groq vision model which violations appear in a frame."""
    if not is_configured():
        return not_configured(PROVIDER, INSTRUCTION)

    encoded = base64.b64encode(image_bytes).decode()
    payload = {
        "model": settings.groq_model,
        "temperature": 0.1,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyse this traffic camera frame and report violations "
                            f"as strict JSON. Camera context: {context or 'not provided'}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                    },
                ],
            },
        ],
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions", headers=_headers(), json=payload
            )
        latency = int((time.perf_counter() - started) * 1000)
    except httpx.HTTPError as exc:
        return result(ok=False, provider=PROVIDER, message=f"Groq request failed: {exc}")

    if response.status_code != 200:
        return result(
            ok=False,
            provider=PROVIDER,
            message=f"Groq vision error HTTP {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
            latency_ms=latency,
        )

    body = response.json()
    content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
    parsed = _extract_json(content)

    detections = []
    for item in parsed.get("violations") or []:
        code = str(item.get("type", "")).upper().replace(" ", "_")
        if code not in VIOLATION_TYPES:
            continue
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        detections.append(
            {
                "violation_type": code,
                "confidence": round(min(max(confidence, 0.0), 1.0), 3),
                "reason": str(item.get("reason", ""))[:240],
                "vehicle_type": str(item.get("vehicle_type", ""))[:60],
                "plate_text": str(item.get("plate_text", ""))[:20].upper(),
            }
        )

    return result(
        ok=True,
        provider=PROVIDER,
        message="Frame analysed by Groq vision model",
        data={
            "detections": detections,
            "scene": str(parsed.get("scene", ""))[:240],
            "vehicle_count": parsed.get("vehicle_count"),
            "model": settings.groq_model,
            "raw_text": content[:800],
        },
        status_code=200,
        latency_ms=latency,
    )


async def summarise(prompt: str) -> dict:
    """Natural-language report summary (Reports page)."""
    if not is_configured():
        return not_configured(PROVIDER, INSTRUCTION)

    payload = {
        "model": settings.groq_text_model,
        "temperature": 0.3,
        "max_tokens": 500,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a traffic enforcement analyst. Write a concise, factual "
                    "briefing for RTO officers using only the statistics provided. "
                    "Use short paragraphs and plain language. Do not invent numbers."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions", headers=_headers(), json=payload
            )
    except httpx.HTTPError as exc:
        return result(ok=False, provider=PROVIDER, message=f"Groq request failed: {exc}")

    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        return result(
            ok=False,
            provider=PROVIDER,
            message=f"Groq error HTTP {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
            latency_ms=latency,
        )

    content = (
        (response.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    )
    return result(
        ok=True,
        provider=PROVIDER,
        message="Summary generated",
        data={"summary": content.strip(), "model": settings.groq_text_model},
        status_code=200,
        latency_ms=latency,
    )
