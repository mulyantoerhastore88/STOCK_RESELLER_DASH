import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Reseller Stock (F213)",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS FOR MODERN UI ---
st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        font-size: 24px;
    }
    .stAlert {
        padding: 0.5rem;
    }
    .big-font {
        font-size:18px !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- CACHED DATA LOADING ---
@st.cache_data(ttl=300)
def load_data():
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)

        # URL Sheet Bapak
        spreadsheet_url = "https://docs.google.com/spreadsheets/d/1HfC0mLgfSaRa64dd3II6HFY1gTTeVt9WBTBUC5nfwac/edit?usp=sharing"
        sh = client.open_by_url(spreadsheet_url)
        worksheet = sh.get_worksheet(0)
        
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"Gagal koneksi ke GSheet: {e}")
        return pd.DataFrame()

# --- PREPROCESSING ---
def process_data(df):
    if df.empty: return df
    
    # 1. Filter F213
    df = df[df['Storage Location'] == 'F213'].copy()
    
    # 2. Fix Numeric
    numeric_cols = ['Unrestricted', 'Remaining Expiry Date']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # 3. Logic Expiry (Dalam Hari)
    # 1 Bulan ~ 30 Hari
    # 12 Bulan = 360 Hari | 18 Bulan = 540 Hari
    def get_status(days):
        if days < 360: return "🔴 Critical (< 12 Mo)"
        elif days < 540: return "🟡 Warning (12-18 Mo)"
        else: return "🟢 Safe (> 18 Mo)"
        
    df['Expiry Status'] = df['Remaining Expiry Date'].apply(get_status)
    
    # 4. Helper: Convert days to months string
    df['Umur (Bulan)'] = (df['Remaining Expiry Date'] / 30).round(1)
    
    return df

# --- MAIN APP ---
def main():
    # Sidebar
    st.sidebar.title("📦 Stock Monitor")
    st.sidebar.caption("Reseller Location: F213")
    
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    # Load Data
    raw_df = load_data()
    df = process_data(raw_df)
    
    if df.empty:
        st.warning("Data kosong atau gagal dimuat.")
        return

    # --- TOP KPI ---
    total_qty = df['Unrestricted'].sum()
    total_sku = df['Material'].nunique()
    critical_qty = df[df['Remaining Expiry Date'] < 360]['Unrestricted'].sum()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Stock (Pcs)", f"{total_qty:,.0f}")
    c2.metric("Total SKU", f"{total_sku}")
    c3.metric("Critical Stock (<12 Mo)", f"{critical_qty:,.0f}", delta="Harusnya 0", delta_color="inverse")
    c4.markdown(f"**Last Update:**\n{datetime.now().strftime('%H:%M')} WIB")

    st.markdown("---")

    # --- TABS LAYOUT ---
    tab1, tab2 = st.tabs(["📊 Dashboard Overview", "🔍 SKU Inspector (Detail)"])

    with tab1:
        # Row 1: Charts
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            st.subheader("Distribusi Brand (Hierarchy 2)")
            # Group by Hierarchy 2 (Brand)
            if 'Product Hierarchy 2' in df.columns:
                brand_grp = df.groupby('Product Hierarchy 2')['Unrestricted'].sum().reset_index()
                fig_bar = px.bar(brand_grp, x='Product Hierarchy 2', y='Unrestricted',
                                 color='Unrestricted', title="Stock per Brand",
                                 text_auto='.2s', color_continuous_scale='Blues')
                fig_bar.update_layout(xaxis_title="Brand", yaxis_title="Qty", showlegend=False)
                st.plotly_chart(fig_bar, use_container_width=True)
        
        with col_right:
            st.subheader("Kesehatan Stock (Expiry)")
            expiry_grp = df.groupby('Expiry Status')['Unrestricted'].sum().reset_index()
            # Custom Color Map
            colors = {
                "🔴 Critical (< 12 Mo)": "#FF4B4B",
                "🟡 Warning (12-18 Mo)": "#FFA15A",
                "🟢 Safe (> 18 Mo)": "#00CC96"
            }
            fig_pie = px.pie(expiry_grp, values='Unrestricted', names='Expiry Status',
                             color='Expiry Status', color_discrete_map=colors, hole=0.4)
            fig_pie.update_layout(legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_pie, use_container_width=True)

        # Row 2: Tabel Warning (Hanya menampilkan yang bermasalah)
        st.subheader("🚨 Early Warning System (Stock < 18 Bulan)")
        problem_df = df[df['Remaining Expiry Date'] < 540][
            ['Material', 'Material Description', 'Batch', 'Unrestricted', 'Umur (Bulan)', 'Expiry Status']
        ].sort_values('Umur (Bulan)')
        
        if not problem_df.empty:
            st.dataframe(problem_df, use_container_width=True, hide_index=True)
        else:
            st.success("✨ Semua stock aman! Tidak ada yang expired di bawah 18 bulan.")

    with tab2:
        st.markdown("### 🔎 Cari Detail Produk")
        
        # 1. Filter Brand (Optional)
        brand_list = ["All"] + sorted(df['Product Hierarchy 2'].astype(str).unique().tolist())
        sel_brand = st.selectbox("Filter Brand (Hierarchy 2):", brand_list)
        
        temp_df = df if sel_brand == "All" else df[df['Product Hierarchy 2'] == sel_brand]
        
        # 2. Select SKU
        # Bikin list unik: "Kode - Nama Barang"
        temp_df['Display_Name'] = temp_df['Material'].astype(str) + " - " + temp_df['Material Description']
        sku_list = sorted(temp_df['Display_Name'].unique().tolist())
        
        selected_sku_str = st.selectbox("Pilih SKU / Material:", sku_list)
        
        if selected_sku_str:
            # Ambil Material Code dari string
            sel_material_code = selected_sku_str.split(" - ")[0]
            
            # Filter Data
            sku_data = df[df['Material'].astype(str) == sel_material_code]
            
            # --- PRODUCT CARD ---
            with st.container():
                st.info(f"📦 **{selected_sku_str}**")
                
                k1, k2, k3 = st.columns(3)
                total_sku_qty = sku_data['Unrestricted'].sum()
                min_month = sku_data['Umur (Bulan)'].min()
                brand_name = sku_data['Product Hierarchy 2'].iloc[0]
                
                k1.metric("Total Qty", f"{total_sku_qty:,.0f}")
                k2.metric("Expiry Terdekat", f"{min_month} Bulan")
                k3.metric("Brand", brand_name)
                
                st.markdown("#### Detail Batch & Expiry")
                
                # Format tabel detail biar cantik
                detail_table = sku_data[['Batch', 'Unrestricted', 'Expiry Date', 'Umur (Bulan)', 'Expiry Status']].sort_values('Umur (Bulan)')
                
                # Highlight baris
                def highlight_status(val):
                    color = ''
                    if 'Critical' in val: color = 'background-color: #ffcccc' # Merah muda
                    elif 'Warning' in val: color = 'background-color: #ffeebb' # Kuning muda
                    elif 'Safe' in val: color = 'background-color: #ccffcc' # Hijau muda
                    return color

                st.dataframe(
                    detail_table.style.applymap(highlight_status, subset=['Expiry Status'])
                    .format({'Unrestricted': '{:,.0f}', 'Umur (Bulan)': '{:.1f} Bln'}),
                    use_container_width=True,
                    hide_index=True
                )

if __name__ == "__main__":
    main()
