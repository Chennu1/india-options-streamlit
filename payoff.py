from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedLeg:
    action: str
    strike: float
    option_type: str
    premium: float


@dataclass
class PayoffResult:
    rows: list[dict[str, float]]
    legs: list[ParsedLeg]
    premium_source: str
    net_premium: float
    max_profit: float
    max_loss: float
    breakevens: list[float]


def build_payoff(
    leg_texts: list[str],
    snapshot: Any,
    spot: float,
    strike_step: int,
    lot_size: int,
) -> PayoffResult | None:
    if not snapshot:
        return None

    legs = parse_legs(leg_texts, snapshot)
    if not legs:
        return None

    low = min([spot * 0.96] + [leg.strike for leg in legs]) - 3 * strike_step
    high = max([spot * 1.04] + [leg.strike for leg in legs]) + 3 * strike_step
    points = price_grid(low, high, strike_step)

    rows = []
    for price in points:
        payoff = sum(expiry_payoff(price, leg) for leg in legs) * lot_size
        rows.append({"Underlying": price, "P/L": round(payoff, 2)})

    profits = [row["P/L"] for row in rows]
    return PayoffResult(
        rows=rows,
        legs=legs,
        premium_source="Live option LTP" if all(leg.premium > 0 for leg in legs) else "Partial live LTP",
        net_premium=round(sum(leg_premium_effect(leg) for leg in legs) * lot_size, 2),
        max_profit=round(max(profits), 2),
        max_loss=round(min(profits), 2),
        breakevens=find_breakevens(rows),
    )


def parse_legs(leg_texts: list[str], snapshot: Any) -> list[ParsedLeg]:
    legs: list[ParsedLeg] = []
    for text in leg_texts:
        parts = text.split()
        if len(parts) != 3 or parts[0] not in {"Buy", "Sell"} or parts[2] not in {"CE", "PE"}:
            continue
        try:
            strike = float(parts[1])
        except ValueError:
            continue
        premium = lookup_premium(snapshot, strike, parts[2])
        legs.append(
            ParsedLeg(
                action=parts[0],
                strike=strike,
                option_type=parts[2],
                premium=premium,
            )
        )
    return legs


def lookup_premium(snapshot: Any, strike: float, option_type: str) -> float:
    for row in getattr(snapshot, "rows", []):
        try:
            row_strike = float(row.get("strikePrice") or 0)
        except (TypeError, ValueError):
            continue
        if row_strike == strike:
            side = row.get(option_type) or {}
            return numeric(side.get("lastPrice") or side.get("ltp") or 0)
    return 0.0


def expiry_payoff(price: float, leg: ParsedLeg) -> float:
    intrinsic = max(0.0, price - leg.strike) if leg.option_type == "CE" else max(0.0, leg.strike - price)
    if leg.action == "Buy":
        return intrinsic - leg.premium
    return leg.premium - intrinsic


def leg_premium_effect(leg: ParsedLeg) -> float:
    return -leg.premium if leg.action == "Buy" else leg.premium


def price_grid(low: float, high: float, step: int) -> list[float]:
    step = max(1, int(step))
    start = int(low // step * step)
    end = int((high // step + 1) * step)
    return [float(value) for value in range(start, end + step, step)]


def find_breakevens(rows: list[dict[str, float]]) -> list[float]:
    breakevens: list[float] = []
    for previous, current in zip(rows, rows[1:]):
        prev_pl = previous["P/L"]
        curr_pl = current["P/L"]
        if prev_pl == 0:
            breakevens.append(previous["Underlying"])
        elif prev_pl * curr_pl < 0:
            span = current["Underlying"] - previous["Underlying"]
            ratio = abs(prev_pl) / (abs(prev_pl) + abs(curr_pl))
            breakevens.append(round(previous["Underlying"] + span * ratio, 2))
    return dedupe_numbers(breakevens)


def dedupe_numbers(values: list[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        if not any(abs(value - existing) < 0.01 for existing in result):
            result.append(value)
    return result[:4]


def numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
