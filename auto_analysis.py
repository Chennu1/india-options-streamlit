from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import floor
from typing import Any

from market_data import OptionChainSnapshot, option_value, rows_near_spot
from options_suggestion import MarketView


@dataclass
class AutoContract:
    action: str
    strike: float
    option_type: str
    ltp: float
    open_interest: float
    reason: str


@dataclass
class AutoAnalysis:
    view: MarketView
    signal: str
    signal_strength: int
    risk_level: str
    risk_percent: float
    trend_label: str
    iv_label: str
    range_position: float
    indicators: list[dict[str, str]]
    contract: AutoContract | None
    summary: str


def build_auto_analysis(
    symbol: str,
    spot: float,
    strike_step: int,
    lot_size: int,
    capital: float,
    experience: str,
    snapshot: OptionChainSnapshot | None,
) -> AutoAnalysis:
    support = snapshot.support if snapshot else max(1.0, spot - 250)
    resistance = snapshot.resistance if snapshot else spot + 250
    pcr = snapshot.pcr if snapshot else 1.0
    avg_iv = snapshot.avg_iv if snapshot else 0.0
    days_to_expiry = estimate_days_to_expiry(snapshot.selected_expiry) if snapshot else 7
    range_position = calculate_range_position(spot, support, resistance)

    direction_score = 0
    reasons: list[str] = []
    if pcr >= 1.15:
        direction_score += 18
        reasons.append("PCR supports bullish undertone")
    elif pcr <= 0.85:
        direction_score -= 18
        reasons.append("PCR supports bearish undertone")
    else:
        reasons.append("PCR is neutral")

    if range_position >= 0.68:
        direction_score += 14
        reasons.append("spot is closer to resistance")
    elif range_position <= 0.32:
        direction_score -= 14
        reasons.append("spot is closer to support")
    else:
        reasons.append("spot is mid-range")

    if snapshot:
        oi_bias = option_oi_bias(snapshot)
        direction_score += oi_bias
        if oi_bias > 0:
            reasons.append("nearby put OI is stronger")
        elif oi_bias < 0:
            reasons.append("nearby call OI is stronger")

    if direction_score >= 18:
        signal = "BUY CALL"
        direction = "Bullish"
    elif direction_score <= -18:
        signal = "BUY PUT"
        direction = "Bearish"
    else:
        signal = "WAIT"
        direction = "Range-bound"

    signal_strength = min(100, max(0, 50 + abs(direction_score)))
    risk_level, risk_percent = dynamic_risk(signal_strength, avg_iv, days_to_expiry, experience)
    trend_strength = min(10, max(1, round(signal_strength / 10)))
    iv_percentile = implied_iv_regime(avg_iv)
    contract = choose_contract(snapshot, signal, spot, strike_step)

    view = MarketView(
        symbol=symbol,
        spot=spot,
        direction=direction,
        trend_strength=trend_strength,
        iv_percentile=iv_percentile,
        days_to_expiry=days_to_expiry,
        support=support,
        resistance=resistance,
        pcr=pcr,
        capital=capital,
        risk_percent=risk_percent,
        strike_step=strike_step,
        lot_size=lot_size,
        experience=experience,
    )

    indicators = [
        {"Indicator": "PCR", "Value": f"{pcr:.2f}", "Reading": pcr_reading(pcr)},
        {"Indicator": "Range Position", "Value": f"{range_position * 100:.0f}%", "Reading": range_reading(range_position)},
        {"Indicator": "Average IV", "Value": f"{avg_iv:.2f}", "Reading": iv_reading(avg_iv)},
        {"Indicator": "OI Bias", "Value": f"{direction_score:+d}", "Reading": signal},
        {"Indicator": "Risk", "Value": risk_level, "Reading": f"{risk_percent:.2f}% capital"},
    ]

    summary = (
        f"Auto mode reads this as {direction.lower()} with {signal_strength}/100 signal strength. "
        f"Risk is set to {risk_level.lower()} because of signal quality, IV, expiry proximity, and experience. "
        f"Key inputs: {', '.join(reasons[:3])}."
    )

    return AutoAnalysis(
        view=view,
        signal=signal,
        signal_strength=signal_strength,
        risk_level=risk_level,
        risk_percent=risk_percent,
        trend_label=trend_label(signal_strength),
        iv_label=iv_reading(avg_iv),
        range_position=range_position,
        indicators=indicators,
        contract=contract,
        summary=summary,
    )


