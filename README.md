# India Options Strategy Assistant

A Streamlit app that generates rule-based options strategy ideas for Indian market underlyings such as NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, and stock options.

## What it does

- Runs from Streamlit secrets without asking for Angel or Gemini keys in the app UI
- Lets the user select NIFTY, BANKNIFTY, SENSEX, FINNIFTY, or MIDCPNIFTY from the main dashboard
- Connects to Angel One SmartAPI automatically and requires live data before analysis is shown
- Fetches live index spot from Angel index tokens before scanning option contracts
- Can fetch NSE option-chain data on demand for index and stock options in code, but the production UI uses Angel
- Can consume a custom broker/vendor JSON endpoint for more reliable live data
- Auto-fills spot, PCR, support from highest PE OI, and resistance from highest CE OI
- Shows option-chain rows near spot for the selected expiry
- Highlights ATM, support, and resistance zones in the option-chain table
- Suggests defined-risk options ideas such as bull call spreads, bear put spreads, bull put spreads, bear call spreads, iron condors, and hedged short strangles
- Estimates a modelled risk per lot and lot count based on the user's risk budget
- Builds live premium-based payoff charts when matching option quotes are available
- Shows breakeven, net premium, max profit, and max loss estimates from live option LTP
- Adds an optional Gemini AI brief for cautious market commentary and risk review
- Auto-derives market view, trend strength, risk percentage, support, resistance, and option contract selection from live data
- Shows recent Angel historical candles with the latest buy-call, buy-put, or wait marker
- Uses manual live refresh to avoid Streamlit's full-page auto-refresh grey overlay
- Ranks nearby CE/PE contracts by liquidity, strike distance, IV quality, and available premium
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

Optional Gemini variables:

```powershell
$env:GEMINI_API_KEY="your_gemini_api_key"
$env:GEMINI_MODEL="gemini-2.5-flash"
streamlit run app.py
```

On Streamlit Cloud, add broker and Gemini keys under **App settings -> Secrets**:

```toml
ANGEL_API_KEY = "your_api_key"
ANGEL_CLIENT_CODE = "your_client_code"
ANGEL_PIN = "your_pin"
ANGEL_TOTP_SECRET = "your_totp_secret"
GEMINI_API_KEY = "your_gemini_api_key"
GEMINI_MODEL = "gemini-2.5-flash"
APP_CAPITAL = "100000"
APP_EXPERIENCE = "Intermediate"
APP_CANDLE_INTERVAL = "FIFTEEN_MINUTE"
APP_HISTORY_DAYS = "5"
```

Optional per-index overrides:

```toml
NIFTY_LOT_SIZE = "75"
BANKNIFTY_LOT_SIZE = "30"
SENSEX_LOT_SIZE = "10"
NIFTY_STRIKE_STEP = "50"
BANKNIFTY_STRIKE_STEP = "100"
SENSEX_STRIKE_STEP = "100"
```

## Files

- `app.py`: Streamlit user interface
- `market_data.py`: NSE option-chain fetch and parsing helpers
- `options_suggestion.py`: strategy and risk engine
- `auto_analysis.py`: automatic indicator, risk, signal, and contract-selection engine
- `payoff.py`: option-leg parsing and expiry payoff calculations
- `gemini_advisor.py`: Gemini market brief integration
- `requirements.txt`: Python dependencies

## Notes

- The app auto-connects to Angel One when secrets are configured.
- The app does not place orders.
- Default lot sizes and strike intervals can be overridden with Streamlit secrets because exchange rules and contract specifications can change.
- Streamlit full-page auto-refresh was removed because it greys out the UI during reruns. True tick streaming should be implemented as a separate Angel WebSocket service.
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
