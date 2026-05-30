"""Road SOS dashboard visual system — mission-critical, restrained, production-grade."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

# Semantic tokens only — color carries meaning
COLORS = {
    "bg": "#0c0e10",
    "surface": "#14171b",
    "surface_raised": "#1a1e24",
    "border": "#2a3139",
    "border_subtle": "#1f252c",
    "text": "#e4e7eb",
    "text_secondary": "#9aa3ad",
    "text_muted": "#5f6872",
    "accent": "#4a7c9b",
    "accent_dim": "#2d4a5c",
    "critical": "#b85c50",
    "warning": "#a68b4b",
    "ok": "#4d8a6a",
    "neutral": "#6b7580",
    "grid": "#232930",
}

SEVERITY_CLASS = {
    "severe": "rsos-sev-critical",
    "collision": "rsos-sev-critical",
    "near_miss": "rsos-sev-warning",
    "pending_review": "rsos-sev-warning",
    "confirmed": "rsos-sev-ok",
    "dismissed": "rsos-sev-neutral",
    "log_only": "rsos-sev-neutral",
}


def inject_theme() -> None:
    st.markdown(
        f"""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
        :root {{
            --rsos-bg: {COLORS["bg"]};
            --rsos-surface: {COLORS["surface"]};
            --rsos-border: {COLORS["border"]};
            --rsos-text: {COLORS["text"]};
            --rsos-muted: {COLORS["text_muted"]};
            --rsos-accent: {COLORS["accent"]};
        }}
        .stApp {{
            background-color: var(--rsos-bg);
            font-family: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            background-color: var(--rsos-bg);
        }}
        [data-testid="stHeader"] {{
            background: transparent;
        }}
        [data-testid="stSidebar"] {{
            background-color: {COLORS["surface"]};
            border-right: 1px solid {COLORS["border"]};
        }}
        [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{
            color: {COLORS["text_secondary"]};
        }}
        h1, h2, h3, [data-testid="stMarkdownContainer"] h1 {{
            font-family: "IBM Plex Sans", sans-serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em;
            color: {COLORS["text"]} !important;
        }}
        p, span, label, .stCaption {{
            color: {COLORS["text_secondary"]};
        }}
        [data-testid="stMetricValue"] {{
            font-family: "IBM Plex Mono", monospace !important;
            font-size: 1.35rem !important;
            color: {COLORS["text"]} !important;
        }}
        [data-testid="stMetricLabel"] {{
            font-size: 0.7rem !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: {COLORS["text_muted"]} !important;
        }}
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
            gap: 0;
            background: transparent;
            border-bottom: 1px solid {COLORS["border"]};
            padding: 0;
        }}
        div[data-testid="stTabs"] button[data-baseweb="tab"] {{
            background: transparent !important;
            border: none !important;
            border-radius: 0 !important;
            color: {COLORS["text_muted"]} !important;
            font-family: "IBM Plex Sans", sans-serif !important;
            font-size: 0.8125rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            padding: 0.75rem 1.25rem !important;
            margin: 0 !important;
        }}
        div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {{
            color: {COLORS["text"]} !important;
            border-bottom: 2px solid {COLORS["accent"]} !important;
            background: transparent !important;
        }}
        div[data-testid="stTabs"] [data-baseweb="tab-panel"] {{
            padding-top: 1.5rem;
        }}
        .stButton > button {{
            border-radius: 2px !important;
            font-family: "IBM Plex Sans", sans-serif !important;
            font-weight: 500 !important;
            font-size: 0.8125rem !important;
            letter-spacing: 0.02em;
            border: 1px solid {COLORS["border"]} !important;
            background: {COLORS["surface_raised"]} !important;
            color: {COLORS["text"]} !important;
            box-shadow: none !important;
        }}
        .stButton > button[kind="primary"] {{
            background: {COLORS["accent_dim"]} !important;
            border-color: {COLORS["accent"]} !important;
            color: {COLORS["text"]} !important;
        }}
        .stButton > button:hover {{
            border-color: {COLORS["accent"]} !important;
        }}
        [data-testid="stExpander"] {{
            border: 1px solid {COLORS["border"]} !important;
            border-radius: 2px !important;
            background: {COLORS["surface"]} !important;
        }}
        [data-testid="stFileUploader"] {{
            border: 1px dashed {COLORS["border"]} !important;
            border-radius: 2px !important;
            background: {COLORS["surface"]} !important;
        }}
        .stSelectbox > div > div, .stTextInput > div > div > input {{
            border-radius: 2px !important;
            background: {COLORS["surface"]} !important;
            border-color: {COLORS["border"]} !important;
            color: {COLORS["text"]} !important;
            font-size: 0.875rem !important;
        }}
        [data-testid="stAlert"] {{
            border-radius: 2px !important;
            border: 1px solid {COLORS["border"]} !important;
            background: {COLORS["surface"]} !important;
        }}
        hr {{
            border-color: {COLORS["border_subtle"]} !important;
            margin: 1.25rem 0 !important;
        }}
        /* Hide Streamlit chrome noise */
        #MainMenu, footer, header[data-testid="stHeader"] {{
            visibility: hidden;
        }}
        [data-testid="stToolbar"] {{
            display: none;
        }}

        /* Custom components */
        .rsos-shell {{ max-width: 100%; }}
        .rsos-topbar {{
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            padding-bottom: 1.25rem;
            margin-bottom: 0.5rem;
            border-bottom: 1px solid {COLORS["border"]};
        }}
        .rsos-brand {{
            font-size: 1.125rem;
            font-weight: 600;
            letter-spacing: -0.02em;
            color: {COLORS["text"]};
            margin: 0;
            line-height: 1.2;
        }}
        .rsos-subbrand {{
            font-size: 0.75rem;
            font-weight: 400;
            color: {COLORS["text_muted"]};
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-top: 0.25rem;
        }}
        .rsos-system-status {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.6875rem;
            font-weight: 500;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: {COLORS["text_secondary"]};
        }}
        .rsos-status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: {COLORS["ok"]};
        }}
        .rsos-section {{
            margin-bottom: 1.5rem;
        }}
        .rsos-section-title {{
            font-size: 0.6875rem;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: {COLORS["text_muted"]};
            margin: 0 0 0.35rem 0;
        }}
        .rsos-section-head {{
            font-size: 1rem;
            font-weight: 600;
            color: {COLORS["text"]};
            margin: 0 0 0.25rem 0;
        }}
        .rsos-section-desc {{
            font-size: 0.8125rem;
            color: {COLORS["text_secondary"]};
            margin: 0 0 1rem 0;
            line-height: 1.5;
            max-width: 52rem;
        }}
        .rsos-stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1px;
            background: {COLORS["border"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 2px;
            overflow: hidden;
            margin-bottom: 1.5rem;
        }}
        .rsos-stat-cell {{
            background: {COLORS["surface"]};
            padding: 0.875rem 1rem;
        }}
        .rsos-stat-label {{
            font-size: 0.625rem;
            font-weight: 500;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: {COLORS["text_muted"]};
            margin-bottom: 0.35rem;
        }}
        .rsos-stat-value {{
            font-family: "IBM Plex Mono", monospace;
            font-size: 1.25rem;
            font-weight: 500;
            color: {COLORS["text"]};
            line-height: 1.2;
        }}
        .rsos-stat-value.critical {{ color: {COLORS["critical"]}; }}
        .rsos-stat-value.warning {{ color: {COLORS["warning"]}; }}
        .rsos-stat-value.ok {{ color: {COLORS["ok"]}; }}
        .rsos-panel {{
            border: 1px solid {COLORS["border"]};
            border-radius: 2px;
            background: {COLORS["surface"]};
            margin-bottom: 1rem;
        }}
        .rsos-panel-hd {{
            padding: 0.65rem 1rem;
            border-bottom: 1px solid {COLORS["border_subtle"]};
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
        }}
        .rsos-panel-title {{
            font-size: 0.8125rem;
            font-weight: 600;
            color: {COLORS["text"]};
            margin: 0;
        }}
        .rsos-panel-body {{
            padding: 1rem;
        }}
        .rsos-badge {{
            display: inline-block;
            font-size: 0.625rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            padding: 0.2rem 0.45rem;
            border-radius: 2px;
            border: 1px solid;
        }}
        .rsos-sev-critical {{
            color: {COLORS["critical"]};
            border-color: {COLORS["critical"]};
            background: rgba(184, 92, 80, 0.08);
        }}
        .rsos-sev-warning {{
            color: {COLORS["warning"]};
            border-color: {COLORS["warning"]};
            background: rgba(166, 139, 75, 0.08);
        }}
        .rsos-sev-ok {{
            color: {COLORS["ok"]};
            border-color: {COLORS["ok"]};
            background: rgba(77, 138, 106, 0.08);
        }}
        .rsos-sev-neutral {{
            color: {COLORS["neutral"]};
            border-color: {COLORS["border"]};
            background: transparent;
        }}
        .rsos-meta-row {{
            display: grid;
            grid-template-columns: 120px 1fr;
            gap: 0.5rem 1rem;
            font-size: 0.8125rem;
            margin-bottom: 0.35rem;
        }}
        .rsos-meta-key {{
            color: {COLORS["text_muted"]};
            font-size: 0.6875rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .rsos-meta-val {{
            color: {COLORS["text"]};
            font-family: "IBM Plex Mono", monospace;
            font-size: 0.75rem;
        }}
        .rsos-empty {{
            padding: 2rem 1rem;
            text-align: center;
            color: {COLORS["text_muted"]};
            font-size: 0.8125rem;
            border: 1px dashed {COLORS["border"]};
            border-radius: 2px;
            background: {COLORS["surface"]};
        }}
        .rsos-table-wrap {{
            overflow-x: auto;
            border: 1px solid {COLORS["border"]};
            border-radius: 2px;
        }}
        table.rsos-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.75rem;
        }}
        table.rsos-table th {{
            text-align: left;
            padding: 0.5rem 0.75rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            font-size: 0.625rem;
            color: {COLORS["text_muted"]};
            background: {COLORS["surface_raised"]};
            border-bottom: 1px solid {COLORS["border"]};
        }}
        table.rsos-table td {{
            padding: 0.5rem 0.75rem;
            color: {COLORS["text_secondary"]};
            border-bottom: 1px solid {COLORS["border_subtle"]};
            font-family: "IBM Plex Mono", monospace;
            font-size: 0.6875rem;
        }}
        table.rsos-table tr:last-child td {{
            border-bottom: none;
        }}
        .rsos-sidebar-label {{
            font-size: 0.625rem;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: {COLORS["text_muted"]};
            margin: 1rem 0 0.5rem 0;
        }}
        .rsos-sidebar-val {{
            font-size: 0.8125rem;
            color: {COLORS["text"]};
            margin-bottom: 0.25rem;
        }}
        .rsos-sidebar-mono {{
            font-family: "IBM Plex Mono", monospace;
            font-size: 0.6875rem;
            color: {COLORS["text_secondary"]};
        }}
        .rsos-routing-line {{
            font-size: 0.75rem;
            color: {COLORS["text_secondary"]};
            padding: 0.35rem 0;
            border-bottom: 1px solid {COLORS["border_subtle"]};
        }}
        .rsos-routing-line:last-child {{ border-bottom: none; }}
        .rsos-routing-key {{
            color: {COLORS["text_muted"]};
            display: inline-block;
            width: 5.5rem;
            text-transform: uppercase;
            font-size: 0.625rem;
            letter-spacing: 0.06em;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _esc(text: Any) -> str:
    return html.escape(str(text) if text is not None else "")


def render_topbar(subtitle: str = "Traffic Accident Detection System") -> None:
    st.markdown(
        f"""
        <div class="rsos-topbar">
            <div>
                <p class="rsos-brand">Road SOS</p>
                <p class="rsos-subbrand">{_esc(subtitle)}</p>
            </div>
            <div class="rsos-system-status">
                <span class="rsos-status-dot"></span>
                <span>Operational</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str, description: str = "") -> None:
    st.markdown(f"#### {_esc(title)}")
    if description:
        st.caption(description)


def render_stat_grid(stats: list[tuple[str, str, str]]) -> None:
    """stats: [(label, value, tone)] — uses native metrics (avoids markdown code-block HTML bug)."""
    cols = st.columns(len(stats))
    for col, (label, value, _tone) in zip(cols, stats):
        with col:
            st.metric(label=label, value=value)


def render_badge(text: str, severity_key: str = "neutral") -> str:
    cls = SEVERITY_CLASS.get(severity_key, "rsos-sev-neutral")
    return f'<span class="rsos-badge {cls}">{_esc(text)}</span>'


def render_panel_header(title: str, badge_html: str = "") -> None:
    if badge_html:
        st.markdown(f"**{_esc(title)}** &nbsp; {badge_html}", unsafe_allow_html=True)
    else:
        st.markdown(f"**{_esc(title)}**")


def render_meta_grid(rows: list[tuple[str, str]]) -> None:
    for key, val in rows:
        st.markdown(f"<span class='rsos-meta-key'>{_esc(key)}</span> `{_esc(val)}`", unsafe_allow_html=True)


def render_empty(message: str) -> None:
    st.info(message)


def render_html_table(rows: list[dict], columns: list[tuple[str, str]]) -> None:
    """columns: [(key, header_label), ...]"""
    if not rows:
        render_empty("No records in this period.")
        return
    import pandas as pd

    labels = [h for _, h in columns]
    keys = [k for k, _ in columns]
    data = [{h: row.get(k, "") for k, h in zip(keys, labels)} for row in rows]
    st.dataframe(pd.DataFrame(data), width="stretch", hide_index=True)


def render_analytics_bars(by_severity: dict[str, int]) -> None:
    if not by_severity:
        render_empty("No classified incidents yet.")
        return
    max_val = max(by_severity.values()) or 1
    bars = []
    tone_map = {"severe": "critical", "collision": "critical", "near_miss": "warning"}
    for sev, count in sorted(by_severity.items(), key=lambda x: -x[1]):
        pct = int(100 * count / max_val)
        tone = tone_map.get(sev, "")
        color = COLORS.get(tone, COLORS["accent"]) if tone else COLORS["accent"]
        bars.append(
            f"""
            <div style="margin-bottom:0.75rem;">
                <div style="display:flex;justify-content:space-between;font-size:0.6875rem;
                    text-transform:uppercase;letter-spacing:0.06em;color:{COLORS["text_muted"]};margin-bottom:0.25rem;">
                    <span>{_esc(sev)}</span>
                    <span style="font-family:IBM Plex Mono,monospace;color:{COLORS["text"]};">{count}</span>
                </div>
                <div style="height:4px;background:{COLORS["grid"]};border-radius:1px;">
                    <div style="width:{pct}%;height:100%;background:{color};border-radius:1px;"></div>
                </div>
            </div>
            """
        )
    st.markdown(
        f'<div class="rsos-panel" style="padding:1rem;">{"".join(bars)}</div>',
        unsafe_allow_html=True,
    )


def plot_cooldown_chart(zones: list[dict]) -> None:
    import pandas as pd

    df = pd.DataFrame(zones)
    if df.empty:
        return

    try:
        import plotly.express as px

        fig = px.scatter(
            df,
            x="x",
            y="y",
            size="radius_px",
            color="reason",
            color_discrete_map={"alert": COLORS["critical"], "blocked": COLORS["neutral"]},
            height=320,
        )
        fig.update_layout(
            paper_bgcolor=COLORS["surface"],
            plot_bgcolor=COLORS["bg"],
            font_family="IBM Plex Sans",
            font_color=COLORS["text_secondary"],
            margin=dict(l=40, r=20, t=30, b=40),
            xaxis=dict(gridcolor=COLORS["grid"], linecolor=COLORS["border"], title="X (px)"),
            yaxis=dict(gridcolor=COLORS["grid"], linecolor=COLORS["border"], title="Y (px)"),
            legend=dict(bgcolor="transparent", borderwidth=0),
            showlegend=True,
        )
        fig.update_traces(marker=dict(line=dict(width=0), opacity=0.85))
        st.plotly_chart(fig, width="stretch")
    except ImportError:
        st.caption("Install plotly for styled chart, or use table below.")
        st.scatter_chart(df, x="x", y="y", size="radius_px", color="reason")


def sidebar_block(label: str, value: str, mono: str | None = None) -> None:
    extra = f'<div class="rsos-sidebar-mono">{_esc(mono)}</div>' if mono else ""
    st.markdown(
        f"""
        <p class="rsos-sidebar-label">{_esc(label)}</p>
        <p class="rsos-sidebar-val">{_esc(value)}</p>
        {extra}
        """,
        unsafe_allow_html=True,
    )
