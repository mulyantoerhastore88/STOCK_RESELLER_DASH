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
    .stApp {
        background-color: #f8f9fa !important;
        color: #1f2937 !important;
    }
    
    p, h1, h2, h3, h4, h5, h6, span, div, li {
        color: #1f2937;
    }

    div[data-testid="stMetric"] {
        background-color: #ffffff !important;
        border: 1px solid #e0e0e0;
        padding: 15px 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    div[data-testid="stMetricLabel"] p {
        color: #6b7280 !important;
    }
    
    div[data-testid="stMetricValue"] {
        color: #111827 !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #111827 !important;
    }
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3, 
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div {
        color: #f3f4f6 !important;
    }

    .stTabs [data-baseweb="tab"] {
        color: #374151 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #000000 !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. DATA LOADER ---
@st.cache_data(ttl=300)
def load_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Secrets 'gcp_service_account' belum di-set!")
            return pd.DataFrame()

        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)

        spreadsheet_url = "https://docs.google.com/spreadsheets/d/1HfC0mLgfSaRa64dd3II6HFY1gTTeVt9WBTBUC5nfwac/edit?usp=sharing"
        sh = client.open_by_url(spreadsheet_url)
        worksheet = sh.get_worksheet(0)
        
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Tampilkan info kolom untuk debugging
        st.sidebar.info(f"📋 Jumlah kolom: {len(df.columns)}")
        st.sidebar.info(f"📋 Kolom yang ada: {list(df.columns)}")
        st.sidebar.info(f"📋 Sample Unrestricted value: {df['Unrestricted'].iloc[0] if 'Unrestricted' in df.columns else 'Kolom tidak ada'}")
        
        return df
    except Exception as e:
        st.error(f"🔥 Koneksi Gagal: {e}")
        return pd.DataFrame()

# --- 4. DATA PROCESSING ---
def process_data(df):
    if df.empty: 
        return df
    
    # Filter untuk F213
    if 'Storage Location' in df.columns:
        df = df[df['Storage Location'] == 'F213'].copy()
        st.sidebar.success(f"✅ Filtered F213: {len(df)} rows")
    
    # Convert Unrestricted to numeric
    if 'Unrestricted' in df.columns:
        df['Unrestricted'] = pd.to_numeric(df['Unrestricted'], errors='coerce').fillna(0)
        st.sidebar.success(f"✅ Unrestricted total: {df['Unrestricted'].sum():,.0f}")
    else:
        st.sidebar.error("❌ Kolom 'Unrestricted' tidak ditemukan!")
        return pd.DataFrame()
    
    # Convert Remaining Expiry Date to numeric
    if 'Remaining Expiry Date' in df.columns:
        df['Remaining Expiry Date'] = pd.to_numeric(df['Remaining Expiry Date'], errors='coerce').fillna(0)
        st.sidebar.success(f"✅ Expiry data loaded")
    else:
        st.sidebar.warning("⚠️ Kolom 'Remaining Expiry Date' tidak ditemukan")
    
    # Create Status column
    if 'Remaining Expiry Date' in df.columns:
        def get_status(days):
            try:
                days = float(days)
                if days < 360: return "Critical"
                elif days < 540: return "Warning"
                else: return "Safe"
            except:
                return "Unknown"
        
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
        st.markdown(f"<div style='text-align: right; color: #6b7280; font-size: 12px;'>Last Sync: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

    raw_df = load_data()
    df = process_data(raw_df)
    
    if df.empty:
        st.warning("⚠️ Data Kosong. Cek koneksi Google Sheet atau filter F213.")
        return

    # Tampilkan info data
    st.info(f"📊 Data berhasil dimuat: {len(df)} baris, Total Stock: {df['Unrestricted'].sum():,.0f} unit")
    
    st.markdown("---")

    # --- KPI CARDS ---
    total_qty = df['Unrestricted'].sum()
    total_sku = df['Material'].nunique()
    
    if 'Status' in df.columns:
        critical_qty = df[df['Status'] == 'Critical']['Unrestricted'].sum()
        critical_sku_count = df[df['Status'] == 'Critical']['Material'].nunique()
    else:
        critical_qty = 0
        critical_sku_count = 0
    
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
                fig.update_traces(texttemplate='%{text:.2s}', textposition='outside', textfont_color='black')
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", 
                    paper_bgcolor="rgba(0,0,0,0)", 
                    xaxis_title=None, 
                    yaxis_title=None,
                    font=dict(color="#1f2937")
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Kolom 'Product Hierarchy 2' tidak ditemukan")

        with row1_col2:
            st.subheader("Kesehatan Stock")
            if 'Status' in df.columns:
                status_grp = df.groupby('Status')['Unrestricted'].sum().reset_index()
                color_map = {"Critical": "#ef4444", "Warning": "#f59e0b", "Safe": "#10b981"}
                
                fig_pie = px.pie(status_grp, values='Unrestricted', names='Status', 
                                 color='Status', color_discrete_map=color_map, hole=0.6)
                fig_pie.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", 
                    paper_bgcolor="rgba(0,0,0,0)", 
                    legend=dict(orientation="h", y=-0.1),
                    font=dict(color="#1f2937")
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Data status tidak tersedia")

        st.subheader("🚨 Stock Alert: Barang Expired < 18 Bulan")
        
        if 'Remaining Expiry Date' in df.columns:
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
        else:
            st.info("Data expiry date tidak ditemukan")

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
            
            if not item_data.empty:
                with st.container():
                    st.markdown(f"""
                    <div style='background-color: white; padding: 20px; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 20px;'>
                        <h3 style='margin:0; color: #1f2937;'>📦 {item_data['Material Description'].iloc[0]}</h3>
                        <p style='color: #6b7280;'>SKU: <b>{sel_code}</b> &nbsp;|&nbsp; Brand: <b>{item_data['Product Hierarchy 2'].iloc[0]}</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    m1, m2, m3 = st.columns(3)
                    m1.info(f"**Total Qty:** {item_data['Unrestricted'].sum():,.0f}")
                    
                    if 'Umur (Bulan)' in item_data.columns:
                        m2.warning(f"**Batch Termuda:** {item_data['Umur (Bulan)'].max()} Bln")
                        m3.error(f"**Batch Tertua:** {item_data['Umur (Bulan)'].min()} Bln")
                    else:
                        m2.warning("**Batch Termuda:** N/A")
                        m3.error("**Batch Tertua:** N/A")
                    
                    st.markdown("#### 📅 Detail Batch & Expiry")
                    
                    # Tentukan kolom yang akan ditampilkan
                    display_cols = ['Batch', 'Unrestricted']
                    if 'Expiry Date' in item_data.columns:
                        display_cols.append('Expiry Date')
                    if 'Umur (Bulan)' in item_data.columns:
                        display_cols.append('Umur (Bulan)')
                    if 'Status' in item_data.columns:
                        display_cols.append('Status')
                    
                    detail_view = item_data[display_cols]
                    
                    if 'Umur (Bulan)' in display_cols:
                        detail_view = detail_view.sort_values('Umur (Bulan)')
                    
                    if 'Status' in display_cols:
                        def highlight_row(val):
                            if val == 'Critical': return 'background-color: #fee2e2; color: #991b1b'
                            elif val == 'Warning': return 'background-color: #fef3c7; color: #92400e'
                            else: return 'background-color: #d1fae5; color: #065f46'

                        st.dataframe(
                            detail_view.style.applymap(highlight_row, subset=['Status']),
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.dataframe(detail_view, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
