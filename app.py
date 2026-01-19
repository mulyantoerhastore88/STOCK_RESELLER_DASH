import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import os
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

# --- 2. CUSTOM CSS (FIX WARNA & KONTRAS) ---
st.markdown("""
<style>
    /* 1. PAKSA BACKGROUND TERANG & TEKS GELAP (Global) */
    .stApp {
        background-color: #f8f9fa !important;
        color: #1f2937 !important;
    }
    
    /* 2. PAKSA SEMUA TEKS JADI HITAM/ABU TUA */
    p, h1, h2, h3, h4, h5, h6, span, div, li {
        color: #1f2937;
    }

    /* 3. Metric Cards (Kotak Angka) */
    div[data-testid="stMetric"] {
        background-color: #ffffff !important;
        border: 1px solid #e0e0e0;
        padding: 15px 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Label Metric (Judul kecil di atas angka) */
    div[data-testid="stMetricLabel"] p {
        color: #6b7280 !important; /* Abu-abu */
    }
    /* Value Metric (Angka Besar) */
    div[data-testid="stMetricValue"] {
        color: #111827 !important; /* Hitam Pekat */
    }

    /* 4. SIDEBAR (PENGECUALIAN: Background Gelap, Teks Putih) */
    section[data-testid="stSidebar"] {
        background-color: #111827 !important;
    }
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3, 
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div {
        color: #f3f4f6 !important; /* Putih */
    }

    /* 5. Tabs */
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
        
        # Build Google Drive API service
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Folder ID dari URL
        folder_id = "1hSnG1XP-nsw1CbhLlHRo_PiiN45IHbXu"
        
        # Cari file dengan kata "Stock" di dalam folder
        query = f"'{folder_id}' in parents and name contains 'Stock' and trashed = false"
        results = drive_service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            orderBy="createdTime desc"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            st.error("❌ Tidak ditemukan file dengan kata 'Stock' di folder tersebut")
            return pd.DataFrame()
        
        # Ambil file pertama yang ditemukan (bisa dimodifikasi untuk multiple files)
        target_file = files[0]
        file_id = target_file['id']
        file_name = target_file['name']
        mime_type = target_file['mimeType']
        
        st.info(f"📂 Membaca file: {file_name}")
        
        # Handle file berdasarkan tipe
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            # Jika Google Sheets langsung
            client = gspread.authorize(creds)
            sh = client.open_by_key(file_id)
            worksheet = sh.get_worksheet(0)
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
            
        elif mime_type in ['text/csv', 'application/vnd.ms-excel']:
            # Jika file CSV/Excel, download dulu
            request = drive_service.files().get_media(fileId=file_id)
            file_bytes = io.BytesIO()
            downloader = MediaIoBaseDownload(file_bytes, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            file_bytes.seek(0)
            
            if file_name.endswith('.csv'):
                df = pd.read_csv(file_bytes)
            else:  # Excel file
                df = pd.read_excel(file_bytes)
            return df
            
        else:
            st.error(f"❌ Format file tidak didukung: {mime_type}")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"🔥 Koneksi Gagal: {str(e)}")
        return pd.DataFrame()

# --- 4. DATA PROCESSING ---
def process_data(df):
    if df.empty: return df
    
    # Cek format data yang ada
    st.info(f"📊 Format data yang ditemukan: {list(df.columns)}")
    
    # Cari kolom yang mungkin berisi Storage Location
    storage_col = None
    for col in df.columns:
        if 'storage' in col.lower() or 'location' in col.lower():
            storage_col = col
            break
    
    if storage_col:
        df = df[df[storage_col] == 'F213'].copy()
    
    # Cari kolom untuk Unrestricted stock
    unrestricted_col = None
    for col in df.columns:
        if 'unrestricted' in col.lower() or 'stock' in col.lower() or 'qty' in col.lower():
            unrestricted_col = col
            break
    
    # Cari kolom untuk Expiry Date
    expiry_col = None
    for col in df.columns:
        if 'expiry' in col.lower() or 'remaining' in col.lower() or 'shelf' in col.lower():
            expiry_col = col
            break
    
    numeric_cols = []
    if unrestricted_col:
        numeric_cols.append(unrestricted_col)
    if expiry_col:
        numeric_cols.append(expiry_col)
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    def get_status(days):
        if days < 360: return "Critical"
        elif days < 540: return "Warning"
        else: return "Safe"
        
    if expiry_col:
        df['Status'] = df[expiry_col].apply(get_status)
        df['Umur (Bulan)'] = (df[expiry_col] / 30).round(1)
        df['Remaining Expiry Date'] = df[expiry_col]  # Untuk backward compatibility
    
    if unrestricted_col:
        df['Unrestricted'] = df[unrestricted_col]  # Untuk backward compatibility
    
    return df

# --- 5. MAIN UI ---
def main():
    # --- HEADER ---
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("📦 F213 Inventory Command Center")
        st.caption("Monitoring Real-time Stock Reseller & Expiry Health - Auto-detect from Drive Folder")
    with c2:
        if st.button("🔄 Refresh Live Data", type="primary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown(f"<div style='text-align: right; color: #6b7280; font-size: 12px;'>Last Sync: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

    raw_df = load_data()
    df = process_data(raw_df)
    
    if df.empty:
        st.warning("⚠️ Data Kosong. Cek koneksi Google Drive atau format file.")
        return

    st.markdown("---")

    # --- KPI CARDS ---
    total_qty = df['Unrestricted'].sum() if 'Unrestricted' in df.columns else 0
    total_sku = df['Material'].nunique() if 'Material' in df.columns else 0
    critical_qty = df[df['Status'] == 'Critical']['Unrestricted'].sum() if 'Status' in df.columns else 0
    critical_sku_count = df[df['Status'] == 'Critical']['Material'].nunique() if 'Status' in df.columns else 0
    
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
            # Cari kolom untuk Brand/Product Hierarchy
            brand_col = None
            for col in df.columns:
                if 'product' in col.lower() or 'hierarchy' in col.lower() or 'brand' in col.lower():
                    brand_col = col
                    break
            
            if brand_col and 'Unrestricted' in df.columns:
                brand_grp = df.groupby(brand_col)['Unrestricted'].sum().reset_index().sort_values('Unrestricted', ascending=True).tail(10)
                
                fig = px.bar(brand_grp, x='Unrestricted', y=brand_col, 
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
                st.info("Kolom Brand tidak ditemukan di data")

        with row1_col2:
            st.subheader("Kesehatan Stock")
            if 'Status' in df.columns and 'Unrestricted' in df.columns:
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
            alert_df = df[df['Remaining Expiry Date'] < 540].copy()
            
            # Cari kolom yang sesuai
            material_col = 'Material' if 'Material' in df.columns else df.columns[0]
            desc_col = 'Material Description' if 'Material Description' in df.columns else df.columns[1]
            batch_col = 'Batch' if 'Batch' in df.columns else df.columns[2]
            
            if not alert_df.empty:
                alert_df = alert_df[[
                    material_col, desc_col, batch_col, 'Unrestricted', 'Umur (Bulan)', 'Status'
                ]].sort_values('Umur (Bulan)')
                
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
        
        # Cari kolom untuk Brand
        brand_col = None
        for col in df.columns:
            if 'product' in col.lower() or 'hierarchy' in col.lower() or 'brand' in col.lower():
                brand_col = col
                break
        
        with col_brand:
            if brand_col:
                brand_opts = ["All Brands"] + sorted(df[brand_col].astype(str).unique().tolist())
                sel_brand = st.selectbox("Filter Brand:", brand_opts)
                temp_df = df if sel_brand == "All Brands" else df[df[brand_col] == sel_brand]
            else:
                temp_df = df
        
        with col_search:
            # Cari kolom untuk Material dan Description
            material_col = 'Material' if 'Material' in temp_df.columns else temp_df.columns[0]
            desc_col = 'Material Description' if 'Material Description' in temp_df.columns else temp_df.columns[1]
            
            temp_df['Search_Key'] = temp_df[material_col].astype(str) + " | " + temp_df[desc_col].astype(str)
            search_list = sorted(temp_df['Search_Key'].unique().tolist())
            selected_item = st.selectbox("🔍 Cari SKU / Nama Produk:", search_list)

        if selected_item:
            sel_code = selected_item.split(" | ")[0]
            item_data = df[df[material_col].astype(str) == sel_code]
            
            if not item_data.empty:
                with st.container():
                    st.markdown(f"""
                    <div style='background-color: white; padding: 20px; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 20px;'>
                        <h3 style='margin:0; color: #1f2937;'>📦 {item_data[desc_col].iloc[0]}</h3>
                        <p style='color: #6b7280;'>SKU: <b>{sel_code}</b> &nbsp;|&nbsp; Brand: <b>{item_data[brand_col].iloc[0] if brand_col else 'N/A'}</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    m1, m2, m3 = st.columns(3)
                    m1.info(f"**Total Qty:** {item_data['Unrestricted'].sum():,.0f}")
                    m2.warning(f"**Batch Termuda:** {item_data['Umur (Bulan)'].max() if 'Umur (Bulan)' in item_data.columns else 'N/A'} Bln")
                    m3.error(f"**Batch Tertua:** {item_data['Umur (Bulan)'].min() if 'Umur (Bulan)' in item_data.columns else 'N/A'} Bln")
                    
                    st.markdown("#### 📅 Detail Batch & Expiry")
                    
                    if 'Batch' in item_data.columns and 'Umur (Bulan)' in item_data.columns:
                        detail_view = item_data[['Batch', 'Unrestricted', 'Umur (Bulan)', 'Status']].sort_values('Umur (Bulan)')
                        
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
                        st.info("Data batch tidak lengkap")
            else:
                st.warning("Data tidak ditemukan")

if __name__ == "__main__":
    main()
