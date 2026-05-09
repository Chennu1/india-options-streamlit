# India Options Strategy Assistant

A Streamlit app that generates rule-based options strategy ideas for Indian market underlyings such as NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, and stock options.

## What it does

- Takes spot price, support, resistance, PCR, IV percentile, expiry, capital, risk percentage, strike interval, and lot size
- Can fetch NSE option-chain data on demand for index and stock options
- Can consume a custom broker/vendor JSON endpoint for more reliable live data
- Auto-fills spot, PCR, support from highest PE OI, and resistance from highest CE OI
- Shows option-chain rows near spot for the selected expiry
- Suggests defined-risk options ideas such as bull call spreads, bear put spreads, bull put spreads, bear call spreads, iron condors, and hedged short strangles
- Estimates a modelled risk per lot and lot count based on the user's risk budget
- Shows entry filters, exit rules, and risk notes for each setup
- Adds beginner guardrails and avoids naked short option suggestions

## Important disclaimer

This app is for education and trade planning only. It is not investment advice, a buy/sell recommendation, or a replacement for a SEBI-registered investment adviser. Always verify live NSE data, broker margin, liquidity, bid-ask spread, lot size, expiry rules, and transaction costs before placing any trade.

NSE website polling is not the same as an official low-latency real-time feed. Production-grade real-time data should come from a licensed NSE data feed, authorized market-data vendor, or broker API.

## Tech stack

- `Frontend`: Streamlit
- `Backend`: Python
- `Logic`: Local rule-based strategy engine

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
streamlit run app.py
```

Optional Angel One credential variables:

```powershell
$env:ANGEL_API_KEY="your_api_key"
$env:ANGEL_CLIENT_CODE="your_client_code"
$env:ANGEL_PIN="your_pin"
$env:ANGEL_TOTP_SECRET="your_totp_secret"
streamlit run app.py
```

Do not commit real broker credentials to project files.

## Files

- `app.py`: Streamlit user interface
- `market_data.py`: NSE option-chain fetch and parsing helpers
- `options_suggestion.py`: strategy and risk engine
- `requirements.txt`: Python dependencies

## Notes

- The app fetches option-chain data only when you enable live mode and press refresh.
- The app does not place orders.
- Default lot sizes and strike intervals are editable because exchange rules and contract specifications can change.
- The older static Snake prototype files are still present in the repo and were left untouched.

## Custom live-data JSON shape

If you use a broker or data vendor, expose/enter a JSON endpoint like this:

```json
{
  "symbol": "NIFTY",
  "spot": 24350.25,
  "timestamp": "2026-05-09 15:29:30",
  "expiry": "14-May-2026",
  "pcr": 1.08,
  "support": 24200,
  "resistance": 24500,
  "avg_iv": 13.5,
  "rows": [
    {
      "strike": 24350,
      "ce": {"ltp": 120.5, "oi": 120000, "iv": 12.8},
      "pe": {"ltp": 98.2, "oi": 150000, "iv": 13.1}
    }
  ]
}
```
