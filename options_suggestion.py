from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor


INDEX_DEFAULTS = {
    "NIFTY": {"strike_step": 50, "lot_size": 75},
    "BANKNIFTY": {"strike_step": 100, "lot_size": 30},
    "FINNIFTY": {"strike_step": 50, "lot_size": 65},
    "MIDCPNIFTY": {"strike_step": 25, "lot_size": 120},
    "SENSEX": {"strike_step": 100, "lot_size": 10},
    "STOCK OPTION": {"strike_step": 10, "lot_size": 1},
}


@dataclass
class MarketView:
    symbol: str
    spot: float
    direction: str
    trend_strength: int
    iv_percentile: int
    days_to_expiry: int
    support: float
    resistance: float
    pcr: float
    capital: float
    risk_percent: float
    strike_step: int
    lot_size: int
    experience: str


@dataclass
class StrategyIdea:
    name: str
    bias: str
    legs: list[str]
    entry_filter: list[str]
    exit_plan: list[str]
    risk_notes: list[str]
    score: int
    max_risk_per_lot: float | None
    affordable_lots: int | None


def generate_suggestions(view: MarketView) -> list[StrategyIdea]:
    ideas: list[StrategyIdea] = []
    risk_budget = view.capital * view.risk_percent / 100

    if view.direction == "Bullish":
        ideas.append(bull_call_spread(view, risk_budget))
        if view.iv_percentile >= 55 and view.experience != "Beginner":
            ideas.append(bull_put_spread(view, risk_budget))
        else:
            ideas.append(long_call(view, risk_budget))

    elif view.direction == "Bearish":
        ideas.append(bear_put_spread(view, risk_budget))
        if view.iv_percentile >= 55 and view.experience != "Beginner":
            ideas.append(bear_call_spread(view, risk_budget))
        else:
            ideas.append(long_put(view, risk_budget))

    else:
        ideas.append(iron_fly_or_condor(view, risk_budget))
        if view.experience != "Beginner":
            ideas.append(short_strangle_with_hedges(view, risk_budget))
        else:
            ideas.append(no_trade_wait(view))

    return sorted(ideas, key=lambda idea: idea.score, reverse=True)


def bull_call_spread(view: MarketView, risk_budget: float) -> StrategyIdea:
    buy = round_to_step(max(view.spot, view.support), view.strike_step, "up")
    sell = round_to_step(min(view.resistance, buy + 2 * view.strike_step), view.strike_step, "up")
    if sell <= buy:
        sell = buy + 2 * view.strike_step
    width = sell - buy
    estimated_debit = width * 0.35
    return StrategyIdea(
        name="Bull Call Spread",
        bias="Defined-risk bullish",
        legs=[f"Buy {buy:g} CE", f"Sell {sell:g} CE"],
        entry_filter=bullish_filters(view),
        exit_plan=standard_exit_plan(view, "bullish"),
        risk_notes=[
            "Risk is limited to net debit paid plus brokerage and taxes.",
            "Avoid entering if the spread debit is more than 45% of the strike width.",
        ],
        score=score_base(view, "Bullish") + (12 if view.iv_percentile < 60 else 4),
        max_risk_per_lot=estimated_debit * view.lot_size,
        affordable_lots=lots_for_budget(risk_budget, estimated_debit, view.lot_size),
    )


def bull_put_spread(view: MarketView, risk_budget: float) -> StrategyIdea:
    sell = round_to_step(min(view.support, view.spot - view.strike_step), view.strike_step, "down")
    buy = sell - 2 * view.strike_step
    width = sell - buy
    estimated_max_loss = width * 0.65 * view.lot_size
    return StrategyIdea(
        name="Bull Put Spread",
        bias="Defined-risk bullish income",
        legs=[f"Sell {sell:g} PE", f"Buy {buy:g} PE"],
        entry_filter=bullish_filters(view) + ["Prefer when IV percentile is elevated and support is clearly below spot."],
        exit_plan=credit_exit_plan(),
        risk_notes=[
            "Loss can expand quickly if price breaks support; keep the hedge leg active.",
            "Do not hold through major event risk unless that is part of your tested plan.",
        ],
        score=score_base(view, "Bullish") + (14 if view.iv_percentile >= 55 else 2),
        max_risk_per_lot=estimated_max_loss,
        affordable_lots=max(0, floor(risk_budget / estimated_max_loss)) if estimated_max_loss else None,
    )


def bear_put_spread(view: MarketView, risk_budget: float) -> StrategyIdea:
    buy = round_to_step(min(view.spot, view.resistance), view.strike_step, "down")
    sell = round_to_step(max(view.support, buy - 2 * view.strike_step), view.strike_step, "down")
    if sell >= buy:
        sell = buy - 2 * view.strike_step
    width = buy - sell
    estimated_debit = width * 0.35
    return StrategyIdea(
        name="Bear Put Spread",
        bias="Defined-risk bearish",
        legs=[f"Buy {buy:g} PE", f"Sell {sell:g} PE"],
        entry_filter=bearish_filters(view),
        exit_plan=standard_exit_plan(view, "bearish"),
        risk_notes=[
            "Risk is limited to net debit paid plus brokerage and taxes.",
            "Avoid entering if the spread debit is more than 45% of the strike width.",
        ],
        score=score_base(view, "Bearish") + (12 if view.iv_percentile < 60 else 4),
        max_risk_per_lot=estimated_debit * view.lot_size,
        affordable_lots=lots_for_budget(risk_budget, estimated_debit, view.lot_size),
    )


