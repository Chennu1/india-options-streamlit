from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

import requests


NSE_HOME = "https://www.nseindia.com"
ANGEL_SCRIP_MASTER = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
ANGEL_INDEX_EXCHANGES = {"NIFTY": "NFO", "BANKNIFTY": "NFO", "FINNIFTY": "NFO", "MIDCPNIFTY": "NFO", "SENSEX": "BFO"}


@dataclass
class OptionChainSnapshot:
    symbol: str
    spot: float
    timestamp: str
    expiries: list[str]
    selected_expiry: str
    pcr: float
    support: float
    resistance: float
    avg_iv: float
    rows: list[dict[str, Any]]
    source: str


class MarketDataError(RuntimeError):
    pass


@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_option_chain(symbol: str, expiry: str | None = None) -> OptionChainSnapshot:
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise MarketDataError("Enter a valid NSE symbol.")

    endpoint = (
        f"{NSE_HOME}/api/option-chain-indices?symbol={clean_symbol}"
        if clean_symbol in INDEX_SYMBOLS
        else f"{NSE_HOME}/api/option-chain-equities?symbol={clean_symbol}"
    )

    session = requests.Session()
    headers = {
        "accept": "application/json,text/plain,*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": f"{NSE_HOME}/option-chain",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
    }

    try:
        session.get(NSE_HOME, headers=headers, timeout=10)
        response = session.get(endpoint, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise MarketDataError(f"NSE request failed: {exc}") from exc
    except ValueError as exc:
        raise MarketDataError("NSE returned a non-JSON response. Try refresh again.") from exc

    records = payload.get("records", {})
    expiries = [str(item) for item in records.get("expiryDates", [])]
    if not expiries:
        raise MarketDataError(
            "NSE returned an empty option-chain payload. This usually means the website "
            "API blocked server-side polling. Use a licensed broker/vendor data URL for "
            "reliable real-time data."
        )

    selected_expiry = expiry if expiry in expiries else expiries[0]
    rows = [row for row in records.get("data", []) if row.get("expiryDate") == selected_expiry]
    if not rows:
        raise MarketDataError(f"No option-chain rows found for expiry {selected_expiry}.")

    spot = float(records.get("underlyingValue") or 0)
    timestamp = str(records.get("timestamp") or datetime.now().strftime("%d-%b-%Y %H:%M:%S"))
    pcr = calculate_pcr(rows)
    support = highest_oi_strike(rows, "PE", fallback=spot)
    resistance = highest_oi_strike(rows, "CE", fallback=spot)
    avg_iv = calculate_avg_iv(rows)

    return OptionChainSnapshot(
        symbol=clean_symbol,
        spot=spot,
        timestamp=timestamp,
        expiries=expiries,
        selected_expiry=selected_expiry,
        pcr=pcr,
        support=support,
        resistance=resistance,
        avg_iv=avg_iv,
        rows=rows,
        source="NSE option-chain endpoint",
    )


def calculate_pcr(rows: list[dict[str, Any]]) -> float:
    put_oi = sum(option_value(row.get("PE"), "openInterest") for row in rows)
    call_oi = sum(option_value(row.get("CE"), "openInterest") for row in rows)
    if call_oi <= 0:
        return 1.0
    return round(put_oi / call_oi, 2)


def highest_oi_strike(rows: list[dict[str, Any]], side: str, fallback: float) -> float:
    candidates = [
        (option_value(row.get(side), "openInterest"), float(row.get("strikePrice") or 0))
        for row in rows
        if row.get(side)
    ]
    candidates = [(oi, strike) for oi, strike in candidates if oi > 0 and strike > 0]
    if not candidates:
        return fallback
    return max(candidates, key=lambda item: item[0])[1]


def calculate_avg_iv(rows: list[dict[str, Any]]) -> float:
    ivs: list[float] = []
    for row in rows:
        for side in ("CE", "PE"):
            iv = option_value(row.get(side), "impliedVolatility")
            if iv > 0:
                ivs.append(iv)
    return round(mean(ivs), 2) if ivs else 0.0


def option_value(option: dict[str, Any] | None, key: str) -> float:
    if not option:
        return 0.0
    value = option.get(key, 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def rows_near_spot(snapshot: OptionChainSnapshot, width: int = 8) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        snapshot.rows,
        key=lambda row: abs(float(row.get("strikePrice") or 0) - snapshot.spot),
    )
    return sorted(sorted_rows[:width], key=lambda row: float(row.get("strikePrice") or 0))


def fetch_custom_snapshot(url: str, bearer_token: str = "") -> OptionChainSnapshot:
    headers = {"accept": "application/json"}
    if bearer_token.strip():
        headers["authorization"] = f"Bearer {bearer_token.strip()}"

    try:
        response = requests.get(url.strip(), headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise MarketDataError(f"Custom data request failed: {exc}") from exc
    except ValueError as exc:
        raise MarketDataError("Custom data URL did not return valid JSON.") from exc

    return snapshot_from_custom_payload(payload)


def fetch_angel_snapshot(
    api_key: str,
    client_code: str,
    password: str,
    totp_or_secret: str,
    symbol: str,
    spot_hint: float,
    strike_step: int,
    expiry: str | None = None,
    strikes_each_side: int = 5,
) -> OptionChainSnapshot:
    try:
        import pyotp
        from SmartApi import SmartConnect
    except ImportError as exc:
        raise MarketDataError(
            "Angel provider needs smartapi-python and pyotp. Run: "
            "pip install smartapi-python pyotp logzero websocket-client pycryptodome"
        ) from exc

    api_key = api_key.strip()
    client_code = client_code.strip()
    password = password.strip()
    clean_symbol = symbol.strip().upper()
    if not all([api_key, client_code, password, totp_or_secret.strip(), clean_symbol]):
        raise MarketDataError("Enter Angel API key, client code, PIN/password, TOTP/secret, and symbol.")

    totp_value = totp_or_secret.strip()
    if not totp_value.isdigit() or len(totp_value) != 6:
        try:
            totp_value = pyotp.TOTP(totp_value).now()
        except Exception as exc:
            raise MarketDataError("Angel TOTP value/secret is invalid.") from exc

    smart_api = SmartConnect(api_key=api_key)
    session = smart_api.generateSession(client_code, password, totp_value)
    if not session or session.get("status") is False:
        raise MarketDataError(f"Angel login failed: {session}")

    instruments = fetch_angel_instruments()
    live_spot = fetch_angel_index_spot(smart_api, instruments, clean_symbol, spot_hint)
    option_rows = filter_angel_options(instruments, clean_symbol, live_spot, strike_step, expiry, strikes_each_side)
    if not option_rows:
        raise MarketDataError("No Angel option tokens found. Check symbol, expiry, and strike range.")

    exchange_tokens: dict[str, list[str]] = {}
    for row in option_rows:
        exchange_tokens.setdefault(str(row.get("exch_seg", "NFO")), []).append(row["token"])
    quotes = smart_api.getMarketData("FULL", exchange_tokens)
    if not quotes or quotes.get("status") is False:
        raise MarketDataError(f"Angel market data failed: {quotes}")

    fetched = (quotes.get("data") or {}).get("fetched") or []
    quote_by_token = {str(item.get("symbolToken") or item.get("symboltoken") or item.get("token")): item for item in fetched}
    normalized_rows = build_rows_from_angel_options(option_rows, quote_by_token)
    expiries = sorted({row.get("expiry", "") for row in instruments if is_angel_option(row, clean_symbol)})
    selected_expiry = expiry or (option_rows[0].get("expiry") if option_rows else "")

    return OptionChainSnapshot(
        symbol=clean_symbol,
        spot=live_spot,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        expiries=expiries,
        selected_expiry=selected_expiry,
        pcr=calculate_pcr(normalized_rows),
        support=highest_oi_strike(normalized_rows, "PE", live_spot),
        resistance=highest_oi_strike(normalized_rows, "CE", live_spot),
        avg_iv=calculate_avg_iv(normalized_rows),
        rows=normalized_rows,
        source="Angel One SmartAPI quotes",
    )


def fetch_angel_historical_candles(
    api_key: str,
    client_code: str,
    password: str,
    totp_or_secret: str,
    symbol: str,
    interval: str = "FIFTEEN_MINUTE",
    days: int = 5,
) -> list[Candle]:
    try:
        import pyotp
        from SmartApi import SmartConnect
    except ImportError as exc:
        raise MarketDataError(
            "Angel historical candles need smartapi-python and pyotp."
        ) from exc

    clean_symbol = symbol.strip().upper()
    totp_value = totp_or_secret.strip()
    if not totp_value.isdigit() or len(totp_value) != 6:
        try:
            totp_value = pyotp.TOTP(totp_value).now()
        except Exception as exc:
            raise MarketDataError("Angel TOTP value/secret is invalid.") from exc

    smart_api = SmartConnect(api_key=api_key.strip())
    session = smart_api.generateSession(client_code.strip(), password.strip(), totp_value)
    if not session or session.get("status") is False:
        raise MarketDataError(f"Angel login failed: {session}")

    instruments = fetch_angel_instruments()
    index_row = find_angel_index_row(instruments, clean_symbol)
    if not index_row:
        raise MarketDataError(f"No Angel index token found for {clean_symbol}.")

    to_time = datetime.now()
    from_time = to_time - timedelta(days=days)
    params = {
        "exchange": str(index_row.get("exch_seg", "NSE")),
        "symboltoken": str(index_row.get("token", "")),
        "interval": interval,
        "fromdate": from_time.strftime("%Y-%m-%d %H:%M"),
        "todate": to_time.strftime("%Y-%m-%d %H:%M"),
    }
    response = smart_api.getCandleData(params)
    if not response or response.get("status") is False:
        raise MarketDataError(f"Angel candle data failed: {response}")
    rows = response.get("data") or []
    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        candles.append(
            Candle(
                timestamp=str(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5] or 0),
            )
        )
    return candles


def snapshot_from_custom_payload(payload: dict[str, Any]) -> OptionChainSnapshot:
    rows = payload.get("rows") or payload.get("option_chain") or []
    expiries = payload.get("expiries") or []
    selected_expiry = str(payload.get("selected_expiry") or payload.get("expiry") or (expiries[0] if expiries else ""))
    symbol = str(payload.get("symbol") or "CUSTOM").upper()
    spot = float(payload.get("spot") or payload.get("underlyingValue") or 0)
    timestamp = str(payload.get("timestamp") or datetime.now().strftime("%d-%b-%Y %H:%M:%S"))

    if not isinstance(rows, list):
        raise MarketDataError("Custom data JSON must include rows as a list.")

    normalized_rows = [normalize_custom_row(row) for row in rows if isinstance(row, dict)]
    if not normalized_rows:
        normalized_rows = [
            {
                "strikePrice": spot,
                "CE": {"lastPrice": 0, "openInterest": 0, "impliedVolatility": 0},
                "PE": {"lastPrice": 0, "openInterest": 0, "impliedVolatility": 0},
            }
        ]

    return OptionChainSnapshot(
        symbol=symbol,
        spot=spot,
        timestamp=timestamp,
        expiries=[str(item) for item in expiries] or ([selected_expiry] if selected_expiry else []),
        selected_expiry=selected_expiry,
        pcr=float(payload.get("pcr") or calculate_pcr(normalized_rows)),
        support=float(payload.get("support") or highest_oi_strike(normalized_rows, "PE", spot)),
        resistance=float(payload.get("resistance") or highest_oi_strike(normalized_rows, "CE", spot)),
        avg_iv=float(payload.get("avg_iv") or calculate_avg_iv(normalized_rows)),
        rows=normalized_rows,
        source=str(payload.get("source") or "Custom JSON data provider"),
    )


def fetch_angel_instruments() -> list[dict[str, Any]]:
    try:
        response = requests.get(ANGEL_SCRIP_MASTER, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise MarketDataError(f"Angel scrip master request failed: {exc}") from exc
    except ValueError as exc:
        raise MarketDataError("Angel scrip master did not return valid JSON.") from exc
    if not isinstance(payload, list):
        raise MarketDataError("Angel scrip master format changed.")
    return payload


def fetch_angel_index_spot(
    smart_api: Any,
    instruments: list[dict[str, Any]],
    symbol: str,
    fallback: float,
) -> float:
    index_row = find_angel_index_row(instruments, symbol)
    if not index_row:
        return fallback
    exchange = str(index_row.get("exch_seg", "NSE"))
    token = str(index_row.get("token", "")).strip()
    if not token:
        return fallback
    try:
        response = smart_api.getMarketData("LTP", {exchange: [token]})
    except Exception:
        return fallback
    if not response or response.get("status") is False:
        return fallback
    fetched = (response.get("data") or {}).get("fetched") or []
    if not fetched:
        return fallback
    return first_present(fetched[0], ["ltp", "lastPrice", "lastTradedPrice"]) or fallback


def find_angel_index_row(instruments: list[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    preferred_exchange = "BSE" if symbol == "SENSEX" else "NSE"
    for row in instruments:
        name = str(row.get("name", "")).upper()
        instrument_type = str(row.get("instrumenttype", "")).upper()
        exchange = str(row.get("exch_seg", "")).upper()
        if name == symbol and instrument_type == "AMXIDX" and exchange == preferred_exchange:
            return row
    for row in instruments:
        if str(row.get("symbol", "")).upper() == symbol and str(row.get("exch_seg", "")).upper() == preferred_exchange:
            return row
    return None


def filter_angel_options(
    instruments: list[dict[str, Any]],
    symbol: str,
    spot_hint: float,
    strike_step: int,
    expiry: str | None,
    strikes_each_side: int,
) -> list[dict[str, Any]]:
    options = [row for row in instruments if is_angel_option(row, symbol)]
    expiries = sorted({row.get("expiry", "") for row in options if row.get("expiry")})
    selected_expiry = expiry if expiry in expiries else (expiries[0] if expiries else None)
    if selected_expiry:
        options = [row for row in options if row.get("expiry") == selected_expiry]

    atm = round_to_step(spot_hint, strike_step)
    low = atm - strikes_each_side * strike_step
    high = atm + strikes_each_side * strike_step
    result = []
    for row in options:
        strike = parse_angel_strike(row.get("strike"))
        if low <= strike <= high:
            copied = dict(row)
            copied["parsed_strike"] = strike
            result.append(copied)
    return result


def is_angel_option(row: dict[str, Any], symbol: str) -> bool:
    exch = str(row.get("exch_seg", "")).upper()
    instrument_type = str(row.get("instrumenttype", "")).upper()
    name = str(row.get("name", "")).upper()
    token = str(row.get("token", "")).strip()
    expected_exchange = ANGEL_INDEX_EXCHANGES.get(symbol)
    exchange_ok = exch == expected_exchange if expected_exchange else exch in {"NFO", "BFO"}
    return exchange_ok and instrument_type in {"OPTIDX", "OPTSTK"} and name == symbol and bool(token)


def parse_angel_strike(value: Any) -> float:
    try:
        strike = float(value)
    except (TypeError, ValueError):
        return 0.0
    return strike / 100 if strike > 100000 else strike


def build_rows_from_angel_options(
    option_rows: list[dict[str, Any]],
    quote_by_token: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_strike: dict[float, dict[str, Any]] = {}
    for option in option_rows:
        strike = float(option.get("parsed_strike") or parse_angel_strike(option.get("strike")))
        symbol = str(option.get("symbol", "")).upper()
        side = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else ""
        if not side:
            continue
        quote = quote_by_token.get(str(option.get("token"))) or {}
        row = by_strike.setdefault(strike, {"strikePrice": strike, "CE": {}, "PE": {}})
        row[side] = {
            "lastPrice": first_present(quote, ["ltp", "lastPrice", "lastTradedPrice"]),
            "openInterest": first_present(quote, ["opnInterest", "openInterest", "oi"]),
            "impliedVolatility": first_present(quote, ["impliedVolatility", "iv"]),
        }
    return [by_strike[key] for key in sorted(by_strike)]


def first_present(values: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        if key in values and values[key] not in {None, ""}:
            return option_value(values, key)
    return 0.0


def round_to_step(value: float, step: int) -> int:
    if step <= 0:
        return int(round(value))
    return int(round(value / step) * step)


def normalize_custom_row(row: dict[str, Any]) -> dict[str, Any]:
    strike = row.get("strikePrice") or row.get("strike") or row.get("sp") or 0
    ce = row.get("CE") or row.get("ce") or {}
    pe = row.get("PE") or row.get("pe") or {}
    return {
        "strikePrice": strike,
        "CE": normalize_option_side(ce),
        "PE": normalize_option_side(pe),
    }


def normalize_option_side(side: dict[str, Any]) -> dict[str, Any]:
    return {
        "lastPrice": side.get("lastPrice") or side.get("ltp") or side.get("last_price") or 0,
        "openInterest": side.get("openInterest") or side.get("oi") or side.get("open_interest") or 0,
        "impliedVolatility": side.get("impliedVolatility") or side.get("iv") or side.get("implied_volatility") or 0,
    }
