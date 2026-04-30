"""AARZOU Operations Dashboard — Amazon UAE + Noon UAE"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data import amazon, noon, costs

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AARZOU Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Data loader (cached 15 min) ───────────────────────────────────────────────

@st.cache_data(ttl=900)
def load_amazon_data():
    inventory = amazon.get_inventory()
    sales_7d  = amazon.get_sales_7d()
    df_inv    = amazon.build_inventory_df(inventory, sales_7d)
    df_rev    = amazon.get_daily_revenue_30d()
    df_ads    = amazon.get_ad_performance_30d()
    fees      = amazon.get_fees()
    return df_inv, df_rev, df_ads, fees

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
            "**Demo mode** — representative data shown. "
            "Switches to live data automatically once SP-API credentials are added to GitHub Secrets."
        )

# ── Load data ─────────────────────────────────────────────────────────────────

df_inv, df_rev, df_ads, fees = load_amazon_data()

# ── Top KPI metrics ───────────────────────────────────────────────────────────

total_rev_30d  = df_rev["revenue_aed"].sum()
units_sold_30d = int(df_inv["_velocity_raw"].sum() * 30)
skus_alert     = int((df_inv["Status"].isin(["REORDER NOW", "LOW", "ZERO SALES"])).sum())
avg_days_stock = df_inv[df_inv["_days_left_raw"] < 999]["_days_left_raw"].mean()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Revenue (30d)", f"AED {total_rev_30d:,.0f}")
with col2:
    st.metric("Units Sold (30d est.)", str(units_sold_30d))
with col3:
    st.metric("SKUs Needing Attention", str(skus_alert))
with col4:
    st.metric("Avg Days of Stock", f"{avg_days_stock:.0f} days" if not pd.isna(avg_days_stock) else "—")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_inv, tab_rev, tab_ads, tab_pl = st.tabs([
    "📦  Inventory",
    "💰  Revenue & Sales",
    "📊  Ad Performance",
    "📈  P&L",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — INVENTORY
# ══════════════════════════════════════════════════════════════════════════════

with tab_inv:
    reorder_now = df_inv[df_inv["Status"] == "REORDER NOW"]
    low_stock   = df_inv[df_inv["Status"] == "LOW"]
    zero_sales  = df_inv[df_inv["Status"] == "ZERO SALES"]

    if not reorder_now.empty:
        st.error(f"**REORDER NOW:** {', '.join(reorder_now['Product'].tolist())}", icon="🚨")
    if not low_stock.empty:
        st.warning(f"**Low stock — reorder soon:** {', '.join(low_stock['Product'].tolist())}", icon="⚠️")
    if not zero_sales.empty:
        st.warning(f"**Zero sales (7d):** {', '.join(zero_sales['Product'].tolist())} — check listing / Buy Box", icon="📉")
    if reorder_now.empty and low_stock.empty and zero_sales.empty:
        st.success("All SKUs healthy.", icon="✅")

    st.markdown("### Stock Levels")

    def _status_color(val):
        return {
            "REORDER NOW": "background-color:#5c1a1a;color:#ff6b6b;font-weight:bold",
            "LOW":         "background-color:#3d3000;color:#ffd166;font-weight:bold",
            "ZERO SALES":  "background-color:#2d2d00;color:#ffe66d",
            "OK":          "color:#6bcb77",
        }.get(val, "")

    display_cols = ["Product", "ASIN", "Stock", "Reorder @", "Sold (7d)", "Velocity", "Days Left", "Status"]
    st.dataframe(
        df_inv[display_cols].style.map(_status_color, subset=["Status"]),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Stock vs Reorder Threshold")
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Current Stock",      x=df_inv["Product"], y=df_inv["Stock"],      marker_color="#4C9BE8", text=df_inv["Stock"],      textposition="outside"))
    fig.add_trace(go.Bar(name="Reorder Threshold",  x=df_inv["Product"], y=df_inv["Reorder @"],  marker_color="#FF6B35", opacity=0.7, text=df_inv["Reorder @"],  textposition="outside"))
    fig.update_layout(barmode="group", plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      margin=dict(t=20, b=0), height=300)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Days of Stock Remaining")
    days_df = df_inv[df_inv["_days_left_raw"] < 999].copy()
    days_df["color"] = days_df["_days_left_raw"].apply(
        lambda d: "#ff6b6b" if d <= 7 else ("#ffd166" if d <= 14 else "#6bcb77")
    )
    fig2 = go.Figure(go.Bar(
        x=days_df["Product"], y=days_df["_days_left_raw"],
        marker_color=days_df["color"].tolist(),
        text=days_df["_days_left_raw"].astype(int).astype(str) + "d",
        textposition="outside",
    ))
    fig2.add_hline(y=14, line_dash="dash", line_color="#ffd166", annotation_text="14-day warning")
    fig2.update_layout(plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
                       margin=dict(t=20, b=0), height=280, yaxis_title="Days")
    st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — REVENUE & SALES
# ══════════════════════════════════════════════════════════════════════════════

with tab_rev:
    st.markdown("### Daily Revenue — Last 30 Days")
    fig3 = px.area(df_rev, x="date", y="revenue_aed",
                   labels={"date": "", "revenue_aed": "Revenue (AED)"},
                   color_discrete_sequence=["#FF6B35"])
    fig3.update_traces(line_width=2, fillcolor="rgba(255,107,53,0.15)")
    fig3.update_layout(plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
                       margin=dict(t=10, b=0), height=300,
                       yaxis=dict(gridcolor="#2a2a3a"), xaxis=dict(gridcolor="#2a2a3a"))
    st.plotly_chart(fig3, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### Units Sold — Last 7 Days")
        fig4 = px.bar(df_inv, x="Product", y="Sold (7d)",
                      color="Sold (7d)", color_continuous_scale=["#1A1D27", "#FF6B35"],
                      text="Sold (7d)")
        fig4.update_traces(textposition="outside")
        fig4.update_layout(plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
                           coloraxis_showscale=False, margin=dict(t=10, b=0), height=280)
        st.plotly_chart(fig4, use_container_width=True)

    with col_b:
        st.markdown("### Est. Revenue by Product — 30 Days")
        df_inv["rev_30d_est"] = df_inv.apply(lambda r: round(r["_velocity_raw"] * 30 * r["_price"], 2), axis=1)
        fig5 = px.pie(df_inv, names="Product", values="rev_30d_est",
                      color_discrete_sequence=px.colors.qualitative.Bold, hole=0.4)
        fig5.update_traces(textposition="inside", textinfo="percent+label")
        fig5.update_layout(plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
                           margin=dict(t=10, b=0), height=280, showlegend=False)
        st.plotly_chart(fig5, use_container_width=True)

    st.markdown("### Product Revenue Breakdown")
    breakdown = df_inv[["Product", "Sold (7d)", "_velocity_raw", "_price", "rev_30d_est"]].copy()
    breakdown["Price (AED)"]      = breakdown["_price"]
    breakdown["Revenue 7d (AED)"] = (breakdown["Sold (7d)"] * breakdown["_price"]).round(0).astype(int)
    breakdown["Revenue 30d Est."] = breakdown["rev_30d_est"].round(0).astype(int).apply(lambda x: f"AED {x:,}")
    breakdown["Velocity"]         = breakdown["_velocity_raw"].apply(lambda v: f"{v:.2f}/day")
    st.dataframe(
        breakdown[["Product", "Price (AED)", "Sold (7d)", "Revenue 7d (AED)", "Velocity", "Revenue 30d Est."]],
        use_container_width=True, hide_index=True,
    )
    st.caption(f"7-day revenue total: **AED {(df_inv['Sold (7d)'] * df_inv['_price']).sum():,.0f}** · "
               f"30-day estimated total: **AED {df_inv['rev_30d_est'].sum():,.0f}**")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AD PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

with tab_ads:
    total_spend  = df_ads["Spend"].sum()
    total_sales  = df_ads["Sales"].sum()
    total_orders = int(df_ads["Orders"].sum())
    overall_acos = round(total_spend / total_sales * 100, 1) if total_sales > 0 else 0
    overall_roas = round(total_sales / total_spend, 2) if total_spend > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total Ad Spend (30d)",    f"AED {total_spend:,.0f}")
    with c2: st.metric("Attributed Sales (30d)",  f"AED {total_sales:,.0f}")
    with c3: st.metric("Overall ACOS",            f"{overall_acos}%")
    with c4: st.metric("Overall ROAS",            str(overall_roas))

    st.divider()

    # ── By Campaign ──────────────────────────────────────────────────────────
    st.markdown("### By Campaign")

    campaign_display = df_ads[[
        "Campaign", "Product", "Impressions", "Clicks", "CTR (%)",
        "Spend", "Sales", "Orders", "ACOS (%)", "ROAS", "CPC (AED)"
    ]].copy()
    campaign_display = campaign_display.rename(columns={"Spend": "Spend (AED)", "Sales": "Sales (AED)"})

    def _acos_color(val):
        if val > 35:  return "color:#ff6b6b"
        if val > 25:  return "color:#ffd166"
        return "color:#6bcb77"

    st.dataframe(
        campaign_display.style.map(_acos_color, subset=["ACOS (%)"]),
        use_container_width=True,
        hide_index=True,
    )

    # Spend vs Sales bar chart by campaign
    fig_camp = go.Figure()
    fig_camp.add_trace(go.Bar(name="Spend (AED)",  x=df_ads["Campaign"], y=df_ads["Spend"],  marker_color="#FF6B35"))
    fig_camp.add_trace(go.Bar(name="Sales (AED)",  x=df_ads["Campaign"], y=df_ads["Sales"],  marker_color="#4C9BE8"))
    fig_camp.update_layout(
        barmode="group", plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=20, b=80), height=320,
        xaxis=dict(tickangle=-30),
    )
    st.plotly_chart(fig_camp, use_container_width=True)

    # ── By Product ───────────────────────────────────────────────────────────
    st.markdown("### By Product")

    by_product = (
        df_ads.groupby("Product")
        .agg(
            Impressions=("Impressions", "sum"),
            Clicks=("Clicks", "sum"),
            Spend=("Spend", "sum"),
            Sales=("Sales", "sum"),
            Orders=("Orders", "sum"),
        )
        .reset_index()
    )
    by_product["ACOS (%)"] = (by_product["Spend"] / by_product["Sales"] * 100).round(1)
    by_product["ROAS"]     = (by_product["Sales"] / by_product["Spend"]).round(2)
    by_product = by_product.rename(columns={"Spend": "Spend (AED)", "Sales": "Sales (AED)"})

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        fig_ps = px.bar(by_product, x="Product", y=["Spend (AED)", "Sales (AED)"],
                        barmode="group",
                        color_discrete_sequence=["#FF6B35", "#4C9BE8"],
                        labels={"value": "AED", "variable": ""})
        fig_ps.update_layout(plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
                             margin=dict(t=10, b=0), height=280,
                             legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_ps, use_container_width=True)

    with col_p2:
        fig_acos = px.bar(by_product, x="Product", y="ACOS (%)",
                          color="ACOS (%)",
                          color_continuous_scale=["#6bcb77", "#ffd166", "#ff6b6b"],
                          range_color=[15, 40],
                          text=by_product["ACOS (%)"].apply(lambda v: f"{v}%"))
        fig_acos.update_traces(textposition="outside")
        fig_acos.add_hline(y=30, line_dash="dash", line_color="#ffd166", annotation_text="30% target")
        fig_acos.update_layout(plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
                               coloraxis_showscale=False, margin=dict(t=10, b=0), height=280)
        st.plotly_chart(fig_acos, use_container_width=True)

    st.dataframe(by_product, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — P&L
# ══════════════════════════════════════════════════════════════════════════════

with tab_pl:

    # ── Landed cost inputs ────────────────────────────────────────────────────
    st.markdown("### Landed Cost per Unit (AED)")
    st.caption("Enter your all-in landed cost: product + freight + customs per unit. All other costs are pulled from Amazon.")

    current_costs = costs.load()

    with st.form("costs_form"):
        cols = st.columns(len(amazon.PRODUCTS))
        new_costs = {}
        for i, (asin, meta) in enumerate(amazon.PRODUCTS.items()):
            with cols[i]:
                new_costs[asin] = st.number_input(
                    meta["name"],
                    value=float(current_costs.get(asin, 0.0)),
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                )
        submitted = st.form_submit_button("💾  Save Costs", use_container_width=True)
        if submitted:
            costs.save(new_costs)
            current_costs = new_costs
            st.success("Costs saved.")

    st.divider()

    # ── P&L calculation ───────────────────────────────────────────────────────
    st.markdown("### P&L by Product — Last 30 Days")

    # Ad spend per ASIN
    ad_by_asin = df_ads.groupby("ASIN")["Spend"].sum().to_dict()

    pl_rows = []
    for asin, meta in amazon.PRODUCTS.items():
        velocity   = float(df_inv.loc[df_inv["ASIN"] == asin, "_velocity_raw"].values[0])
        units_30d  = velocity * 30
        price      = meta["price"]
        revenue    = units_30d * price

        fee        = fees[asin]
        referral   = revenue * fee["referral_pct"]
        fba        = units_30d * fee["fba_per_unit"]
        storage    = fee["storage_monthly"]
        ad_spend   = ad_by_asin.get(asin, 0.0)
        landed     = current_costs.get(asin, 0.0) * units_30d

        total_cost    = referral + fba + storage + ad_spend + landed
        gross_profit  = revenue - total_cost
        margin        = (gross_profit / revenue * 100) if revenue > 0 else 0.0

        pl_rows.append({
            "Product":         meta["name"],
            "Units (30d)":     round(units_30d, 1),
            "Revenue":         round(revenue, 0),
            "Referral Fee":    round(referral, 0),
            "FBA Fee":         round(fba, 0),
            "Storage":         round(storage, 1),
            "Ad Spend":        round(ad_spend, 0),
            "Landed Cost":     round(landed, 0),
            "Gross Profit":    round(gross_profit, 0),
            "Margin %":        round(margin, 1),
        })

    df_pl = pd.DataFrame(pl_rows)

    # Overall summary KPIs
    o_rev    = df_pl["Revenue"].sum()
    o_cost   = df_pl[["Referral Fee", "FBA Fee", "Storage", "Ad Spend", "Landed Cost"]].sum().sum()
    o_profit = df_pl["Gross Profit"].sum()
    o_margin = (o_profit / o_rev * 100) if o_rev > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    with k1: st.metric("Gross Revenue (30d)",  f"AED {o_rev:,.0f}")
    with k2: st.metric("Total Costs (30d)",    f"AED {o_cost:,.0f}")
    with k3: st.metric("Gross Profit (30d)",   f"AED {o_profit:,.0f}")
    with k4: st.metric("Overall Margin",       f"{o_margin:.1f}%")

    # P&L table with color-coded margin
    def _margin_color(val):
        if val < 10:  return "color:#ff6b6b;font-weight:bold"
        if val < 20:  return "color:#ffd166"
        return "color:#6bcb77"

    def _profit_color(val):
        return "color:#ff6b6b;font-weight:bold" if val < 0 else "color:#6bcb77"

    currency_cols = ["Revenue", "Referral Fee", "FBA Fee", "Storage", "Ad Spend", "Landed Cost", "Gross Profit"]
    df_pl_display = df_pl.copy()
    for col in currency_cols:
        df_pl_display[col] = df_pl_display[col].apply(lambda v: f"AED {v:,.0f}")
    df_pl_display["Margin %"] = df_pl["Margin %"].apply(lambda v: f"{v:.1f}%")

    st.dataframe(
        df_pl.style
             .map(_margin_color, subset=["Margin %"])
             .map(_profit_color, subset=["Gross Profit"])
             .format({c: "AED {:.0f}" for c in ["Revenue","Referral Fee","FBA Fee","Storage","Ad Spend","Landed Cost","Gross Profit"]})
             .format({"Margin %": "{:.1f}%", "Units (30d)": "{:.1f}"}),
        use_container_width=True,
        hide_index=True,
    )

    # ── Cost waterfall (overall) ──────────────────────────────────────────────
    st.markdown("### Cost Breakdown — Where Revenue Goes")

    wf_labels  = ["Revenue", "Referral Fee", "FBA Fee", "Storage", "Ad Spend", "Landed Cost", "Gross Profit"]
    wf_values  = [
        o_rev,
        -df_pl["Referral Fee"].sum(),
        -df_pl["FBA Fee"].sum(),
        -df_pl["Storage"].sum(),
        -df_pl["Ad Spend"].sum(),
        -df_pl["Landed Cost"].sum(),
        o_profit,
    ]
    wf_measure = ["absolute", "relative", "relative", "relative", "relative", "relative", "total"]
    wf_colors  = ["#4C9BE8", "#FF6B35", "#FF6B35", "#FF6B35", "#FF6B35", "#FF6B35",
                  "#6bcb77" if o_profit >= 0 else "#ff6b6b"]

    fig_wf = go.Figure(go.Waterfall(
        orientation="v",
        measure=wf_measure,
        x=wf_labels,
        y=wf_values,
        text=[f"AED {abs(v):,.0f}" for v in wf_values],
        textposition="outside",
        connector={"line": {"color": "#444", "width": 1}},
        increasing={"marker": {"color": "#4C9BE8"}},
        decreasing={"marker": {"color": "#FF6B35"}},
        totals={"marker": {"color": "#6bcb77" if o_profit >= 0 else "#ff6b6b"}},
    ))
    fig_wf.update_layout(
        plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
        margin=dict(t=20, b=0), height=350,
        yaxis_title="AED",
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    # ── Gross profit by product ───────────────────────────────────────────────
    st.markdown("### Gross Profit by Product")
    profit_colors = ["#ff6b6b" if v < 0 else "#6bcb77" for v in df_pl["Gross Profit"]]
    fig_gp = go.Figure(go.Bar(
        x=df_pl["Product"],
        y=df_pl["Gross Profit"],
        marker_color=profit_colors,
        text=df_pl["Gross Profit"].apply(lambda v: f"AED {v:,.0f}"),
        textposition="outside",
    ))
    fig_gp.add_hline(y=0, line_color="#888", line_width=1)
    fig_gp.update_layout(
        plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="#FAFAFA",
        margin=dict(t=20, b=0), height=280, yaxis_title="AED",
    )
    st.plotly_chart(fig_gp, use_container_width=True)
