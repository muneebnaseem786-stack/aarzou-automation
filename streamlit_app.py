"""AARZOU Operations Dashboard — Amazon UAE + Noon UAE"""

import sys
import os

# Allow imports from the automation root
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data import amazon, noon

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AARZOU Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load data (cached 15 min) ─────────────────────────────────────────────────

@st.cache_data(ttl=900)
def load_amazon_data():
    inventory = amazon.get_inventory()
    sales_7d  = amazon.get_sales_7d()
    df_inv    = amazon.build_inventory_df(inventory, sales_7d)
    df_rev    = amazon.get_daily_revenue_30d()
    return df_inv, df_rev

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("AARZOU")
    st.caption("Operations Dashboard")
    st.divider()

    amazon_live = amazon.is_live()
    noon_live   = noon.is_live()

    if amazon_live:
        st.success("Amazon UAE  •  LIVE", icon="🟢")
    else:
        st.warning("Amazon UAE  •  DEMO", icon="🟡")

    if noon_live:
        st.success("Noon UAE  •  LIVE", icon="🟢")
    else:
        st.info("Noon UAE  •  Pending credentials", icon="⚪")

    st.divider()

    if st.button("↻  Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Last refreshed: {datetime.now(timezone.utc).strftime('%d %b %Y  %H:%M UTC')}")

    if not amazon_live:
        st.divider()
        st.caption(
            "**Demo mode** — showing representative data. "
            "Dashboard switches to live data automatically once SP-API credentials "
            "are added to GitHub Secrets."
        )

# ── Load data ─────────────────────────────────────────────────────────────────

df_inv, df_rev = load_amazon_data()

# ── Top KPI metrics ───────────────────────────────────────────────────────────

total_rev_30d   = df_rev["revenue_aed"].sum()
units_sold_30d  = sum(
    int(v.replace("/day", "").replace("∞", "0")) * 0   # placeholder: use raw
    for v in df_inv["Velocity"]
)
# use raw velocity for 30d unit estimate
units_sold_30d = int(df_inv["_velocity_raw"].sum() * 30)
skus_alert      = (df_inv["Status"].isin(["REORDER NOW", "LOW", "ZERO SALES"])).sum()
avg_days_stock  = df_inv[df_inv["_days_left_raw"] < 999]["_days_left_raw"].mean()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Revenue (30d)", f"AED {total_rev_30d:,.0f}")
with col2:
    st.metric("Units Sold (30d est.)", f"{units_sold_30d}")
with col3:
    delta_color = "inverse" if skus_alert > 0 else "normal"
    st.metric("SKUs Needing Attention", str(skus_alert), delta=None)
