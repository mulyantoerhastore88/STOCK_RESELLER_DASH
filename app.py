import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import re

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

# --- 3. DATA LOADER DARI GOOGLE DRIVE FOLDER ---
@st.cache_data(ttl=300)
def load_data():
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ]
        
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Secrets 'gcp_service_account' belum di-set!")
            return pd.DataFrame()

        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # ID folder dari URL yang diberikan
        folder_id = "1hSnG1XP-nsw1CbhLlHRo_PiiN45IHbXu"
        
        # Karena gspread tidak support listing folder secara langsung,
        # kita akan menggunakan workaround:
        # 1. Gunakan Google Drive API via REST API sederhana
        # 2. Atau gunakan spreadsheet ID yang sudah diketahui
        
        # SOLUSI: Coba beberapa approach
        
        # Approach 1: Jika ada spreadsheet ID di secrets
        if "stock_spreadsheet_id" in st.secrets:
            try:
                spreadsheet_id = st.secrets["stock_spreadsheet_id"]
                sh = client.open_by_key(spreadsheet_id)
                worksheet = sh.get_worksheet(0)
                data = worksheet.get_all_records()
                df = pd.DataFrame(data)
                st.sidebar.success(f"✅ Load dari spreadsheet ID di secrets")
                return df
            except Exception as e:
                st.sidebar.warning(f"⚠️ Gagal load dari secrets: {str(e)}")
        
        # Approach 2: Coba akses spreadsheet yang berisi kata 'Stock' di nama
        try:
            # List semua spreadsheet yang bisa diakses
            spreadsheet_list = []
            
            # Kita akan coba beberapa spreadsheet yang mungkin
            possible_spreadsheets = [
                "https://docs.google.com/spreadsheets/d/1HfC0mLgfSaRa64dd3II6HFY1gTTeVt9WBTBUC5nfwac/edit",
                # Tambahkan URL spreadsheet lain jika perlu
            ]
            
            for url in possible_spreadsheets:
                try:
                    sh = client.open_by_url(url)
                    spreadsheet_title = sh.title
                    
                    # Cek apakah judul mengandung kata 'Stock'
                    if 'stock' in spreadsheet_title.lower():
                        st.sidebar.info(f"📁 Found spreadsheet: {spreadsheet_title}")
                        worksheet = sh.get_worksheet(0)
                        data = worksheet.get_all_records()
                        df = pd.DataFrame(data)
                        st.sidebar.success(f"✅ Load dari: {spreadsheet_title}")
                        return df
                except:
                    continue
            
            # Jika tidak ada yang mengandung 'Stock', ambil spreadsheet pertama
            if possible_spreadsheets:
                try:
                    sh = client.open_by_url(possible_spreadsheets[0])
                    worksheet = sh.get_worksheet(0)
                    data = worksheet.get_all_records()
                    df = pd.DataFrame(data)
                    st.sidebar.warning(f"⚠️ Menggunakan spreadsheet backup: {sh.title}")
                    return df
                except Exception as e:
                    st.sidebar.error(f"❌ Error backup: {str(e)}")
                    
        except Exception as e:
            st.sidebar.error(f"❌ Error mencari spreadsheet: {str(e)}")
            
        # Fallback: coba file dari URL lama
        try:
            spreadsheet_url = "https://docs.google.com/spreadsheets/d/1HfC0mLgfSaRa64dd3II6HFY1gTTeVt9WBTBUC5nfwac/edit?usp=sharing"
            sh = client.open_by_url(spreadsheet_url)
            worksheet = sh.get_worksheet(0)
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
            st.sidebar.warning("⚠️ Menggunakan spreadsheet URL default")
            return df
        except Exception as e:
            st.error(f"❌ Semua metode gagal: {str(e)}")
            
        return pd.DataFrame()
            
    except Exception as e:
        st.error(f"🔥 Koneksi Gagal: {str(e)}")
        return pd.DataFrame()