def bear_call_spread(view: MarketView, risk_budget: float) -> StrategyIdea:
    sell = round_to_step(max(view.resistance, view.spot + view.strike_step), view.strike_step, "up")
    buy = sell + 2 * view.strike_step
    width = buy - sell
    estimated_max_loss = width * 0.65 * view.lot_size
    return StrategyIdea(
        name="Bear Call Spread",
        bias="Defined-risk bearish income",
        legs=[f"Sell {sell:g} CE", f"Buy {buy:g} CE"],
        entry_filter=bearish_filters(view) + ["Prefer when IV percentile is elevated and resistance is clearly above spot."],
        exit_plan=credit_exit_plan(),
        risk_notes=[
            "Loss can expand quickly if price breaks resistance; keep the hedge leg active.",
            "Do not average a losing short option spread.",
        ],
        score=score_base(view, "Bearish") + (14 if view.iv_percentile >= 55 else 2),
        max_risk_per_lot=estimated_max_loss,
        affordable_lots=max(0, floor(risk_budget / estimated_max_loss)) if estimated_max_loss else None,
    )


def long_call(view: MarketView, risk_budget: float) -> StrategyIdea:
    strike = round_to_step(view.spot, view.strike_step, "up")
    estimated_premium = view.strike_step * (1.2 if view.days_to_expiry <= 3 else 1.8)
    return StrategyIdea(
        name="Long Call",
        bias="Bullish momentum",
        legs=[f"Buy {strike:g} CE"],
        entry_filter=bullish_filters(view) + ["Use only when momentum is strong enough to overcome theta decay."],
        exit_plan=option_buyer_exit_plan(),
        risk_notes=[
            "Option buying can lose 100% of premium.",
            "Avoid far OTM calls near expiry unless you are explicitly trading a high-risk breakout.",
        ],
        score=score_base(view, "Bullish") + (10 if view.iv_percentile < 45 else -4),
        max_risk_per_lot=estimated_premium * view.lot_size,
        affordable_lots=lots_for_budget(risk_budget, estimated_premium, view.lot_size),
    )


def long_put(view: MarketView, risk_budget: float) -> StrategyIdea:
    strike = round_to_step(view.spot, view.strike_step, "down")
    estimated_premium = view.strike_step * (1.2 if view.days_to_expiry <= 3 else 1.8)
    return StrategyIdea(
        name="Long Put",
        bias="Bearish momentum",
        legs=[f"Buy {strike:g} PE"],
        entry_filter=bearish_filters(view) + ["Use only when momentum is strong enough to overcome theta decay."],
        exit_plan=option_buyer_exit_plan(),
        risk_notes=[
            "Option buying can lose 100% of premium.",
            "Avoid far OTM puts near expiry unless you are explicitly trading a high-risk breakdown.",
        ],
        score=score_base(view, "Bearish") + (10 if view.iv_percentile < 45 else -4),
        max_risk_per_lot=estimated_premium * view.lot_size,
        affordable_lots=lots_for_budget(risk_budget, estimated_premium, view.lot_size),
    )


def iron_fly_or_condor(view: MarketView, risk_budget: float) -> StrategyIdea:
    center = round_to_step(view.spot, view.strike_step, "nearest")
    lower_sell = round_to_step(max(view.support, center - view.strike_step), view.strike_step, "down")
    upper_sell = round_to_step(min(view.resistance, center + view.strike_step), view.strike_step, "up")
    lower_buy = lower_sell - 2 * view.strike_step
    upper_buy = upper_sell + 2 * view.strike_step
    width = max(upper_buy - upper_sell, lower_sell - lower_buy)
    estimated_max_loss = width * 0.7 * view.lot_size
    name = "Iron Condor" if upper_sell > center and lower_sell < center else "Iron Fly"
    return StrategyIdea(
        name=name,
        bias="Range-bound, defined-risk income",
        legs=[
            f"Sell {lower_sell:g} PE",
            f"Buy {lower_buy:g} PE",
            f"Sell {upper_sell:g} CE",
            f"Buy {upper_buy:g} CE",
        ],
        entry_filter=[
            "Use only when price is respecting both support and resistance.",
            "Prefer higher IV percentile so collected premium is meaningful.",
            "Avoid fresh entry if the spot is already near either short strike.",
        ],
        exit_plan=credit_exit_plan(),
        risk_notes=[
            "Range trades can fail sharply during trending days.",
            "Keep position size small because adjustments add complexity and cost.",
        ],
        score=60 + (18 if view.iv_percentile >= 55 else 4) + range_quality_score(view),
        max_risk_per_lot=estimated_max_loss,
        affordable_lots=max(0, floor(risk_budget / estimated_max_loss)) if estimated_max_loss else None,
    )


