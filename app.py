from __future__ import annotations

import os
import textwrap

import altair as alt
import pandas as pd
import streamlit as st

from auto_analysis import AutoAnalysis, append_snapshot_history, build_auto_analysis
from gemini_advisor import GeminiAdvisorError, GeminiBrief, generate_gemini_brief
from market_data import (
    MarketDataError,
    fetch_angel_snapshot,
    fetch_custom_snapshot,
    fetch_option_chain,
    rows_near_spot,
)
from options_suggestion import INDEX_DEFAULTS, MarketView, StrategyIdea, generate_suggestions
from payoff import PayoffResult, build_payoff


st.set_page_config(
    page_title="India Options Strategy Assistant",
    page_icon="O",
    layout="wide",
)


def main() -> None:
    inject_css()
    render_header()
    analysis = render_sidebar()

    suggestions = generate_suggestions(analysis.view)
    render_dashboard(analysis, suggestions)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --page: #f4f7f6;
          --ink: #17201d;
          --ink-soft: #4e5c57;
          --muted: #71817b;
          --panel: #ffffff;
          --line: #dce5e1;
          --line-dark: #283531;
          --terminal: #101816;
          --terminal-2: #17211e;
          --accent: #008f7a;
          --accent-soft: #dff5ef;
          --amber: #b7791f;
          --amber-soft: #fff4d8;
          --red: #c24141;
          --red-soft: #ffe4e4;
          --shadow: 0 14px 34px rgba(23, 32, 29, 0.08);
        }
        .stApp {
          background: linear-gradient(180deg, #eef4f2 0, var(--page) 260px), var(--page);
        }
        .main .block-container {
          max-width: 1480px;
          padding: 1rem 2rem 3rem;
        }
        .hero {
          border: 1px solid var(--line-dark);
          background:
            linear-gradient(135deg, rgba(0, 143, 122, 0.18), transparent 36%),
            linear-gradient(120deg, var(--terminal), var(--terminal-2));
          border-radius: 8px;
          padding: 22px 24px 18px;
          margin-bottom: 12px;
          box-shadow: var(--shadow);
          color: #f7fbfa;
        }
        .hero h1 {
          margin: 0;
          font-size: 2.25rem;
          letter-spacing: 0;
          line-height: 1.05;
        }
        .hero p {
          margin: 8px 0 0;
          color: #b8c8c3;
          max-width: 78ch;
        }
        .hero-topline {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: start;
        }
        .terminal-badge {
          display: inline-flex;
          padding: 6px 10px;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.14);
          color: #d8e8e4;
          font-weight: 700;
          font-size: 0.78rem;
          white-space: nowrap;
        }
        .hero-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 10px;
          margin-top: 18px;
        }
        .hero-kpi {
          border: 1px solid rgba(255, 255, 255, 0.12);
          background: rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 10px 12px;
        }
        .hero-kpi span {
          display: block;
          color: #90a49e;
          font-size: 0.72rem;
          text-transform: uppercase;
          margin-bottom: 3px;
        }
        .hero-kpi strong {
          color: #ffffff;
          font-size: 0.98rem;
        }
        .notice-grid {
          display: grid;
          grid-template-columns: 1.15fr 1fr 0.95fr;
          gap: 10px;
          margin-bottom: 16px;
        }
        .notice {
          border-radius: 8px;
          padding: 10px 12px;
          border: 1px solid var(--line);
          background: var(--panel);
          color: var(--ink-soft);
          font-size: 0.88rem;
        }
        .notice strong {
          display: block;
          color: var(--ink);
          margin-bottom: 2px;
          font-size: 0.82rem;
          text-transform: uppercase;
        }
        .notice.risk {
          background: var(--amber-soft);
          border-color: #f0dca3;
        }
        .notice.live {
          background: var(--accent-soft);
          border-color: #bde8dd;
        }
        .status-strip {
          display: grid;
          grid-template-columns: 1fr 1.25fr 1fr 1fr 1.35fr 1.2fr;
          gap: 10px;
          margin: 12px 0 10px;
        }
        .status-cell {
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 12px 14px;
          background: var(--panel);
          box-shadow: 0 8px 22px rgba(23, 32, 29, 0.04);
        }
        .status-label {
          color: var(--muted);
          font-size: 0.78rem;
          text-transform: uppercase;
          margin-bottom: 4px;
        }
        .status-value {
          font-size: 1.15rem;
          font-weight: 700;
          color: var(--ink);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .status-value.accent {
          color: var(--accent);
        }
        .section-title {
          display: flex;
          align-items: end;
          justify-content: space-between;
          gap: 16px;
          margin: 20px 0 10px;
        }
        .section-title h3 {
          margin: 0;
          font-size: 1.05rem;
          color: var(--ink);
        }
        .section-title span {
          color: var(--muted);
          font-size: 0.85rem;
        }
        .signal-card {
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 16px;
          background: var(--panel);
          min-height: 100%;
          box-shadow: 0 10px 24px rgba(23, 32, 29, 0.05);
          margin-bottom: 8px;
        }
        .signal-title {
          font-size: 1.08rem;
          font-weight: 800;
          margin-bottom: 2px;
          color: var(--ink);
        }
        .signal-bias {
          color: var(--muted);
          font-size: 0.9rem;
          margin-bottom: 10px;
        }
        .score {
          display: inline-block;
          padding: 3px 8px;
          border-radius: 999px;
          background: var(--accent-soft);
          color: var(--accent);
          font-weight: 700;
          font-size: 0.86rem;
        }
        .risk-pill {
          display: inline-block;
          padding: 3px 8px;
          border-radius: 999px;
          background: var(--amber-soft);
          color: var(--amber);
          font-weight: 700;
          font-size: 0.86rem;
          margin-left: 6px;
        }
        .leg-list {
          margin: 10px 0 0;
          padding-left: 18px;
          color: var(--ink-soft);
        }
        .small-note {
          color: var(--muted);
          font-size: 0.86rem;
          margin-top: 10px;
        }
        .best-shell,
        .payoff-shell,
        .ai-brief-card {
          border: 1px solid var(--line);
          background: var(--panel);
          border-radius: 8px;
          padding: 14px;
          box-shadow: var(--shadow);
        }
        .payoff-shell {
          border-color: #bde8dd;
          background: linear-gradient(180deg, #ffffff, #f4fffb);
        }
        .quality-badge {
          display: inline-block;
          padding: 5px 10px;
          border-radius: 999px;
          font-weight: 800;
          color: var(--accent);
          background: var(--accent-soft);
          margin-bottom: 8px;
        }
        div[data-testid="stSidebar"] {
          border-right: 1px solid var(--line-dark);
          background: #121b18;
        }
        div[data-testid="stSidebar"] * {
          color: #e8f0ed;
        }
        div[data-testid="stSidebar"] label,
        div[data-testid="stSidebar"] p,
        div[data-testid="stSidebar"] span {
          color: #d1dfda;
        }
        div[data-testid="stSidebar"] [data-testid="stExpander"] {
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.04);
        }
        div[data-testid="stSidebar"] input,
        div[data-testid="stSidebar"] textarea,
        div[data-testid="stSidebar"] div[data-baseweb="select"] > div {
          background: #0d1412;
          border-color: rgba(255, 255, 255, 0.16);
        }
        div[data-testid="stTabs"] button {
          font-weight: 800;
        }
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
          gap: 6px;
        }
        div[data-testid="stTabs"] [data-baseweb="tab"] {
          border: 1px solid var(--line);
          border-radius: 8px 8px 0 0;
          background: #ffffff;
          padding: 8px 16px;
        }
        div[data-testid="stMetric"] {
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 12px;
          background: var(--panel);
          box-shadow: 0 8px 20px rgba(23, 32, 29, 0.04);
        }
        div[data-testid="stMetricValue"] {
          color: var(--ink);
          font-size: 1.35rem;
        }
        div[data-testid="stDataFrame"] {
          border: 1px solid var(--line);
          border-radius: 8px;
          overflow: hidden;
          box-shadow: 0 8px 20px rgba(23, 32, 29, 0.04);
        }
        div[data-testid="stAlert"] {
          border-radius: 8px;
        }
        @media (max-width: 900px) {
          .hero-topline { display: block; }
          .terminal-badge { margin-top: 12px; }
          .hero-grid,
          .notice-grid,
          .status-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 560px) {
          .hero-grid,
          .notice-grid,
          .status-strip { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="hero-topline">
            <div>
              <h1>India Options Strategy Desk</h1>
              <p>Live-data aware options planning for NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, and stock options.</p>
            </div>
            <div class="terminal-badge">Gemini 2.5 Flash Ready</div>
          </div>
          <div class="hero-grid">
            <div class="hero-kpi"><span>Data providers</span><strong>Angel, NSE, Custom</strong></div>
            <div class="hero-kpi"><span>Analytics</span><strong>Payoff + Breakeven</strong></div>
            <div class="hero-kpi"><span>Strategies</span><strong>Defined Risk First</strong></div>
            <div class="hero-kpi"><span>Deployment</span><strong>Streamlit Cloud</strong></div>
          </div>
        </div>
        <div class="notice-grid">
          <div class="notice risk">
            <strong>Risk disclosure</strong>
            Educational tool only. Not investment advice or a buy/sell recommendation.
          </div>
          <div class="notice live">
            <strong>Live data</strong>
            Broker/vendor feeds are preferred. NSE website polling is best-effort.
          </div>
          <div class="notice">
            <strong>Market reference</strong>
            When closed, use the latest close as the reference spot.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> AutoAnalysis:
    with st.sidebar:
        st.header("Control Panel")
        symbol = st.selectbox("Underlying", list(INDEX_DEFAULTS.keys()))
        defaults = INDEX_DEFAULTS[symbol]

        with st.expander("Live Data Provider", expanded=True):
            use_live_data = st.toggle("Fetch live option data", value=False)
            data_provider = st.selectbox(
                "Provider",
                ["Angel One SmartAPI", "NSE website polling", "Custom broker/vendor JSON"],
            )
            live_symbol = st.text_input("NSE symbol", value=symbol if symbol != "STOCK OPTION" else "RELIANCE")
            custom_url = ""
            custom_token = ""
            angel_api_key = ""
            angel_client_code = ""
            angel_password = ""
            angel_totp = ""
            if data_provider == "Custom broker/vendor JSON":
                custom_url = st.text_input("JSON endpoint URL", placeholder="https://your-data-provider/option-chain")
                custom_token = st.text_input("Bearer token", type="password")
            elif data_provider == "Angel One SmartAPI":
                st.caption("Credentials are used for this session only. They are not written to project files.")
                angel_api_key = st.text_input(
                    "Angel API key",
                    value=os.getenv("ANGEL_API_KEY", ""),
                    type="password",
                )
                angel_client_code = st.text_input(
                    "Angel client code",
                    value=os.getenv("ANGEL_CLIENT_CODE", ""),
                )
                angel_password = st.text_input(
                    "Angel PIN / password",
                    value=os.getenv("ANGEL_PIN", ""),
                    type="password",
                )
                angel_totp = st.text_input(
                    "6-digit TOTP or TOTP secret",
                    value=os.getenv("ANGEL_TOTP_SECRET", ""),
                    type="password",
                )
                if all([angel_api_key, angel_client_code, angel_password, angel_totp]):
                    st.caption("Angel credentials are ready for refresh.")
        expiry_choice = None
        snapshot = st.session_state.get("snapshot")
        reference_spot = float(snapshot.spot) if snapshot else 24176.15

        if use_live_data:
            col_a, col_b = st.columns(2)
            credentials_ready = (
                data_provider != "Angel One SmartAPI"
                or all([angel_api_key, angel_client_code, angel_password, angel_totp])
            )
            fetch_clicked = col_a.button(
                "Refresh",
                use_container_width=True,
                disabled=not credentials_ready,
            )
            clear_clicked = col_b.button("Manual", use_container_width=True)
            if data_provider == "Angel One SmartAPI" and not credentials_ready:
                st.caption("Enter all Angel fields to enable Refresh.")
            if clear_clicked:
                st.session_state.pop("snapshot", None)
                st.session_state.pop("snapshot_symbol", None)
            if fetch_clicked:
                with st.spinner(f"Fetching {data_provider} data..."):
                    try:
                        snapshot = fetch_live_snapshot(
                            provider=data_provider,
                            symbol=live_symbol,
                            custom_url=custom_url,
                            custom_token=custom_token,
                            angel_api_key=angel_api_key,
                            angel_client_code=angel_client_code,
                            angel_password=angel_password,
                            angel_totp=angel_totp,
                            spot_hint=reference_spot,
                            strike_step=int(defaults["strike_step"]),
                        )
                        st.session_state["snapshot"] = snapshot
                        st.session_state["snapshot_symbol"] = live_symbol.upper()
                    except MarketDataError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"{data_provider} failed: {exc}")
            snapshot = st.session_state.get("snapshot")

            if snapshot:
                expiry_choice = st.selectbox(
                    "Expiry",
                    snapshot.expiries,
                    index=snapshot.expiries.index(snapshot.selected_expiry),
                )
                if expiry_choice != snapshot.selected_expiry:
                    with st.spinner("Fetching selected expiry..."):
                        try:
                            snapshot = fetch_live_snapshot(
                                provider=data_provider,
                                symbol=live_symbol,
                                custom_url=custom_url,
                                custom_token=custom_token,
                                angel_api_key=angel_api_key,
                                angel_client_code=angel_client_code,
                                angel_password=angel_password,
                                angel_totp=angel_totp,
                                spot_hint=reference_spot,
                                strike_step=int(defaults["strike_step"]),
                                expiry=expiry_choice,
                            )
                            st.session_state["snapshot"] = snapshot
                        except MarketDataError as exc:
                            st.error(str(exc))
                st.success(f"{snapshot.source}: {snapshot.timestamp}")

        live_spot = float(snapshot.spot) if snapshot else 24176.15

        with st.expander("Account Settings", expanded=True):
            capital = st.number_input("Trading capital (INR)", min_value=1000.0, value=100000.0, step=5000.0)
            experience = st.selectbox("Experience", ["Beginner", "Intermediate", "Advanced"])
            strike_step = st.number_input("Strike interval", min_value=1, value=int(defaults["strike_step"]), step=1)
            lot_size = st.number_input("Lot size", min_value=1, value=int(defaults["lot_size"]), step=1)
            st.caption("Market view, levels, and risk are now calculated automatically from live data.")

        with st.expander("Gemini AI Brief", expanded=False):
            st.text_input(
                "Gemini API key",
                value=get_secret("GEMINI_API_KEY"),
                key="gemini_api_key",
                type="password",
            )
            st.text_input(
                "Gemini model",
                value=get_secret("GEMINI_MODEL") or "gemini-2.5-flash",
                key="gemini_model",
            )
            st.caption("Used only when you click Generate AI Brief. Do not commit keys to GitHub.")

    if snapshot:
        st.session_state["last_snapshot"] = snapshot

    return build_auto_analysis(
        symbol=symbol,
        spot=live_spot,
        strike_step=int(strike_step),
        lot_size=int(lot_size),
        capital=capital,
        experience=experience,
        snapshot=snapshot,
    )


def render_dashboard(analysis: AutoAnalysis, suggestions: list[StrategyIdea]) -> None:
    view = analysis.view
    snapshot = st.session_state.get("last_snapshot")
    append_snapshot_history(snapshot, analysis.signal)
    render_status_strip(view, snapshot)
    render_auto_trade_console(analysis, snapshot)
    tab_signals, tab_ai, tab_chain, tab_risk, tab_playbook = st.tabs(
        ["Auto Contracts", "AI Brief", "Option Chain", "Risk Console", "Playbook"]
    )
    with tab_signals:
        render_best_setup(view, suggestions, snapshot)
        render_suggestions(view, suggestions, snapshot)
    with tab_ai:
        render_ai_brief(view, suggestions, snapshot)
    with tab_chain:
        if snapshot:
            render_option_chain_table(snapshot, expanded=True)
        else:
            st.info("Enable live data and click Refresh to load option-chain rows.")
    with tab_risk:
        render_risk_console(view, suggestions)
    with tab_playbook:
        render_playbook()


def render_status_strip(view: MarketView, snapshot) -> None:
    risk_budget = view.capital * view.risk_percent / 100
    source = snapshot.source if snapshot else "Manual input"
    stamp = snapshot.timestamp if snapshot else "Latest close/manual"
    expiry = snapshot.selected_expiry if snapshot else f"{view.days_to_expiry} days"
    st.markdown(
        f"""
        <div class="status-strip">
          <div class="status-cell"><div class="status-label">Underlying</div><div class="status-value">{view.symbol}</div></div>
          <div class="status-cell"><div class="status-label">Spot</div><div class="status-value accent">{view.spot:,.2f}</div></div>
          <div class="status-cell"><div class="status-label">Bias</div><div class="status-value">{view.direction}</div></div>
          <div class="status-cell"><div class="status-label">Risk Budget</div><div class="status-value">INR {risk_budget:,.0f}</div></div>
          <div class="status-cell"><div class="status-label">Expiry</div><div class="status-value">{expiry}</div></div>
          <div class="status-cell"><div class="status-label">Data</div><div class="status-value">{source}</div></div>
        </div>
        <div class="small-note">Timestamp: {stamp}. Support {view.support:,.2f}, resistance {view.resistance:,.2f}, PCR {view.pcr:.2f}.</div>
        """,
        unsafe_allow_html=True,
    )


def render_auto_trade_console(analysis: AutoAnalysis, snapshot) -> None:
    view = analysis.view
    st.markdown(
        '<div class="section-title"><h3>Realtime Auto Analysis</h3><span>signal, graph, indicators, and option contract are generated from live data</span></div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.55, 1.0])
    with left:
        render_realtime_signal_chart(analysis, snapshot)
        render_contract_recommendation(analysis)
    with right:
        signal_class = "score" if analysis.signal != "WAIT" else "risk-pill"
        st.markdown(
            f"""
            <div class="best-shell">
              <div class="signal-title">{analysis.signal}</div>
              <div class="signal-bias">{analysis.summary}</div>
              <span class="{signal_class}">Strength {analysis.signal_strength}/100</span>
              <span class="risk-pill">Risk {analysis.risk_level} ({analysis.risk_percent:.2f}%)</span>
              <div class="small-note">Trend: {analysis.trend_label}. IV: {analysis.iv_label}.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(pd.DataFrame(analysis.indicators), use_container_width=True, hide_index=True)


def render_realtime_signal_chart(analysis: AutoAnalysis, snapshot) -> None:
    history = st.session_state.get("price_history", [])
    if not history:
        current = {
            "time": "Current",
            "spot": analysis.view.spot,
            "support": analysis.view.support,
            "resistance": analysis.view.resistance,
            "signal": analysis.signal,
        }
        history = [current]

    frame = pd.DataFrame(history)
    base = alt.Chart(frame).encode(x=alt.X("time:N", title="Refresh time"))
    spot_line = base.mark_line(color="#008f7a", strokeWidth=3).encode(
        y=alt.Y("spot:Q", title="Spot"),
        tooltip=["time", "spot", "support", "resistance", "signal"],
    )
    support_line = base.mark_line(color="#2f855a", strokeDash=[6, 4]).encode(y="support:Q")
    resistance_line = base.mark_line(color="#c24141", strokeDash=[6, 4]).encode(y="resistance:Q")
    marker = alt.Chart(frame.tail(1)).mark_point(size=170, filled=True, color=signal_color(analysis.signal)).encode(
        x="time:N",
        y="spot:Q",
        tooltip=["time", "spot", "signal"],
    )
    label = alt.Chart(frame.tail(1)).mark_text(
        align="left",
        dx=10,
        dy=-12,
        fontWeight="bold",
        color=signal_color(analysis.signal),
    ).encode(x="time:N", y="spot:Q", text="signal:N")
    st.altair_chart((spot_line + support_line + resistance_line + marker + label).properties(height=330), use_container_width=True)
    st.caption("The chart updates as each live refresh adds a new spot snapshot. Lines show spot, support, and resistance.")


def render_contract_recommendation(analysis: AutoAnalysis) -> None:
    contract = analysis.contract
    if not contract:
        st.info("No buy contract selected right now. The auto engine is waiting for a cleaner signal or live option quotes.")
        return
    premium = f"INR {contract.ltp:,.2f}" if contract.ltp else "LTP unavailable"
    st.markdown(
        f"""
        <div class="signal-card">
          <div class="signal-title">Suggested Option Contract</div>
          <div class="signal-bias">{contract.action} {contract.strike:g} {contract.option_type}</div>
          <span class="score">{premium}</span>
          <span class="risk-pill">OI {contract.open_interest:,.0f}</span>
          <div class="small-note">{contract.reason}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def signal_color(signal: str) -> str:
    if signal == "BUY CALL":
        return "#008f7a"
    if signal == "BUY PUT":
        return "#c24141"
    return "#b7791f"


def render_best_setup(view: MarketView, suggestions: list[StrategyIdea], snapshot) -> None:
    if not suggestions:
        return
    best = suggestions[0]
    payoff = build_payoff(best.legs, snapshot, view.spot, view.strike_step, view.lot_size)
    left, right = st.columns([1.3, 1.0])
    with left:
        st.markdown('<div class="section-title"><h3>Best Setup</h3><span>highest scoring idea from the rule engine</span></div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="best-shell">
              <div class="signal-title">{best.name}</div>
              <div class="signal-bias">{best.bias}</div>
              <span class="score">Fit {best.score}/100</span>
              <span class="risk-pill">Lots {format_lots(best.affordable_lots)}</span>
              <ul class="leg-list">{''.join(f'<li>{leg}</li>' for leg in best.legs)}</ul>
              <div class="small-note">{best.entry_filter[0] if best.entry_filter else ''}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<div class="section-title"><h3>Live Payoff Snapshot</h3><span>premium-aware when quotes exist</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="payoff-shell">', unsafe_allow_html=True)
        if payoff:
            render_payoff_metrics(payoff)
        else:
            st.info("Load live option data to calculate premium-based payoff.")
        st.markdown('</div>', unsafe_allow_html=True)


def render_market_summary(view: MarketView) -> None:
    risk_budget = view.capital * view.risk_percent / 100
    cols = st.columns(5)
    cols[0].metric("Underlying", view.symbol)
    cols[1].metric("Spot", f"{view.spot:,.2f}")
    cols[2].metric("Bias", view.direction)
    cols[3].metric("Risk Budget", f"INR {risk_budget:,.0f}")
    cols[4].metric("Expiry", f"{view.days_to_expiry} days")

    snapshot = st.session_state.get("last_snapshot")
    if snapshot:
        st.caption(
            f"Live data loaded for {snapshot.symbol}, expiry {snapshot.selected_expiry}, "
            f"timestamp {snapshot.timestamp}. Highest PE OI used as support and highest CE OI used as resistance."
        )
        render_option_chain_table(snapshot)


def render_suggestions(view: MarketView, suggestions: list[StrategyIdea], snapshot) -> None:
    st.markdown('<div class="section-title"><h3>Strategy Signals</h3><span>expand each idea for execution rules and payoff</span></div>', unsafe_allow_html=True)
    for index, idea in enumerate(suggestions, start=1):
        st.markdown(
            f"""
            <div class="signal-card">
              <div class="signal-title">{index}. {idea.name}</div>
              <div class="signal-bias">{idea.bias}</div>
              <span class="score">Fit {idea.score}/100</span>
              <span class="risk-pill">Lots {format_lots(idea.affordable_lots)}</span>
              <ul class="leg-list">{''.join(f'<li>{leg}</li>' for leg in idea.legs)}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander(f"Execution plan: {idea.name}"):
            leg_col, filter_col, risk_col = st.columns(3)
            leg_col.markdown("**Legs**")
            for leg in idea.legs:
                leg_col.write(f"- {leg}")
            filter_col.markdown("**Entry Filters**")
            for item in idea.entry_filter:
                filter_col.write(f"- {item}")
            risk_col.markdown("**Exit and Risk**")
            for item in idea.exit_plan + idea.risk_notes:
                risk_col.write(f"- {item}")
            if idea.max_risk_per_lot is not None:
                st.caption(f"Approximate modelled risk per lot: INR {idea.max_risk_per_lot:,.0f}. Replace this with broker-calculated margin and live premiums before trading.")
            payoff = build_payoff(idea.legs, snapshot, view.spot, view.strike_step, view.lot_size)
            render_payoff_chart(payoff)


def render_risk_console(view: MarketView, suggestions: list[StrategyIdea]) -> None:
    st.markdown('<div class="section-title"><h3>Risk Console</h3><span>position sizing and live payoff summary</span></div>', unsafe_allow_html=True)
    snapshot = st.session_state.get("last_snapshot")
    risk_budget = view.capital * view.risk_percent / 100
    best = suggestions[0] if suggestions else None
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Capital", f"INR {view.capital:,.0f}")
    col2.metric("Risk / Idea", f"{view.risk_percent:.2f}%")
    col3.metric("Risk Budget", f"INR {risk_budget:,.0f}")
    col4.metric("Top Setup", best.name if best else "None")

    st.progress(min(1.0, view.risk_percent / 5.0), text="Risk intensity")
    st.write("Use the modelled lot count as a planning cap. Broker margin and live premiums are the final source of truth.")

    table = []
    for idea in suggestions:
        payoff = build_payoff(idea.legs, snapshot, view.spot, view.strike_step, view.lot_size)
        table.append({
            "Strategy": idea.name,
            "Score": idea.score,
            "Lots by risk": format_lots(idea.affordable_lots),
            "Modelled risk/lot": "Check margin"
            if idea.max_risk_per_lot is None
            else f"INR {idea.max_risk_per_lot:,.0f}",
            "Live max profit": "Load quotes" if not payoff else f"INR {payoff.max_profit:,.0f}",
            "Live max loss": "Load quotes" if not payoff else f"INR {payoff.max_loss:,.0f}",
            "Breakevens": "Load quotes" if not payoff else format_breakevens(payoff.breakevens),
        })
    st.dataframe(table, use_container_width=True, hide_index=True)


def render_ai_brief(view: MarketView, suggestions: list[StrategyIdea], snapshot) -> None:
    st.markdown('<div class="section-title"><h3>Gemini AI Brief</h3><span>cautious commentary from current inputs</span></div>', unsafe_allow_html=True)
    st.write("Generate a concise market brief from the current inputs, strategy scores, and live option-chain summary.")
    key = st.session_state.get("gemini_api_key", "") or get_secret("GEMINI_API_KEY")
    model = st.session_state.get("gemini_model", "") or get_secret("GEMINI_MODEL") or "gemini-2.5-flash"
    col1, col2 = st.columns([1, 2])
    generate = col1.button("Generate AI Brief", use_container_width=True, disabled=not bool(key.strip()))
    col2.caption(f"Model: {model}. The brief is educational only and should be verified against live market data.")
    if not key.strip():
        st.info("Add a Gemini API key in the sidebar, environment, or Streamlit secrets.")

    if generate:
        with st.spinner("Asking Gemini for a cautious options brief..."):
            try:
                brief = generate_gemini_brief(
                    view=view,
                    suggestions=suggestions,
                    snapshot_summary=snapshot_to_summary(snapshot),
                    api_key=key,
                    model=model,
                )
                st.session_state["gemini_brief"] = brief
            except GeminiAdvisorError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Gemini failed: {exc}")

    brief = st.session_state.get("gemini_brief")
    if brief:
        render_gemini_brief(brief)


def render_gemini_brief(brief: GeminiBrief) -> None:
    st.markdown(
        f"""
        <div class="ai-brief-card">
          <div class="quality-badge">Setup Quality: {brief.setup_quality}</div>
          <div>{brief.summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Top Risks**")
        for item in brief.top_risks:
            st.write(f"- {item}")
    with col2:
        st.markdown("**What To Watch**")
        for item in brief.what_to_watch:
            st.write(f"- {item}")
    with col3:
        st.markdown("**Trade Management**")
        for item in brief.trade_management:
            st.write(f"- {item}")
    st.caption(f"{brief.disclaimer} Model: {brief.model}")


def render_playbook() -> None:
    with st.expander("Trade Checklist"):
        st.markdown(
            textwrap.dedent(
                """
                - Check NSE option-chain liquidity, bid-ask spread, IV, OI, and event calendar.
                - Prefer defined-risk spreads when learning or trading near expiry.
                - Keep total open risk below your daily loss limit.
                - Never sell naked options without understanding margin, gap risk, and adjustments.
                - Journal the setup, entry reason, stop, target, and actual exit.
                """
            )
        )

    with st.expander("How the model thinks"):
        st.write(
            "Low IV favors debit strategies, high IV favors defined-risk credit strategies, "
            "directional bias changes call/put selection, and beginner mode prefers simpler "
            "or no-trade outcomes. The app does not fetch live data or place orders."
        )


def render_option_chain_table(snapshot, expanded: bool = False) -> None:
    with st.expander("Option Chain Near Spot", expanded=expanded):
        st.caption("Rows are centered near spot. ATM, support, and resistance zones are highlighted when available.")
        table_rows = []
        for row in rows_near_spot(snapshot, width=10):
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            table_rows.append(
                {
                    "Strike": row.get("strikePrice"),
                    "CE LTP": ce.get("lastPrice"),
                    "CE OI": ce.get("openInterest"),
                    "CE IV": ce.get("impliedVolatility"),
                    "PE LTP": pe.get("lastPrice"),
                    "PE OI": pe.get("openInterest"),
                    "PE IV": pe.get("impliedVolatility"),
                    "Zone": strike_zone(row.get("strikePrice"), snapshot),
                }
            )
        frame = pd.DataFrame(table_rows)
        if not frame.empty:
            styled = frame.style.apply(highlight_chain_rows, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.info("No option-chain rows available near spot.")


def render_payoff_chart(payoff: PayoffResult | None) -> None:
    st.markdown("**Payoff Chart**")
    if not payoff:
        st.info("Load live option data to draw a payoff chart with option LTP.")
        return
    render_payoff_metrics(payoff)
    frame = pd.DataFrame(payoff.rows).set_index("Underlying")
    st.line_chart(frame, height=260)
    st.caption(f"Premium source: {payoff.premium_source}. Payoff is estimated at expiry and excludes charges/slippage.")


def render_payoff_metrics(payoff: PayoffResult) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Net Premium", f"INR {payoff.net_premium:,.0f}")
    col2.metric("Max Profit", f"INR {payoff.max_profit:,.0f}")
    col3.metric("Max Loss", f"INR {payoff.max_loss:,.0f}")
    st.caption(f"Breakeven: {format_breakevens(payoff.breakevens)}")


def strike_zone(strike, snapshot) -> str:
    try:
        value = float(strike)
    except (TypeError, ValueError):
        return ""
    if abs(value - snapshot.spot) <= 0.01:
        return "ATM"
    if abs(value - snapshot.support) <= 0.01:
        return "Support"
    if abs(value - snapshot.resistance) <= 0.01:
        return "Resistance"
    return ""


def highlight_chain_rows(row) -> list[str]:
    zone = row.get("Zone", "")
    if zone == "ATM":
        return ["background-color: rgba(0, 184, 148, 0.18)"] * len(row)
    if zone == "Support":
        return ["background-color: rgba(46, 204, 113, 0.14)"] * len(row)
    if zone == "Resistance":
        return ["background-color: rgba(255, 92, 92, 0.14)"] * len(row)
    return [""] * len(row)


def fetch_live_snapshot(
    provider: str,
    symbol: str,
    custom_url: str,
    custom_token: str,
    angel_api_key: str,
    angel_client_code: str,
    angel_password: str,
    angel_totp: str,
    spot_hint: float,
    strike_step: int,
    expiry: str | None = None,
):
    if provider == "Angel One SmartAPI":
        return fetch_angel_snapshot(
            api_key=angel_api_key,
            client_code=angel_client_code,
            password=angel_password,
            totp_or_secret=angel_totp,
            symbol=symbol,
            spot_hint=spot_hint,
            strike_step=strike_step,
            expiry=expiry,
        )
    if provider == "Custom broker/vendor JSON":
        if not custom_url.strip():
            raise MarketDataError("Enter a broker/vendor JSON endpoint URL.")
        return fetch_custom_snapshot(custom_url, custom_token)
    return fetch_option_chain(symbol, expiry)


def snapshot_to_summary(snapshot) -> dict:
    if not snapshot:
        return {}
    return {
        "symbol": snapshot.symbol,
        "spot": snapshot.spot,
        "timestamp": snapshot.timestamp,
        "selected_expiry": snapshot.selected_expiry,
        "pcr": snapshot.pcr,
        "support": snapshot.support,
        "resistance": snapshot.resistance,
        "avg_iv": snapshot.avg_iv,
        "source": snapshot.source,
    }


def format_lots(value: int | None) -> str:
    if value is None:
        return "Check margin"
    if value <= 0:
        return "0"
    return str(value)


def format_breakevens(values: list[float]) -> str:
    if not values:
        return "Not found in chart range"
    return ", ".join(f"{value:,.2f}" for value in values)


def get_secret(name: str) -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, "")


if __name__ == "__main__":
    main()
