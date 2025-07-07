import streamlit as st
import pandas as pd
import json
import plotly.express as px
import locale
from io import BytesIO
from pathlib import Path

# --- Format currency as ₹12,34,567 ---
def format_inr(value):
    try:
        locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
        return locale.currency(value, grouping=True)
    except:
        return f"₹{value:,.0f}"

# --- Default file paths ---
default_csv = Path("portfolio_data.csv")
default_beta = Path("bank_financial_metrics.json")
default_master = Path("bank_master.json")
default_labels = Path("labels.json")
default_portfolio_master = Path("portfolio_master.json")

# --- Sidebar: Language ---
st.sidebar.header("🌐 Language / மொழி")
language = st.sidebar.radio("Choose Language", ["English", "Tamil"])

# --- Sidebar: File Uploads ---
st.sidebar.header("📂 File Uploads")
csv_file = default_csv.open("rb") if default_csv.exists() else st.sidebar.file_uploader("Upload Portfolio CSV", type=["csv"])
beta_json_file = default_beta.open("rb") if default_beta.exists() else st.sidebar.file_uploader("Upload Financial Metrics JSON", type=["json"])
bank_master_file = default_master.open("rb") if default_master.exists() else st.sidebar.file_uploader("Upload Bank Master JSON", type=["json"])
labels_file = default_labels.open("rb") if default_labels.exists() else st.sidebar.file_uploader("Upload Labels JSON", type=["json"])
portfolio_master_file = default_portfolio_master.open("rb") if default_portfolio_master.exists() else st.sidebar.file_uploader("Upload Portfolio Master JSON", type=["json"])

# --- Exit if any files missing ---
if not all([csv_file, beta_json_file, bank_master_file, labels_file, portfolio_master_file]):
    st.info("⬅️ Upload all files or ensure default files are in place.")
    st.stop()

# --- Load JSON files ---
label_data = json.load(labels_file)
labels = label_data[language]
header_labels = labels["table_headers"]

bank_data = json.load(bank_master_file)
portfolio_meta = json.load(portfolio_master_file)
beta_data = json.load(beta_json_file)
beta_map = {item["isin"]: item.get("beta_1yr") for item in beta_data["financial_metrics"]}

# --- Load portfolio and map names ---
df = pd.read_csv(csv_file)
df["Beta (1Y)"] = df["ISIN"].map(beta_map)

# Bank name translation by ISIN
bank_name_map = {
    bank["isin"]: {
        "English": bank.get("full_name_en", ""),
        "Tamil": bank.get("full_name_ta", bank.get("full_name_en", ""))
    }
    for bank in bank_data["banks_data"]
}
df["Display Name"] = df.apply(
    lambda row: bank_name_map.get(row["ISIN"], {}).get(language, row["Stock Name"]),
    axis=1
)

# Member code & portfolio name translation
portfolio_map = {
    item["member_code"]: {
        "member": item.get("member_code_ta" if language == "Tamil" else "member_code", item["member_code"]),
        "portfolio": item.get("portfolio_ta" if language == "Tamil" else "portfolio", "")
    }
    for item in portfolio_meta["portfolio_data"]
}
df["Member Display"] = df["Member code"].apply(lambda code: portfolio_map.get(code, {}).get("member", code))
df["Portfolio Name"] = df["Member code"].apply(lambda code: portfolio_map.get(code, {}).get("portfolio", ""))

# Profit %
df["Profit %"] = ((df["Value At Market Price"] - df["Value At Cost"]) / df["Value At Cost"]) * 100
df["Profit %"] = df["Profit %"].round(2)

# --- Sidebar: Stock filter ---
stock_options = df["Display Name"].unique()
selected_stocks = st.sidebar.multiselect(f"🎯 {labels['filter_by_sector']}", stock_options, default=list(stock_options))
filtered_df = df[df["Display Name"].isin(selected_stocks)]

# --- Summary metrics ---
total_cost = filtered_df["Value At Cost"].sum()
total_market = filtered_df["Value At Market Price"].sum()
profit_pct = ((total_market - total_cost) / total_cost) * 100 if total_cost else 0
filtered_df["Weight"] = filtered_df["Value At Market Price"] / total_market
filtered_df["Weighted Beta"] = filtered_df["Beta (1Y)"] * filtered_df["Weight"]
portfolio_beta = filtered_df["Weighted Beta"].sum()

# --- Page layout ---
st.set_page_config(page_title=labels["title"], layout="wide")
st.title(f"📊 {labels['title']}")

# --- Summary cards ---
st.markdown("### 💼 " + labels["table_title"])
col1, col2, col3, col4 = st.columns(4)
col1.metric(labels["marketcap_label"], format_inr(round(total_cost)))
col2.metric("Market Value", format_inr(round(total_market)))
col3.metric("Profit %", f"{profit_pct:.2f}%")
col4.metric(labels["beta_label"], f"{portfolio_beta:.2f}")

# --- Bar Chart ---
st.markdown(f"### 📈 {labels['graph_title']}")
chart_df = filtered_df.copy()
chart_df["Label"] = chart_df["Display Name"] + " (" + chart_df["Sector name"].fillna("Unknown") + ")"
fig = px.bar(
    chart_df.sort_values("Value At Market Price", ascending=False),
    x="Value At Market Price",
    y="Label",
    color="Profit %",
    orientation="h",
    color_continuous_scale="RdYlGn",
    hover_data=["Qty", "Beta (1Y)", "Value At Cost", "Value At Market Price", "Profit %"],
    height=500
)
fig.update_layout(yaxis_title="", xaxis_title=labels["marketcap_label"], coloraxis_colorbar_title="Profit %")
st.plotly_chart(fig, use_container_width=True)

# --- Format ₹ values ---
filtered_df["Value At Cost"] = filtered_df["Value At Cost"].apply(lambda x: format_inr(round(x)))
filtered_df["Value At Market Price"] = filtered_df["Value At Market Price"].apply(lambda x: format_inr(round(x)))

# --- Table view ---
column_map = {
    "Member Display": header_labels["member_code"],
    "Portfolio Name": header_labels.get("portfolio_name", "Portfolio"),
    "Display Name": header_labels["stock_name"],
    "ISIN": header_labels["isin"],
    "Qty": header_labels["qty"],
    "Value At Cost": header_labels["value_cost"],
    "Value At Market Price": header_labels["value_market"],
    "Profit %": header_labels["profit_pct"],
    "Beta (1Y)": header_labels["beta"]
}
table_columns = list(column_map.keys())

styled_df = filtered_df[table_columns].rename(columns=column_map).style.format({
    column_map["Profit %"]: lambda x: f"{x:.2f}%" if isinstance(x, (int, float)) else x
}).applymap(
    lambda val: "color: red" if isinstance(val, (int, float)) and val < 0 else "color: green",
    subset=[column_map["Profit %"]]
)
st.subheader(labels["table_title"])
st.dataframe(styled_df, use_container_width=True)

# --- Excel Export ---
export_df = filtered_df[table_columns].rename(columns=column_map)
buffer = BytesIO()
#with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
 #   export_df.to_excel(writer, index=False, sheet_name="Portfolio")
   # writer.save()
st.download_button(
    label=labels["export_excel"],
    data=buffer.getvalue(),
    file_name="portfolio_dashboard.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