# --- 4. DATA PROCESSING ---
def process_data(df):
    if df.empty: 
        st.warning("⚠️ Dataframe kosong")
        return df
    
    # Tampilkan info kolom di sidebar
    st.sidebar.info(f"📋 Kolom yang ditemukan ({len(df.columns)}):")
    st.sidebar.write(list(df.columns))
    
    if len(df) > 0:
        st.sidebar.info(f"📊 Sample data (baris pertama):")
        sample_row = df.iloc[0].to_dict()
        # Tampilkan hanya beberapa kolom pertama agar tidak terlalu panjang
        for i, (key, value) in enumerate(sample_row.items()):
            if i < 5:  # Tampilkan 5 kolom pertama saja
                st.sidebar.write(f"  {key}: {value}")
    
    # 1. Filter untuk Storage Location = F213
    if 'Storage Location' in df.columns:
        df = df[df['Storage Location'] == 'F213'].copy()
        st.sidebar.success(f"✅ Filtered F213: {len(df)} rows")
    else:
        # Coba cari kolom lain untuk filter
        location_cols = [col for col in df.columns if 'location' in col.lower() or 'storage' in col.lower()]
        if location_cols:
            location_col = location_cols[0]
            if 'F213' in df[location_col].astype(str).values:
                df = df[df[location_col].astype(str) == 'F213'].copy()
                st.sidebar.success(f"✅ Filtered F213 dari kolom {location_col}: {len(df)} rows")
    
    # 2. Convert Unrestricted to numeric
    if 'Unrestricted' in df.columns:
        df['Unrestricted'] = pd.to_numeric(df['Unrestricted'], errors='coerce').fillna(0)
        total_stock = df['Unrestricted'].sum()
        st.sidebar.success(f"✅ Total Stock: {total_stock:,.0f} unit")
    else:
        # Cari kolom stock alternatif
        stock_cols = [col for col in df.columns if any(word in col.lower() for word in ['stock', 'qty', 'quantity', 'unrestricted'])]
        if stock_cols:
            df['Unrestricted'] = pd.to_numeric(df[stock_cols[0]], errors='coerce').fillna(0)
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{stock_cols[0]}' sebagai Unrestricted")
        else:
            st.sidebar.error("❌ Kolom stock tidak ditemukan!")
            df['Unrestricted'] = 0
    
    # 3. Convert Remaining Expiry Date to numeric
    if 'Remaining Expiry Date' in df.columns:
        df['Remaining Expiry Date'] = pd.to_numeric(df['Remaining Expiry Date'], errors='coerce').fillna(0)
    else:
        # Cari kolom expiry alternatif
        expiry_cols = [col for col in df.columns if any(word in col.lower() for word in ['expiry', 'remaining', 'shelf', 'day'])]
        if expiry_cols:
            df['Remaining Expiry Date'] = pd.to_numeric(df[expiry_cols[0]], errors='coerce').fillna(0)
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{expiry_cols[0]}' sebagai Expiry Date")
        else:
            st.sidebar.warning("⚠️ Kolom expiry tidak ditemukan")
            df['Remaining Expiry Date'] = 0
    
    # 4. Create Status and Umur columns
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
    
    # 5. Cek apakah kolom Material dan Description ada
    if 'Material' not in df.columns:
        # Cari kolom material alternatif
        material_cols = [col for col in df.columns if any(word in col.lower() for word in ['material', 'sku', 'code', 'item'])]
        if material_cols:
            df['Material'] = df[material_cols[0]]
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{material_cols[0]}' sebagai Material")
    
    if 'Material Description' not in df.columns:
        # Cari kolom description alternatif
        desc_cols = [col for col in df.columns if any(word in col.lower() for word in ['description', 'name', 'product'])]
        if desc_cols:
            df['Material Description'] = df[desc_cols[0]]
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{desc_cols[0]}' sebagai Material Description")
    
    # 6. Cek apakah kolom Product Hierarchy 2 ada
    if 'Product Hierarchy 2' not in df.columns:
        # Cari kolom brand alternatif
        brand_cols = [col for col in df.columns if any(word in col.lower() for word in ['brand', 'hierarchy', 'product', 'category'])]
        if brand_cols:
            df['Product Hierarchy 2'] = df[brand_cols[0]]
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{brand_cols[0]}' sebagai Product Hierarchy 2")
    
    # 7. Cek apakah kolom Batch ada
    if 'Batch' not in df.columns:
        # Cari kolom batch alternatif
        batch_cols = [col for col in df.columns if any(word in col.lower() for word in ['batch', 'lot', 'serial'])]
        if batch_cols:
            df['Batch'] = df[batch_cols[0]]
    
    return df

