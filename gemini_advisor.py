from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

import requests

from options_suggestion import MarketView, StrategyIdea


@dataclass
class GeminiBrief:
    summary: str
    setup_quality: str
    top_risks: list[str]
    what_to_watch: list[str]
    trade_management: list[str]
    disclaimer: str
    model: str


class GeminiAdvisorError(RuntimeError):
    pass


SYSTEM_PROMPT = """
You are a cautious Indian options-market analyst inside an educational planning app.
Return only JSON.

Required JSON schema:
{
  "summary": "short paragraph",
  "setup_quality": "Avoid | Weak | Moderate | Strong",
  "top_risks": ["risk 1", "risk 2", "risk 3"],
  "what_to_watch": ["watch item 1", "watch item 2", "watch item 3"],
  "trade_management": ["management item 1", "management item 2", "management item 3"]
}

Rules:
- Do not give personalized investment advice.
- Do not say guaranteed, sure-shot, risk-free, or must buy/sell.
- Discuss conditions, invalidation, position sizing, and risk.
- Keep it concise and useful for an options trader in India.
""".strip()


def generate_gemini_brief(
    view: MarketView,
    suggestions: list[StrategyIdea],
    snapshot_summary: dict[str, Any] | None,
    api_key: str | None = None,
    model: str | None = None,
) -> GeminiBrief:
    clean_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not clean_key:
        raise GeminiAdvisorError("Add GEMINI_API_KEY in the app, environment, or Streamlit secrets.")

    selected_model = (model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")).strip() or "gemini-2.0-flash"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "market_view": asdict(view),
                                "strategy_suggestions": [asdict(item) for item in suggestions[:3]],
                                "live_data_summary": snapshot_summary or {},
                            },
                            indent=2,
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
        },
    }

    try:
        response = requests.post(endpoint, params={"key": clean_key}, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise GeminiAdvisorError(f"Gemini request failed: {exc}") from exc
    except ValueError as exc:
        raise GeminiAdvisorError("Gemini returned a non-JSON response.") from exc

    raw_text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = parse_json_block(raw_text)
    return normalize_brief(parsed, selected_model)


def normalize_brief(data: dict[str, Any], model: str) -> GeminiBrief:
    quality = str(data.get("setup_quality", "Moderate")).strip().title()
    if quality not in {"Avoid", "Weak", "Moderate", "Strong"}:
        quality = "Moderate"

    return GeminiBrief(
        summary=str(data.get("summary", "")).strip() or "Gemini brief generated.",
        setup_quality=quality,
        top_risks=ensure_list(data.get("top_risks"), ["Market risk and execution risk remain material."])[:4],
        what_to_watch=ensure_list(data.get("what_to_watch"), ["Watch spot near key support and resistance."])[:4],
        trade_management=ensure_list(data.get("trade_management"), ["Predefine entry, stop, target, and maximum loss."])[:4],
        disclaimer="Gemini output is educational analysis only, not investment advice.",
        model=model,
    )


def parse_json_block(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw_text[start : end + 1])
        raise GeminiAdvisorError("Gemini did not return valid JSON.")


def ensure_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if cleaned:
            return cleaned
    return fallback
