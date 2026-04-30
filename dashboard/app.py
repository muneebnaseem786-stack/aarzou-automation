"""
AARZOU Operations Dashboard
Amazon UAE + Noon UAE — Revenue, Inventory, Ad Performance
"""

import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Must be first Streamlit call
st.set_page_config(
    page_title="AARZOU Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Import data layer ─────────────────────────────────────────────────────────
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dashboard.data import (
    amazon_ready, noon_ready,
    get_combined_revenue, get_combined_inventory,
    fetch_amazon_orders, fetch_noon_orders,
    fetch_amazon_inventory, fetch_noon_inventory,
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1a1a2e;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .stMetric label { font-size: 13px; color: #888; }
    .stMetric .stMetricValue { font-size: 28px; font-weight: 700; }
    div[data-testid="stHorizontalBlock"] { gap: 16px; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📦 AARZOU Operations Dashboard")
st.caption(f"Last refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')} UAE time")

# Platform status badges
col_a, col_b, col_c = st.columns([1, 1, 4])
with col_a:
    if amazon_ready():
        st.success("Amazon ✓ Connected")
    else:
        st.warning("Amazon — SP-API pending")
with col_b:
    if noon_ready():
        st.success("Noon ✓ Connected")
    else:
        st.warning("Noon — credentials needed")

st.divider()

# ── Date range selector ────────────────────────────────────────────────────────
days = st.select_slider(
    "Date range",
    options=[7, 14, 30, 60, 90],
    value=30,
    format_func=lambda x: f"Last {x} days",
)

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Fetching latest data..."):
    revenue_df   = get_combined_revenue(days)
    inventory_df = get_combined_inventory()

# ── If no credentials yet — show setup guide ──────────────────────────────────
if not amazon_ready() and not noon_ready():
    st.info(
        "**Dashboard is ready — waiting for API credentials.**\n\n"
        "Add these to your GitHub repository Secrets to go live:\n"
        "- `AMAZON_CLIENT_ID` + `AMAZON_CLIENT_SECRET` + `AMAZON_REFRESH_TOKEN` (SP-API, under review)\n"
        "- `NOON_API_KEY` + `NOON_API_SECRET` (from seller.noon.com → Settings → API Management)\n\n"
        "Once added, refresh this page."
    )
    st.stop()

# ── Tab layout ────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["💰 Revenue & Sales", "📦 Inventory", "📊 Ad Performance"])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Revenue & Sales
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    if revenue_df.empty:
        st.warning("No sales data available.")
    else:
        # Top-line metrics
        total_rev    = revenue_df["revenue_aed"].sum()
        total_units  = revenue_df["units"].sum()
        amazon_rev   = revenue_df[revenue_df["platform"] == "Amazon"]["revenue_aed"].sum()
        noon_rev     = revenue_df[revenue_df["platform"] == "Noon"]["revenue_aed"].sum()
        daily_avg    = total_rev / days

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Revenue", f"AED {total_rev:,.0f}")
        m2.metric("Units Sold", f"{total_units:,}")
        m3.metric("Daily Avg Revenue", f"AED {daily_avg:,.0f}")
        m4.metric("Amazon Revenue", f"AED {amazon_rev:,.0f}")
        m5.metric("Noon Revenue", f"AED {noon_rev:,.0f}")

        st.divider()

        # Revenue over time chart
        daily = revenue_df.groupby(["date", "platform"])["revenue_aed"].sum().reset_index()
        fig_rev = px.bar(
            daily, x="date", y="revenue_aed", color="platform",
            title=f"Daily Revenue — Last {days} Days",
            labels={"revenue_aed": "Revenue (AED)", "date": "", "platform": "Platform"},
            color_discrete_map={"Amazon": "#FF9900", "Noon": "#F7E03C"},
            barmode="stack",
        )
        fig_rev.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                              font_color="white", height=350)
        st.plotly_chart(fig_rev, use_container_width=True)

        st.divider()

        # Revenue by product
        col1, col2 = st.columns(2)
        with col1:
            by_product = revenue_df.groupby("product")["revenue_aed"].sum().sort_values(ascending=False).reset_index()
            fig_prod = px.bar(
                by_product, x="revenue_aed", y="product", orientation="h",
                title="Revenue by Product",
                labels={"revenue_aed": "Revenue (AED)", "product": ""},
                color="revenue_aed", color_continuous_scale="Oranges",
            )
            fig_prod.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                   font_color="white", height=320, showlegend=False)
            st.plotly_chart(fig_prod, use_container_width=True)

        with col2:
            by_product_units = revenue_df.groupby("product")["units"].sum().sort_values(ascending=False).reset_index()
            fig_units = px.bar(
                by_product_units, x="units", y="product", orientation="h",
                title="Units Sold by Product",
                labels={"units": "Units", "product": ""},
                color="units", color_continuous_scale="Blues",
            )
            fig_units.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                    font_color="white", height=320, showlegend=False)
            st.plotly_chart(fig_units, use_container_width=True)

        # Raw table
        with st.expander("View raw order data"):
            st.dataframe(
                revenue_df.sort_values("date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Inventory
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if inventory_df.empty:
        st.warning("No inventory data available.")
    else:
        # Reorder thresholds
        THRESHOLDS = {
            "Microphone": 10, "Broom Holder": 8, "Bidet": 8,
            "Travel Org Beige": 5, "Travel Org Grey": 5,
        }

        # Merge sales velocity to compute days remaining
        if not revenue_df.empty:
            velocity = revenue_df.groupby("product")["units"].sum().reset_index()
            velocity["daily_velocity"] = (velocity["units"] / days).round(1)
            inventory_df = inventory_df.merge(velocity[["product", "daily_velocity"]], on="product", how="left")
            inventory_df["daily_velocity"] = inventory_df["daily_velocity"].fillna(0)
            inventory_df["days_remaining"] = inventory_df.apply(
                lambda r: round(r["units_available"] / r["daily_velocity"])
                if r["daily_velocity"] > 0 else 999, axis=1
            )
        else:
            inventory_df["daily_velocity"] = 0
            inventory_df["days_remaining"] = 999

        inventory_df["reorder_threshold"] = inventory_df["product"].map(THRESHOLDS).fillna(5)
        inventory_df["status"] = inventory_df.apply(
            lambda r: "🚨 Reorder Now" if r["units_available"] <= r["reorder_threshold"]
            else ("⚠️ Low" if r["days_remaining"] < 21 else "✅ OK"),
            axis=1,
        )

        # Alert count
        critical = inventory_df[inventory_df["status"] == "🚨 Reorder Now"]
        if not critical.empty:
            st.error(f"**{len(critical)} product(s) need reordering now:** {', '.join(critical['product'].tolist())}")

        # Inventory chart
        fig_inv = px.bar(
            inventory_df, x="product", y="units_available", color="platform",
            title="Current Stock by Product & Platform",
            labels={"units_available": "Units Available", "product": "", "platform": "Platform"},
            color_discrete_map={"Amazon": "#FF9900", "Noon": "#F7E03C"},
            barmode="group",
        )
        fig_inv.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                              font_color="white", height=350)
        st.plotly_chart(fig_inv, use_container_width=True)

        # Inventory table
        display_cols = ["product", "platform", "units_available", "daily_velocity", "days_remaining", "status"]
        available_cols = [c for c in display_cols if c in inventory_df.columns]
        st.dataframe(
            inventory_df[available_cols].sort_values("days_remaining"),
            use_container_width=True,
            hide_index=True,
            column_config={
                "units_available": st.column_config.NumberColumn("Stock"),
                "daily_velocity":  st.column_config.NumberColumn("Units/Day", format="%.1f"),
                "days_remaining":  st.column_config.NumberColumn("Days Left"),
            }
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Ad Performance
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.info(
        "**Ad Performance coming soon.**\n\n"
        "This tab will show ACoS, ad spend, impressions, and clicks per product "
        "once the Amazon Advertising API is connected (separate from SP-API — "
        "build planned after SP-API base is live)."
    )

    # Placeholder layout so it doesn't look empty
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Ad Spend", "AED —")
    col2.metric("Total Ad Revenue", "AED —")
    col3.metric("Overall ACoS", "—%")
    col4.metric("Impressions", "—")