with col4:
    st.metric("Avg Days of Stock", f"{avg_days_stock:.0f} days" if not pd.isna(avg_days_stock) else "—")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_inv, tab_rev, tab_ads = st.tabs(["📦  Inventory", "💰  Revenue & Sales", "📊  Ad Performance"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — INVENTORY
# ═══════════════════════════════════════════════════════════════════════════════

with tab_inv:

    # Alert banner
    reorder_now = df_inv[df_inv["Status"] == "REORDER NOW"]
    low_stock   = df_inv[df_inv["Status"] == "LOW"]
    zero_sales  = df_inv[df_inv["Status"] == "ZERO SALES"]

    if not reorder_now.empty:
        names = ", ".join(reorder_now["Product"].tolist())
        st.error(f"**REORDER NOW:** {names}", icon="🚨")
    if not low_stock.empty:
        names = ", ".join(low_stock["Product"].tolist())
        st.warning(f"**Low stock — reorder soon:** {names}", icon="⚠️")
    if not zero_sales.empty:
        names = ", ".join(zero_sales["Product"].tolist())
        st.warning(f"**Zero sales (7d):** {names} — check listing / Buy Box", icon="📉")

    if reorder_now.empty and low_stock.empty and zero_sales.empty:
        st.success("All SKUs are healthy.", icon="✅")

    st.markdown("### Stock Levels")

    # Color-coded table
    def _status_color(val):
        colors = {
            "REORDER NOW": "background-color: #5c1a1a; color: #ff6b6b; font-weight: bold",
            "LOW":         "background-color: #3d3000; color: #ffd166; font-weight: bold",
            "ZERO SALES":  "background-color: #2d2d00; color: #ffe66d",
            "OK":          "color: #6bcb77",
        }
        return colors.get(val, "")

    display_cols = ["Product", "ASIN", "Stock", "Reorder @", "Sold (7d)", "Velocity", "Days Left", "Status"]
    styled = (
        df_inv[display_cols]
        .style
        .applymap(_status_color, subset=["Status"])
        .set_properties(**{"text-align": "center"}, subset=["Stock", "Reorder @", "Sold (7d)", "Velocity", "Days Left"])
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Stock vs threshold bar chart
    st.markdown("### Stock vs Reorder Threshold")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Current Stock",
        x=df_inv["Product"],
        y=df_inv["Stock"],
        marker_color="#4C9BE8",
        text=df_inv["Stock"],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Reorder Threshold",
        x=df_inv["Product"],
        y=df_inv["Reorder @"],
        marker_color="#FF6B35",
        opacity=0.7,
        text=df_inv["Reorder @"],
        textposition="outside",
    ))
    fig.update_layout(
        barmode="group",
        plot_bgcolor="#0E1117",
        paper_bgcolor="#0E1117",
        font_color="#FAFAFA",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=20, b=0),
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Days of stock chart
    st.markdown("### Days of Stock Remaining")

    days_df = df_inv[df_inv["_days_left_raw"] < 999].copy()
    days_df["color"] = days_df["_days_left_raw"].apply(
        lambda d: "#ff6b6b" if d <= 7 else ("#ffd166" if d <= 14 else "#6bcb77")
    )
    fig2 = go.Figure(go.Bar(
        x=days_df["Product"],
        y=days_df["_days_left_raw"],
        marker_color=days_df["color"],
        text=days_df["_days_left_raw"].astype(int).astype(str) + "d",
        textposition="outside",
    ))
    fig2.add_hline(y=14, line_dash="dash", line_color="#ffd166", annotation_text="14-day warning")
    fig2.update_layout(
        plot_bgcolor="#0E1117",
        paper_bgcolor="#0E1117",
        font_color="#FAFAFA",
        margin=dict(t=20, b=0),
        height=280,
        yaxis_title="Days",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — REVENUE & SALES
# ═══════════════════════════════════════════════════════════════════════════════

with tab_rev:

    st.markdown("### Daily Revenue — Last 30 Days")

    fig3 = px.area(
        df_rev,
        x="date",
        y="revenue_aed",
        labels={"date": "", "revenue_aed": "Revenue (AED)"},
        color_discrete_sequence=["#FF6B35"],
    )
    fig3.update_traces(line_width=2, fillcolor="rgba(255,107,53,0.15)")
    fig3.update_layout(
        plot_bgcolor="#0E1117",
        paper_bgcolor="#0E1117",
        font_color="#FAFAFA",
        margin=dict(t=10, b=0),
        height=300,
        yaxis=dict(gridcolor="#2a2a3a"),
        xaxis=dict(gridcolor="#2a2a3a"),
    )
    st.plotly_chart(fig3, use_container_width=True)

    # 7-day sales and estimated 30-day revenue side by side
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("### Units Sold — Last 7 Days")
        fig4 = px.bar(
            df_inv,
            x="Product",
            y="Sold (7d)",
            color="Sold (7d)",
            color_continuous_scale=["#1A1D27", "#FF6B35"],
            text="Sold (7d)",
        )
        fig4.update_traces(textposition="outside")
        fig4.update_layout(
            plot_bgcolor="#0E1117",
            paper_bgcolor="#0E1117",
            font_color="#FAFAFA",
            coloraxis_showscale=False,
            margin=dict(t=10, b=0),
            height=280,
        )
        st.plotly_chart(fig4, use_container_width=True)

    with col_b:
        st.markdown("### Est. Revenue by Product — 30 Days")
        df_inv["rev_30d_est"] = df_inv.apply(
            lambda r: round(r["_velocity_raw"] * 30 * r["_price"], 2), axis=1
        )
        fig5 = px.pie(
            df_inv,
            names="Product",
            values="rev_30d_est",
            color_discrete_sequence=px.colors.qualitative.Bold,
            hole=0.4,
        )
        fig5.update_traces(textposition="inside", textinfo="percent+label")
        fig5.update_layout(
            plot_bgcolor="#0E1117",
            paper_bgcolor="#0E1117",
            font_color="#FAFAFA",
            margin=dict(t=10, b=0),
            height=280,
            showlegend=False,
        )
        st.plotly_chart(fig5, use_container_width=True)

    # Product breakdown table
    st.markdown("### Product Revenue Breakdown")

    breakdown = df_inv[["Product", "Sold (7d)", "_velocity_raw", "_price", "rev_30d_est"]].copy()
    breakdown["Price (AED)"]        = breakdown["_price"]
    breakdown["Revenue 7d (AED)"]   = (breakdown["Sold (7d)"] * breakdown["_price"]).round(0).astype(int)
    breakdown["Revenue 30d Est."]   = breakdown["rev_30d_est"].round(0).astype(int).apply(lambda x: f"AED {x:,}")
    breakdown["Velocity"]           = breakdown["_velocity_raw"].apply(lambda v: f"{v:.2f}/day")

    total_7d  = breakdown["Revenue 7d (AED)"].sum()
    total_30d = breakdown["_velocity_raw"].sum() * 30

    st.dataframe(
        breakdown[["Product", "Price (AED)", "Sold (7d)", "Revenue 7d (AED)", "Velocity", "Revenue 30d Est."]],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"7-day revenue total: **AED {total_7d:,}** · 30-day estimated total: **AED {df_inv['rev_30d_est'].sum():,.0f}**")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AD PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════

with tab_ads:

    st.info(
        "**Ad Performance tracking is coming in the next build.** "
        "This tab will connect to the Amazon Advertising API (separate credentials from SP-API).",
        icon="🔧",
    )

    st.markdown("### What will be tracked here")
    st.markdown("""
| Metric | Source |
|---|---|
| Spend (daily / 7d / 30d) | Amazon Advertising API |
| ACOS (Advertising Cost of Sale) | Amazon Advertising API |
| ROAS (Return on Ad Spend) | Amazon Advertising API |
| Impressions & Clicks per campaign | Amazon Advertising API |
| Top-performing keywords | Amazon Advertising API |
| Noon ad performance | Noon Commercial API |
""")

    st.markdown("### How to enable")
    st.markdown("""
1. Apply for Amazon Advertising API access at [advertising.amazon.com/API](https://advertising.amazon.com/API)
2. Create a developer application — separate from SP-API
3. Add credentials to GitHub Secrets: `AMAZON_ADS_CLIENT_ID`, `AMAZON_ADS_CLIENT_SECRET`, `AMAZON_ADS_REFRESH_TOKEN`
4. Ad data will appear here automatically on the next refresh
""")
