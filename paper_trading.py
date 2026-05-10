from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from auto_analysis import AutoAnalysis


@dataclass
class PaperTrade:
    id: str
    created_at: str
    symbol: str
    contract: str
    side: str
    entry_price: float
    current_price: float
    quantity: int
    stop_loss: float
    target: float
    status: str
    pnl: float
    signal_strength: int
    note: str


def create_trade(analysis: AutoAnalysis) -> dict[str, Any] | None:
    contract = analysis.contract
    if not contract or contract.ltp <= 0:
        return None
    quantity = max(1, analysis.view.lot_size)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade = PaperTrade(
        id=f"{analysis.view.symbol}-{contract.strike:g}-{contract.option_type}-{datetime.now().strftime('%H%M%S')}",
        created_at=now,
        symbol=analysis.view.symbol,
        contract=f"{contract.strike:g} {contract.option_type}",
        side=contract.action,
        entry_price=contract.ltp,
        current_price=contract.ltp,
        quantity=quantity,
        stop_loss=contract.stop_loss,
        target=contract.target,
        status="Open",
        pnl=0.0,
        signal_strength=analysis.signal_strength,
        note=analysis.summary,
    )
    return asdict(trade)


def update_trades(trades: list[dict[str, Any]], analysis: AutoAnalysis | None) -> list[dict[str, Any]]:
    if analysis is None:
        return trades
    scanner_lookup = {
        f"{item.strike:g} {item.option_type}": item
        for item in analysis.scanner
    }
    updated: list[dict[str, Any]] = []
    for trade in trades:
        copied = dict(trade)
        if copied.get("status") not in {"Open"}:
            updated.append(copied)
            continue
        live = scanner_lookup.get(str(copied.get("contract")))
        if live and live.ltp > 0:
            copied["current_price"] = live.ltp
        entry = float(copied.get("entry_price") or 0)
        current = float(copied.get("current_price") or 0)
        quantity = int(copied.get("quantity") or 1)
        copied["pnl"] = round((current - entry) * quantity, 2)
        if current >= float(copied.get("target") or 0):
            copied["status"] = "Target Hit"
        elif current <= float(copied.get("stop_loss") or 0):
            copied["status"] = "Stop Hit"
        updated.append(copied)
    return updated


def close_trade(trade: dict[str, Any]) -> dict[str, Any]:
    copied = dict(trade)
    if copied.get("status") == "Open":
        copied["status"] = "Exited"
    return copied