def choose_contract(
    snapshot: OptionChainSnapshot | None,
    signal: str,
    spot: float,
    strike_step: int,
) -> AutoContract | None:
    if not snapshot or signal == "WAIT":
        return None

    option_type = "CE" if signal == "BUY CALL" else "PE"
    candidates = rows_near_spot(snapshot, width=12)
    if not candidates:
        return None

    atm = round_to_step(spot, strike_step)
    best_row = min(candidates, key=lambda row: abs(float(row.get("strikePrice") or 0) - atm))
    strike = float(best_row.get("strikePrice") or atm)
    side = best_row.get(option_type) or {}
    ltp = option_value(side, "lastPrice")
    oi = option_value(side, "openInterest")
    return AutoContract(
        action="Buy",
        strike=strike,
        option_type=option_type,
        ltp=ltp,
        open_interest=oi,
        reason="Selected nearest liquid ATM contract from the live option-chain snapshot.",
    )


def append_snapshot_history(snapshot: OptionChainSnapshot | None, signal: str) -> list[dict[str, Any]]:
    if "price_history" not in __import__("streamlit").session_state:
        __import__("streamlit").session_state["price_history"] = []
    history = __import__("streamlit").session_state["price_history"]
    if not snapshot:
        return history

    item = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "spot": float(snapshot.spot),
        "support": float(snapshot.support),
        "resistance": float(snapshot.resistance),
        "signal": signal,
    }
    if not history or history[-1] != item:
        history.append(item)
    __import__("streamlit").session_state["price_history"] = history[-80:]
    return __import__("streamlit").session_state["price_history"]


def dynamic_risk(signal_strength: int, avg_iv: float, days_to_expiry: int, experience: str) -> tuple[str, float]:
    base = 1.0
    if signal_strength >= 78:
        base += 0.5
    if signal_strength < 62:
        base -= 0.35
    if avg_iv >= 22:
        base -= 0.25
    if days_to_expiry <= 1:
        base -= 0.35
    if experience == "Beginner":
        base -= 0.25
    elif experience == "Advanced":
        base += 0.25
    percent = max(0.25, min(2.0, round(base, 2)))
    if percent <= 0.6:
        return "Low", percent
    if percent <= 1.25:
        return "Medium", percent
    return "High", percent


def option_oi_bias(snapshot: OptionChainSnapshot) -> int:
    rows = rows_near_spot(snapshot, width=8)
    put_oi = sum(option_value(row.get("PE"), "openInterest") for row in rows)
    call_oi = sum(option_value(row.get("CE"), "openInterest") for row in rows)
    total = put_oi + call_oi
    if total <= 0:
        return 0
    ratio = (put_oi - call_oi) / total
    return int(ratio * 30)


def calculate_range_position(spot: float, support: float, resistance: float) -> float:
    width = max(resistance - support, 1)
    return max(0.0, min(1.0, (spot - support) / width))


def implied_iv_regime(avg_iv: float) -> int:
    if avg_iv <= 0:
        return 45
    return max(5, min(95, int(avg_iv * 3)))


def estimate_days_to_expiry(expiry: str) -> int:
    if not expiry:
        return 7
    for fmt in ("%d-%b-%Y", "%d%b%Y", "%d%b%y"):
        try:
            expiry_date = datetime.strptime(expiry.replace(" ", ""), fmt).date()
            return max(0, (expiry_date - datetime.now().date()).days)
        except ValueError:
            continue
    return 7


def round_to_step(value: float, step: int) -> int:
    if step <= 0:
        return int(round(value))
    return int(round(value / step) * step)


def pcr_reading(pcr: float) -> str:
    if pcr >= 1.15:
        return "Bullish"
    if pcr <= 0.85:
        return "Bearish"
    return "Neutral"


def range_reading(position: float) -> str:
    if position >= 0.68:
        return "Near resistance"
    if position <= 0.32:
        return "Near support"
    return "Mid-range"


def iv_reading(avg_iv: float) -> str:
    if avg_iv <= 0:
        return "Unknown"
    if avg_iv >= 22:
        return "High volatility"
    if avg_iv <= 11:
        return "Low volatility"
    return "Normal volatility"


def trend_label(strength: int) -> str:
    if strength >= 78:
        return "Strong"
    if strength >= 62:
        return "Developing"
    return "Weak"
