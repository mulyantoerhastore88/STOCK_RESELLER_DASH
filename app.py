import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="F213 Inventory Command Center",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: scale(1.02);
        box-shadow: 0 6px 8px rgba(0,0,0,0.1);
    }
    h1 { color: #1f2937; font-family: 'Helvetica Neue', sans-serif; font-weight: 700; }
    h3 { color: #374151; padding-top: 10px; }
    section[data-testid="stSidebar"] { background-color: #111827; }
    section[data-testid="stSidebar"] h1, p { color: #f3f4f6 !important; }
</style>
""", unsafe_allow_html=True)

# --- 3. DATA LOADER ---
@st.cache_data(ttl=300)
def load_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        
        # Cek apakah secrets ada
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Secrets 'gcp_service_account' belum di-set di Streamlit Cloud!")
            return pd.DataFrame()

        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)

        spreadsheet_url = "https://docs.google.com/spreadsheets/d/1HfC0mLgfSaRa64dd3II6HFY1gTTeVt9WBTBUC5nfwac/edit?usp=sharing"
        sh = client.open_by_url(spreadsheet_url)
        worksheet = sh.get_worksheet(0)
        
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"🔥 Koneksi Gagal: {e}")
        return pd.DataFrame()

# --- 4. DATA PROCESSING ---
def process_data(df):
    if df.empty: return df
    
    # Filter F213
    if 'Storage Location' in df.columns:
        df = df[df['Storage Location'] == 'F213'].copy()
    
    # Fix Types
    numeric_cols = ['Unrestricted', 'Remaining Expiry Date']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # Logic Expiry (Hari)
    # < 360 hari (12 bulan) = Critical
    # < 540 hari (18 bulan) = Warning
    def get_status(days):
        if days < 360: return "Critical"
        elif days < 540: return "Warning"
        else: return "Safe"
        
    if 'Remaining Expiry Date' in df.columns:
        df['Status'] = df['Remaining Expiry Date'].apply(get_status)
        df['Umur (Bulan)'] = (df['Remaining Expiry Date'] / 30).round(1)
    
    return df

# --- 5. MAIN UI ---
def main():
    # --- HEADER ---
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("📦 F213 Inventory Command Center")
        st.caption("Monitoring Real-time Stock Reseller & Expiry Health")
    with c2:
        if st.button("🔄 Refresh Live Data", type="primary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown(f"<div style='text-align: right; color: grey; font-size: 12px;'>Last Sync: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

    # Load Data
    raw_df = load_data()
    df = process_data(raw_df)
    
    if df.empty:
        st.warning("⚠️ Data Kosong atau Gagal Load. Cek Secrets dan Koneksi.")
        return

    st.markdown("---")

    # --- KPI CARDS ---
    total_qty = df['Unrestricted'].sum()
    total_sku = df['Material'].nunique()
    critical_qty = df[df['Status'] == 'Critical']['Unrestricted'].sum()
    critical_sku_count = df[df['Status'] == 'Critical']['Material'].nunique()
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("📦 Total Stock", f"{total_qty:,.0f}", delta="Unit")
    kpi2.metric("🔖 Total SKU", f"{total_sku}", delta="Varian")
    kpi3.metric("🚨 Critical Qty (<12 Bln)", f"{critical_qty:,.0f}", delta="Items", delta_color="inverse")
    kpi4.metric("⚠️ SKU Berisiko", f"{critical_sku_count}", delta="Perlu Action", delta_color="inverse")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- TABS ---
    tab1, tab2 = st.tabs(["📊 EXECUTIVE SUMMARY", "🔎 SKU INSPECTOR"])

    # === TAB 1: VISUALISASI ===
    with tab1:
        row1_col1, row1_col2 = st.columns([2, 1])
        
        with row1_col1:
            st.subheader("Distribusi Brand (Top 10)")
            if 'Product Hierarchy 2' in df.columns:
                brand_grp = df.groupby('Product Hierarchy 2')['Unrestricted'].sum().reset_index().sort_values('Unrestricted', ascending=True).tail(10)
                
                fig = px.bar(brand_grp, x='Unrestricted', y='Product Hierarchy 2', 
                             text='Unrestricted', orientation='h',
                             color='Unrestricted', color_continuous_scale='Mint')
                fig.update_traces(texttemplate='%{text:.2s}', textposition='outside')
                fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", xaxis_title=None, yaxis_title=None)
                st.plotly_chart(fig, use_container_width=True)

        with row1_col2:
            st.subheader("Kesehatan Stock")
            status_grp = df.groupby('Status')['Unrestricted'].sum().reset_index()
            
            color_map = {
                "Critical": "#ef4444", # Red
                "Warning": "#f59e0b",  # Amber
                "Safe": "#10b981"      # Emerald
            }
            
            # --- FIX ERROR DISINI: Pake px.pie bukan px.donut ---
            fig_pie = px.pie(status_grp, values='Unrestricted', names='Status', 
                             color='Status', color_discrete_map=color_map, hole=0.6)
            # ----------------------------------------------------
            
            fig_pie.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_pie, use_container_width=True)

        # --- TABEL MODERN ---
        st.subheader("🚨 Stock Alert: Barang Expired < 18 Bulan")
        
        alert_df = df[df['Remaining Expiry Date'] < 540][[
            'Material', 'Material Description', 'Batch', 'Unrestricted', 'Umur (Bulan)', 'Status'
        ]].sort_values('Umur (Bulan)')

        if not alert_df.empty:
            st.dataframe(
                alert_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.SelectboxColumn(
                        "Status Kesehatan",
                        width="medium",
                        options=["Critical", "Warning", "Safe"],
                        required=True,
                    ),
                    "Umur (Bulan)": st.column_config.ProgressColumn(
                        "Sisa Umur (Bln)",
                        format="%.1f Bln",
                        min_value=0,
                        max_value=30,
                    ),
                    "Unrestricted": st.column_config.NumberColumn(
                        "Stock Qty",
                        format="%d Pcs"
                    )
                }
            )
        else:
            st.success("✅ Clean! Tidak ada barang dengan expired di bawah 18 bulan.")

    # === TAB 2: DETAIL SKU ===
    with tab2:
        col_search, col_brand = st.columns([2, 1])
        
        with col_brand:
            if 'Product Hierarchy 2' in df.columns:
                brand_opts = ["All Brands"] + sorted(df['Product Hierarchy 2'].astype(str).unique().tolist())
                sel_brand = st.selectbox("Filter Brand:", brand_opts)
                temp_df = df if sel_brand == "All Brands" else df[df['Product Hierarchy 2'] == sel_brand]
            else:
                temp_df = df
        
        with col_search:
            temp_df['Search_Key'] = temp_df['Material'].astype(str) + " | " + temp_df['Material Description']
            search_list = sorted(temp_df['Search_Key'].unique().tolist())
            selected_item = st.selectbox("🔍 Cari SKU / Nama Produk:", search_list)

        if selected_item:
            sel_code = selected_item.split(" | ")[0]
            item_data = df[df['Material'].astype(str) == sel_code]
            
            with st.container():
                st.markdown(f"### 📦 {item_data['Material Description'].iloc[0]}")
                st.markdown(f"**SKU:** `{sel_code}`")
                
                m1, m2, m3 = st.columns(3)
                m1.info(f"**Total Qty:** {item_data['Unrestricted'].sum():,.0f}")
                m2.warning(f"**Batch Termuda:** {item_data['Umur (Bulan)'].max()} Bln")
                m3.error(f"**Batch Tertua:** {item_data['Umur (Bulan)'].min()} Bln")
                
                st.markdown("#### 📅 Detail Batch & Expiry")
                
                detail_view = item_data[['Batch', 'Unrestricted', 'Expiry Date', 'Umur (Bulan)', 'Status']].sort_values('Umur (Bulan)')
                
                def highlight_row(val):
                    color = ''
                    if val == 'Critical': color = 'background-color: #fee2e2; color: #991b1b'
                    elif val == 'Warning': color = 'background-color: #fef3c7; color: #92400e'
                    else: color = 'background-color: #d1fae5; color: #065f46'
                    return color

                st.dataframe(
                    detail_view.style.applymap(highlight_row, subset=['Status']),
                    use_container_width=True,
                    hide_index=True
                )

if __name__ == "__main__":
    main()