def short_strangle_with_hedges(view: MarketView, risk_budget: float) -> StrategyIdea:
    lower_sell = round_to_step(view.support, view.strike_step, "down")
    upper_sell = round_to_step(view.resistance, view.strike_step, "up")
    lower_buy = lower_sell - 3 * view.strike_step
    upper_buy = upper_sell + 3 * view.strike_step
    width = max(upper_buy - upper_sell, lower_sell - lower_buy)
    estimated_max_loss = width * 0.75 * view.lot_size
    return StrategyIdea(
        name="Hedged Short Strangle",
        bias="Advanced range-bound income",
        legs=[
            f"Sell {lower_sell:g} PE",
            f"Buy {lower_buy:g} PE",
            f"Sell {upper_sell:g} CE",
            f"Buy {upper_buy:g} CE",
        ],
        entry_filter=[
            "Use only after confirming a stable intraday range and elevated IV.",
            "Avoid if either side is close to a breakout or breakdown level.",
        ],
        exit_plan=credit_exit_plan(),
        risk_notes=[
            "This is unsuitable for beginners even with hedges.",
            "Gap moves can hurt both risk and execution quality.",
        ],
        score=58 + (16 if view.iv_percentile >= 65 else 0) + range_quality_score(view),
        max_risk_per_lot=estimated_max_loss,
        affordable_lots=max(0, floor(risk_budget / estimated_max_loss)) if estimated_max_loss else None,
    )


def no_trade_wait(view: MarketView) -> StrategyIdea:
    return StrategyIdea(
        name="Wait / Paper Trade",
        bias="Capital protection",
        legs=["No live position"],
        entry_filter=[
            "Wait for a directional breakout or a clearer range.",
            "Paper trade the setup first if you are new to options.",
        ],
        exit_plan=["Reassess only after price confirms a clean level or volatility changes."],
        risk_notes=["No trade is a valid decision when the edge is unclear."],
        score=72 if view.experience == "Beginner" else 45,
        max_risk_per_lot=0,
        affordable_lots=0,
    )


def bullish_filters(view: MarketView) -> list[str]:
    return [
        f"Spot should hold above support near {view.support:g}.",
        "Prefer entry after a higher high or pullback hold, not after a stretched candle.",
        "PCR above 1 can support bullish bias, but avoid using PCR alone.",
    ]


def bearish_filters(view: MarketView) -> list[str]:
    return [
        f"Spot should stay below resistance near {view.resistance:g}.",
        "Prefer entry after a lower low or failed bounce, not after a panic candle.",
        "PCR below 1 can support bearish bias, but avoid using PCR alone.",
    ]


def standard_exit_plan(view: MarketView, bias: str) -> list[str]:
    invalidation = view.support if bias == "bullish" else view.resistance
    return [
        "Book partial or full profit around 50-70% of maximum potential profit.",
        f"Exit if spot invalidates the key level near {invalidation:g}.",
        "Avoid carrying near-expiry long premium if the move has not started.",
    ]


def credit_exit_plan() -> list[str]:
    return [
        "Take profit after capturing 50-70% of the credit.",
        "Exit or adjust if the short strike is tested with momentum.",
        "Keep a hard maximum loss based on your pre-decided risk budget.",
    ]


def option_buyer_exit_plan() -> list[str]:
    return [
        "Use a premium stop loss, commonly 30-40% of paid premium.",
        "Book partial profit if premium doubles or price reaches the next level.",
        "Do not hold to zero hoping for recovery near expiry.",
    ]


def score_base(view: MarketView, matching_direction: str) -> int:
    score = 50
    if view.direction == matching_direction:
        score += 18
    score += min(16, max(0, view.trend_strength))
    if matching_direction == "Bullish" and view.pcr >= 1:
        score += 4
    if matching_direction == "Bearish" and view.pcr <= 1:
        score += 4
    if view.days_to_expiry <= 1:
        score -= 8
    return max(0, min(100, score))


def range_quality_score(view: MarketView) -> int:
    range_width = max(view.resistance - view.support, 0)
    if not view.spot or range_width <= 0:
        return -10
    distance_to_edge = min(abs(view.spot - view.support), abs(view.resistance - view.spot))
    return 8 if distance_to_edge / range_width > 0.25 else -8


def round_to_step(value: float, step: int, mode: str) -> int:
    if step <= 0:
        return int(round(value))
    if mode == "up":
        return int(ceil(value / step) * step)
    if mode == "down":
        return int(floor(value / step) * step)
    return int(round(value / step) * step)


def lots_for_budget(risk_budget: float, premium_points: float, lot_size: int) -> int:
    risk_per_lot = premium_points * lot_size
    if risk_per_lot <= 0:
        return 0
    return max(0, floor(risk_budget / risk_per_lot))