# --- 5. MAIN UI ---
def main():
    # --- HEADER ---
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("📦 F213 Inventory Command Center")
        st.caption("Monitoring Real-time Stock Reseller & Expiry Health - Auto-detect from Drive")
    with c2:
        if st.button("🔄 Refresh Live Data", type="primary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown(f"<div style='text-align: right; color: #6b7280; font-size: 12px;'>Last Sync: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

    # Load data
    with st.spinner("🔄 Mencari file 'Stock' di Google Drive..."):
        raw_df = load_data()
    
    if raw_df.empty:
        st.error("❌ Gagal memuat data. Periksa koneksi dan service account.")
        st.info("**Tips:**")
        st.info("1. Pastikan service account punya akses ke folder Google Drive")
        st.info("2. Tambahkan spreadsheet ID di Streamlit Secrets dengan key 'stock_spreadsheet_id'")
        st.info("3. Pastikan file mengandung kata 'Stock' di nama file")
        return
    
    # Process data
    df = process_data(raw_df)
    
    if df.empty:
        st.warning("⚠️ Tidak ada data untuk F213 setelah filter")
        # Tampilkan raw data untuk debugging
        st.subheader("📋 Raw Data (10 baris pertama):")
        st.dataframe(raw_df.head(10), use_container_width=True)
        return

    st.markdown("---")

    # --- KPI CARDS ---
    total_qty = df['Unrestricted'].sum()
    total_sku = df['Material'].nunique() if 'Material' in df.columns else len(df)
    
    critical_qty = df[df['Status'] == 'Critical']['Unrestricted'].sum()
    critical_sku_count = df[df['Status'] == 'Critical']['Material'].nunique() if 'Material' in df.columns else len(df[df['Status'] == 'Critical'])
    
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
                st.info("Kolom Brand tidak ditemukan")

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
        
        alert_df = df[df['Remaining Expiry Date'] < 540].copy()
        
        # Tentukan kolom yang akan ditampilkan
        display_cols = []
        if 'Material' in alert_df.columns:
            display_cols.append('Material')
        if 'Material Description' in alert_df.columns:
            display_cols.append('Material Description')
        if 'Batch' in alert_df.columns:
            display_cols.append('Batch')
        
        display_cols.extend(['Unrestricted', 'Umur (Bulan)', 'Status'])
        
        if not alert_df.empty:
            alert_df = alert_df[display_cols].sort_values('Umur (Bulan)')
            
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
            # Buat search key
            if 'Material' in temp_df.columns and 'Material Description' in temp_df.columns:
                temp_df['Search_Key'] = temp_df['Material'].astype(str) + " | " + temp_df['Material Description'].astype(str)
            elif 'Material' in temp_df.columns:
                temp_df['Search_Key'] = temp_df['Material'].astype(str)
            elif 'Material Description' in temp_df.columns:
                temp_df['Search_Key'] = temp_df['Material Description'].astype(str)
            else:
                temp_df['Search_Key'] = temp_df.index.astype(str)
            
            search_list = sorted(temp_df['Search_Key'].unique().tolist())
            selected_item = st.selectbox("🔍 Cari SKU / Nama Produk:", search_list)

        if selected_item:
            # Parse selected item
            if " | " in selected_item:
                sel_code = selected_item.split(" | ")[0]
            else:
                sel_code = selected_item
            
            # Cari data
            if 'Material' in df.columns:
                item_data = df[df['Material'].astype(str) == sel_code]
            elif 'Search_Key' in temp_df.columns:
                item_data = temp_df[temp_df['Search_Key'] == selected_item]
            else:
                item_data = pd.DataFrame()
            
            if not item_data.empty:
                with st.container():
                    # Tampilkan header
                    if 'Material Description' in item_data.columns:
                        desc = item_data['Material Description'].iloc[0]
                    else:
                        desc = "N/A"
                    
                    if 'Product Hierarchy 2' in item_data.columns:
                        brand = item_data['Product Hierarchy 2'].iloc[0]
                    else:
                        brand = "N/A"
                    
                    st.markdown(f"""
                    <div style='background-color: white; padding: 20px; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 20px;'>
                        <h3 style='margin:0; color: #1f2937;'>📦 {desc}</h3>
                        <p style='color: #6b7280;'>SKU: <b>{sel_code}</b> &nbsp;|&nbsp; Brand: <b>{brand}</b></p>
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
                    
                    # Tampilkan kolom yang tersedia
                    display_cols = []
                    for col in ['Batch', 'Unrestricted', 'Umur (Bulan)', 'Status', 'Remaining Expiry Date']:
                        if col in item_data.columns:
                            display_cols.append(col)
                    
                    if display_cols:
                        detail_view = item_data[display_cols]
                        if 'Umur (Bulan)' in display_cols:
                            detail_view = detail_view.sort_values('Umur (Bulan)')
                        
                        if 'Status' in display_cols:
                            def highlight_row(val):
                                if val == 'Critical': return 'background-color: #fee2e2; color: #991b1b'
                                elif val == 'Warning': return 'background-color: #fef3c7; color: #92400e'
                                elif val == 'Safe': return 'background-color: #d1fae5; color: #065f46'
                                else: return ''
                            
                            st.dataframe(
                                detail_view.style.applymap(highlight_row, subset=['Status']),
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.dataframe(detail_view, use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(item_data, use_container_width=True, hide_index=True)
            else:
                st.warning("Data tidak ditemukan")

if __name__ == "__main__":
    main()
