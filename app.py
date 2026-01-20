import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import tempfile
import os

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

# --- 3. DATA LOADER DARI GOOGLE DRIVE FOLDER (REAL) ---
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
        
        # Inisialisasi Google Drive API
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Folder ID dari URL: https://drive.google.com/drive/folders/1hSnG1XP-nsw1CbhLlHRo_PiiN45IHbXu
        folder_id = "1hSnG1XP-nsw1CbhLlHRo_PiiN45IHbXu"
        
        # Cari file dengan kata "Stock" di dalam folder
        query = f"'{folder_id}' in parents and (name contains 'Stock' or name contains 'stock') and trashed = false"
        
        st.sidebar.info("🔍 Mencari file 'Stock' di Google Drive...")
        
        results = drive_service.files().list(
            q=query,
            fields="files(id, name, mimeType, createdTime)",
            orderBy="createdTime desc"  # Ambil yang terbaru
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            st.error("❌ Tidak ditemukan file dengan kata 'Stock' di folder tersebut!")
            st.info(f"Folder ID: {folder_id}")
            st.info("Pastikan:")
            st.info("1. Service account punya akses ke folder")
            st.info("2. File mengandung kata 'Stock' di nama file")
            return pd.DataFrame()
        
        # Tampilkan file yang ditemukan
        st.sidebar.success(f"✅ Ditemukan {len(files)} file dengan kata 'Stock'")
        for file in files:
            st.sidebar.info(f"📄 {file['name']} ({file['mimeType']})")
        
        # Ambil file terbaru (yang paling baru dibuat/diupdate)
        latest_file = files[0]  # Karena sudah diurutkan desc by createdTime
        file_id = latest_file['id']
        file_name = latest_file['name']
        mime_type = latest_file['mimeType']
        
        st.sidebar.success(f"📂 Menggunakan file terbaru: {file_name}")
        
        # Handle berdasarkan tipe file
        if mime_type == 'application/vnd.google-apps.spreadsheet':
            # Jika Google Sheets
            st.sidebar.info("📊 Membaca Google Sheets...")
            client = gspread.authorize(creds)
            sh = client.open_by_key(file_id)
            worksheet = sh.get_worksheet(0)
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
            st.sidebar.success(f"✅ Berhasil load {len(df)} baris dari Google Sheets")
            
        elif mime_type in ['text/csv', 'application/vnd.ms-excel', 
                          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
            # Jika file CSV atau Excel
            st.sidebar.info("📊 Mendownload file CSV/Excel...")
            request = drive_service.files().get_media(fileId=file_id)
            file_bytes = io.BytesIO()
            downloader = MediaIoBaseDownload(file_bytes, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            file_bytes.seek(0)
            
            # Baca file berdasarkan tipe
            if file_name.endswith('.csv'):
                df = pd.read_csv(file_bytes)
            else:  # Excel file
                df = pd.read_excel(file_bytes)
            
            st.sidebar.success(f"✅ Berhasil load {len(df)} baris dari {file_name}")
            
        else:
            st.error(f"❌ Format file tidak didukung: {mime_type}")
            return pd.DataFrame()
        
        return df
            
    except Exception as e:
        st.error(f"🔥 Error: {str(e)}")
        return pd.DataFrame()

# --- 4. DATA PROCESSING ---
def process_data(df):
    if df.empty: 
        st.warning("⚠️ Dataframe kosong")
        return df
    
    # Tampilkan info kolom
    st.sidebar.info(f"📋 Kolom yang ditemukan: {list(df.columns)}")
    
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
    
    if df.empty:
        st.sidebar.warning("⚠️ Tidak ada data untuk F213")
        return df
    
    # 2. Convert Unrestricted to numeric
    if 'Unrestricted' in df.columns:
        df['Unrestricted'] = pd.to_numeric(df['Unrestricted'], errors='coerce').fillna(0)
        total_stock = df['Unrestricted'].sum()
        st.sidebar.success(f"✅ Total Stock: {total_stock:,.0f} unit")
    else:
        # Cari kolom stock alternatif
        stock_cols = [col for col in df.columns if any(word in col.lower() for word in ['stock', 'qty', 'quantity', 'unrestricted', 'sisa'])]
        if stock_cols:
            df['Unrestricted'] = pd.to_numeric(df[stock_cols[0]], errors='coerce').fillna(0)
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{stock_cols[0]}' sebagai Unrestricted")
            total_stock = df['Unrestricted'].sum()
            st.sidebar.info(f"📦 Total Stock: {total_stock:,.0f} unit")
        else:
            st.sidebar.error("❌ Kolom stock tidak ditemukan!")
            df['Unrestricted'] = 0
    
    # 3. Convert Remaining Expiry Date to numeric
    if 'Remaining Expiry Date' in df.columns:
        df['Remaining Expiry Date'] = pd.to_numeric(df['Remaining Expiry Date'], errors='coerce').fillna(0)
    else:
        # Cari kolom expiry alternatif
        expiry_cols = [col for col in df.columns if any(word in col.lower() for word in ['expiry', 'remaining', 'shelf', 'day', 'hari'])]
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
    
    # 5. Pastikan kolom Material ada
    if 'Material' not in df.columns:
        # Cari kolom material alternatif
        material_cols = [col for col in df.columns if any(word in col.lower() for word in ['material', 'sku', 'code', 'item'])]
        if material_cols:
            df['Material'] = df[material_cols[0]].astype(str)
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{material_cols[0]}' sebagai Material")
        else:
            # Jika tidak ada, buat dari index
            df['Material'] = df.index.astype(str)
    
    # 6. Pastikan kolom Material Description ada
    if 'Material Description' not in df.columns:
        # Cari kolom description alternatif
        desc_cols = [col for col in df.columns if any(word in col.lower() for word in ['description', 'name', 'product', 'item'])]
        if desc_cols:
            df['Material Description'] = df[desc_cols[0]].astype(str)
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{desc_cols[0]}' sebagai Material Description")
        else:
            df['Material Description'] = df['Material']
    
    # 7. Pastikan kolom Product Hierarchy 2 ada
    if 'Product Hierarchy 2' not in df.columns:
        # Cari kolom brand alternatif
        brand_cols = [col for col in df.columns if any(word in col.lower() for word in ['brand', 'hierarchy', 'product', 'category', 'type'])]
        if brand_cols:
            df['Product Hierarchy 2'] = df[brand_cols[0]].astype(str)
            st.sidebar.warning(f"⚠️ Menggunakan kolom '{brand_cols[0]}' sebagai Product Hierarchy 2")
        else:
            df['Product Hierarchy 2'] = "Unknown"
    
    # 8. Pastikan kolom Batch ada
    if 'Batch' not in df.columns:
        # Cari kolom batch alternatif
        batch_cols = [col for col in df.columns if any(word in col.lower() for word in ['batch', 'lot', 'serial'])]
        if batch_cols:
            df['Batch'] = df[batch_cols[0]].astype(str)
        else:
            df['Batch'] = "N/A"
    
    return df

# --- 5. FUNGSI UNTUK PROCESSING SALES ORDER ---
def process_sales_order(so_df, stock_df):
    """
    Process Sales Order dan assign batch dari stock berdasarkan FIFO (sisa umur tersingkat)
    """
    if so_df.empty or stock_df.empty:
        return pd.DataFrame()
    
    # Buat copy untuk menghindari warning
    so_df = so_df.copy()
    stock_df = stock_df.copy()
    
    # Standardize column names
    column_mapping = {}
    for col in so_df.columns:
        col_lower = col.lower()
        if 'material' in col_lower or 'sku' in col_lower:
            column_mapping[col] = 'Material'
        elif 'quantity' in col_lower or 'qty' in col_lower:
            column_mapping[col] = 'Order Quantity'
        elif 'batch' in col_lower:
            column_mapping[col] = 'Batch'
        elif 'description' in col_lower:
            column_mapping[col] = 'Material Description'
        elif 'document' in col_lower:
            column_mapping[col] = 'Sales Document'
        elif 'delivery' in col_lower and 'date' in col_lower:
            column_mapping[col] = 'Delivery Date'
        elif 'organization' in col_lower:
            column_mapping[col] = 'Sales Organization'
    
    # Rename columns
    so_df = so_df.rename(columns=column_mapping)
    
    # Ensure required columns exist
    required_cols = ['Material', 'Order Quantity']
    for col in required_cols:
        if col not in so_df.columns:
            st.error(f"❌ Kolom '{col}' tidak ditemukan di file SO!")
            return pd.DataFrame()
    
    # Convert Order Quantity to numeric
    so_df['Order Quantity'] = pd.to_numeric(so_df['Order Quantity'], errors='coerce').fillna(0)
    
    # Prepare stock data - sort by Umur (Bulan) ascending (FIFO: sisa umur tersingkat duluan)
    stock_df = stock_df.sort_values(['Material', 'Umur (Bulan)'], ascending=[True, True])
    
    # Create result dataframe
    results = []
    
    # Process each SO line
    for idx, row in so_df.iterrows():
        material = str(row['Material'])
        order_qty = row['Order Quantity']
        
        # Get available stock for this material
        material_stock = stock_df[stock_df['Material'].astype(str) == material].copy()
        
        if material_stock.empty:
            # No stock available
            result_row = row.to_dict()
            result_row['Assigned Batch'] = 'NO STOCK'
            result_row['Assigned Qty'] = 0
            result_row['Remaining Qty'] = order_qty
            result_row['Status'] = 'NO STOCK'
            results.append(result_row)
            continue
        
        # Calculate total available stock
        total_available = material_stock['Unrestricted'].sum()
        
        if total_available == 0:
            # Stock exists but quantity is 0
            result_row = row.to_dict()
            result_row['Assigned Batch'] = 'OUT OF STOCK'
            result_row['Assigned Qty'] = 0
            result_row['Remaining Qty'] = order_qty
            result_row['Status'] = 'OUT OF STOCK'
            results.append(result_row)
            continue
        
        if order_qty > total_available:
            # Partial fulfillment
            result_row = row.to_dict()
            result_row['Assigned Batch'] = 'INSUFFICIENT STOCK'
            result_row['Assigned Qty'] = total_available
            result_row['Remaining Qty'] = order_qty - total_available
            result_row['Status'] = 'PARTIAL'
            results.append(result_row)
            continue
        
        # Assign batch based on FIFO (sisa umur tersingkat duluan)
        remaining_qty = order_qty
        batch_assignments = []
        
        for _, stock_row in material_stock.iterrows():
            if remaining_qty <= 0:
                break
            
            batch_qty = min(stock_row['Unrestricted'], remaining_qty)
            if batch_qty > 0:
                batch_assignments.append({
                    'Batch': stock_row['Batch'],
                    'Qty': batch_qty,
                    'Umur (Bulan)': stock_row['Umur (Bulan)'],
                    'Status': stock_row['Status']
                })
                remaining_qty -= batch_qty
        
        # Format batch assignments
        if batch_assignments:
            batch_str = ', '.join([f"{b['Batch']} ({b['Qty']}pcs)" for b in batch_assignments])
            result_row = row.to_dict()
            result_row['Assigned Batch'] = batch_str
            result_row['Assigned Qty'] = order_qty - remaining_qty
            result_row['Remaining Qty'] = remaining_qty
            result_row['Status'] = 'FULLFILLED'
            result_row['Batch Details'] = str(batch_assignments)
            results.append(result_row)
    
    # Create results dataframe
    result_df = pd.DataFrame(results)
    
    # Reorder columns for better readability
    preferred_order = [
        'Sales Organization', 'Delivery Date', 'Sales Document',
        'Material', 'Material Description', 'Order Quantity',
        'Assigned Batch', 'Assigned Qty', 'Remaining Qty', 'Status'
    ]
    
    # Only include columns that exist
    existing_cols = [col for col in preferred_order if col in result_df.columns]
    other_cols = [col for col in result_df.columns if col not in existing_cols]
    
    result_df = result_df[existing_cols + other_cols]
    
    return result_df

# --- 6. MAIN UI ---
def main():
    # --- HEADER ---
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("📦 F213 Inventory Command Center")
        st.caption("Monitoring Real-time Stock Reseller & Expiry Health - Auto-detect from Google Drive")
    with c2:
        if st.button("🔄 Refresh Live Data", type="primary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.markdown(f"<div style='text-align: right; color: #6b7280; font-size: 12px;'>Last Sync: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

    # Load data
    with st.spinner("🔍 Scanning Google Drive folder untuk file 'Stock'..."):
        raw_df = load_data()
    
    if raw_df.empty:
        st.error("❌ Gagal memuat data.")
        return
    
    # Process data
    df = process_data(raw_df)
    
    if df.empty:
        st.warning("⚠️ Tidak ada data untuk F213 setelah filter")
        # Tampilkan sample raw data
        if not raw_df.empty:
            with st.expander("📋 Lihat raw data (10 baris pertama)"):
                st.dataframe(raw_df.head(10), use_container_width=True)
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
    tab1, tab2, tab3, tab4 = st.tabs(["📊 EXECUTIVE SUMMARY", "🔎 SKU INSPECTOR", "📋 BATCH INVENTORY", "📄 SALES ORDER PROCESSING"])

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
            temp_df['Search_Key'] = temp_df['Material'].astype(str) + " | " + temp_df['Material Description'].astype(str)
            search_list = sorted(temp_df['Search_Key'].unique().tolist())
            selected_item = st.selectbox("🔍 Cari SKU / Nama Produk:", search_list)

        if selected_item:
            # Parse selected item
            sel_code = selected_item.split(" | ")[0]
            
            # Cari data
            item_data = df[df['Material'].astype(str) == sel_code]
            
            if not item_data.empty:
                with st.container():
                    # Tampilkan header
                    desc = item_data['Material Description'].iloc[0]
                    brand = item_data['Product Hierarchy 2'].iloc[0]
                    
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
                    for col in ['Batch', 'Unrestricted', 'Umur (Bulan)', 'Status']:
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

    # === TAB 3: BATCH INVENTORY ===
    with tab3:
        st.subheader("📋 Inventory per SKU dengan Detail Batch")
        
        # Group data by Material (SKU) and aggregate
        if not df.empty:
            # Get unique SKUs with multiple batches
            sku_batch_counts = df.groupby('Material').agg({
                'Material Description': 'first',
                'Product Hierarchy 2': 'first',
                'Batch': 'count',
                'Unrestricted': 'sum',
                'Umur (Bulan)': ['min', 'max'],
                'Status': lambda x: x.mode()[0] if len(x.mode()) > 0 else 'Unknown'
            }).reset_index()
            
            # Flatten column names
            sku_batch_counts.columns = [
                'SKU', 'Description', 'Brand', 'Batch Count', 
                'Total Qty', 'Min Expiry', 'Max Expiry', 'Status'
            ]
            
            # Filter SKUs with multiple batches
            multi_batch_skus = sku_batch_counts[sku_batch_counts['Batch Count'] > 1]
            
            st.info(f"🔍 Ditemukan {len(multi_batch_skus)} SKU dengan multiple batch")
            
            if not multi_batch_skus.empty:
                # Display summary table
                st.dataframe(
                    multi_batch_skus.sort_values('Total Qty', ascending=False),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Batch Count": st.column_config.NumberColumn(
                            "Jumlah Batch",
                            help="Total batch yang berbeda"
                        ),
                        "Total Qty": st.column_config.NumberColumn(
                            "Total Stock",
                            format="%d Pcs"
                        ),
                        "Min Expiry": st.column_config.NumberColumn(
                            "Exp. Terdekat (Bln)",
                            format="%.1f Bln"
                        ),
                        "Max Expiry": st.column_config.NumberColumn(
                            "Exp. Terjauh (Bln)",
                            format="%.1f Bln"
                        )
                    }
                )
                
                # Select a SKU to see batch details
                st.markdown("---")
                st.subheader("🔍 Detail Batch per SKU")
                
                selected_sku = st.selectbox(
                    "Pilih SKU untuk melihat detail batch:",
                    options=multi_batch_skus['SKU'].tolist(),
                    format_func=lambda x: f"{x} - {multi_batch_skus[multi_batch_skus['SKU']==x]['Description'].iloc[0]} ({multi_batch_skus[multi_batch_skus['SKU']==x]['Batch Count'].iloc[0]} batch)",
                    key="tab3_sku_select"
                )
                
                if selected_sku:
                    sku_batches = df[df['Material'] == selected_sku]
                    
                    # Display batch details
                    st.markdown(f"#### 📦 SKU: {selected_sku}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Stock", f"{sku_batches['Unrestricted'].sum():,.0f} pcs")
                    with col2:
                        st.metric("Jumlah Batch", len(sku_batches))
                    with col3:
                        status_counts = sku_batches['Status'].value_counts()
                        main_status = status_counts.index[0] if len(status_counts) > 0 else 'Unknown'
                        st.metric("Status Dominan", main_status)
                    
                    # Batch details table
                    st.markdown("##### Detail Batch:")
                    batch_detail = sku_batches[['Batch', 'Unrestricted', 'Umur (Bulan)', 'Status']].sort_values('Umur (Bulan)')
                    
                    # Add percentage column
                    total_qty = batch_detail['Unrestricted'].sum()
                    batch_detail['Percentage'] = (batch_detail['Unrestricted'] / total_qty * 100).round(1)
                    
                    st.dataframe(
                        batch_detail,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Unrestricted": st.column_config.NumberColumn(
                                "Quantity",
                                format="%d Pcs"
                            ),
                            "Umur (Bulan)": st.column_config.ProgressColumn(
                                "Sisa Umur",
                                format="%.1f Bln",
                                min_value=0,
                                max_value=36,
                            ),
                            "Percentage": st.column_config.ProgressColumn(
                                "Persentase",
                                format="%.1f%%",
                                min_value=0,
                                max_value=100,
                            )
                        }
                    )
                    
                    # Visual chart
                    fig = px.pie(
                        batch_detail, 
                        values='Unrestricted', 
                        names='Batch',
                        title=f"Distribusi Quantity per Batch - SKU {selected_sku}",
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    fig.update_layout(
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#1f2937")
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.success("✅ Semua SKU hanya memiliki 1 batch (tidak ada multiple batch)")
        else:
            st.warning("Tidak ada data untuk ditampilkan.")

        # === TAB 4: SALES ORDER PROCESSING ===
        with tab4:
            st.subheader("📄 Sales Order Processing")
            st.markdown("Upload file Sales Order (Excel/CSV) untuk assign batch secara otomatis")
            
            # Information about required columns
            with st.expander("📋 Format File Sales Order"):
                st.markdown("""
                **Kolom yang harus ada:**
                - **Material** atau **SKU**: Kode SKU produk
                - **Order Quantity** atau **Quantity**: Jumlah yang dipesan
                
                **Kolom tambahan (jika ada):**
                - Sales Organization
                - Delivery Date
                - Sales Document
                - Material Description
                """)
            
            # File uploader
            uploaded_file = st.file_uploader(
                "Upload file Sales Order", 
                type=['csv', 'xlsx', 'xls'],
                help="Upload file Excel atau CSV yang berisi data Sales Order",
                key="so_uploader"
            )
            
            # Processing settings
            col1, col2 = st.columns(2)
            
            with col1:
                allocation_method = st.selectbox(
                    "Metode Alokasi Batch:",
                    ["FIFO (First Expired First Out)", "LIFO (Last In First Out)"],
                    help="FIFO: Batch dengan sisa umur tersingkat dipakai duluan",
                    key="allocation_method"
                )
            
            with col2:
                include_critical = st.checkbox(
                    "Include Batch Critical (<12 bulan)", 
                    value=True,
                    help="Apakah batch dengan status 'Critical' boleh digunakan?",
                    key="include_critical"
                )
            
            if uploaded_file is not None:
                try:
                    # Read the uploaded file
                    if uploaded_file.name.endswith('.csv'):
                        so_df = pd.read_csv(uploaded_file)
                    else:
                        so_df = pd.read_excel(uploaded_file)
                    
                    st.success(f"✅ File berhasil diupload: {uploaded_file.name}")
                    st.info(f"📊 Data SO: {len(so_df)} baris, {len(so_df.columns)} kolom")
                    
                    # Show preview of uploaded data
                    with st.expander("🔍 Preview Data SO"):
                        st.dataframe(so_df.head(), use_container_width=True)
                        st.write("Kolom yang ditemukan:", list(so_df.columns))
                    
                    # Process button
                    if st.button("🚀 Process Sales Order", type="primary", use_container_width=True, key="process_so"):
                        with st.spinner("Memproses Sales Order..."):
                            # Prepare stock data based on settings
                            stock_for_allocation = df.copy()
                            
                            # Filter out critical batches if not allowed
                            if not include_critical:
                                initial_count = len(stock_for_allocation)
                                stock_for_allocation = stock_for_allocation[stock_for_allocation['Status'] != 'Critical']
                                filtered_count = len(stock_for_allocation)
                                st.info(f"⚠️ Filtered out {initial_count - filtered_count} batch dengan status Critical")
                            
                            # Sort based on allocation method
                            if "FIFO" in allocation_method:
                                # First Expired First Out - sort by Umur (Bulan) ascending
                                stock_for_allocation = stock_for_allocation.sort_values(['Material', 'Umur (Bulan)'], ascending=[True, True])
                            else:  # LIFO
                                # Last In First Out - sort by Umur (Bulan) descending
                                stock_for_allocation = stock_for_allocation.sort_values(['Material', 'Umur (Bulan)'], ascending=[True, False])
                            
                            # SIMPLIFIED PROCESSING FUNCTION - FIXED VERSION
                            def process_sales_order_simple(so_df, stock_df):
                                """
                                Simple function to assign batches to Sales Orders
                                """
                                results = []
                                
                                # Create a copy of stock for tracking
                                stock_tracker = stock_df.copy()
                                
                                # Standardize column names in SO
                                so_processed = so_df.copy()
                                
                                # Map column names
                                col_mapping = {}
                                for col in so_processed.columns:
                                    col_lower = str(col).lower()
                                    if 'material' in col_lower or 'sku' in col_lower:
                                        col_mapping[col] = 'Material'
                                    elif any(word in col_lower for word in ['quantity', 'qty', 'order']):
                                        col_mapping[col] = 'Order Quantity'
                                    elif 'description' in col_lower:
                                        col_mapping[col] = 'Material Description'
                                
                                so_processed = so_processed.rename(columns=col_mapping)
                                
                                # Ensure Material column exists
                                if 'Material' not in so_processed.columns:
                                    st.error("❌ Kolom 'Material' atau 'SKU' tidak ditemukan di file SO!")
                                    return pd.DataFrame()
                                
                                # Ensure Order Quantity column exists
                                if 'Order Quantity' not in so_processed.columns:
                                    # Try to find quantity column
                                    qty_cols = [c for c in so_processed.columns if any(word in str(c).lower() for word in ['qty', 'quantity'])]
                                    if qty_cols:
                                        so_processed['Order Quantity'] = pd.to_numeric(so_processed[qty_cols[0]], errors='coerce')
                                    else:
                                        st.error("❌ Kolom quantity tidak ditemukan di file SO!")
                                        return pd.DataFrame()
                                
                                # Convert Order Quantity to numeric
                                so_processed['Order Quantity'] = pd.to_numeric(so_processed['Order Quantity'], errors='coerce').fillna(0)
                                
                                # Process each SO line
                                for idx, row in so_processed.iterrows():
                                    material = str(row['Material'])
                                    order_qty = row['Order Quantity']
                                    
                                    # Get available stock for this material
                                    material_stock = stock_tracker[stock_tracker['Material'].astype(str) == material].copy()
                                    
                                    if material_stock.empty:
                                        # No stock available
                                        result = {
                                            'Material': material,
                                            'Order Quantity': order_qty,
                                            'Assigned Batch': 'NO STOCK',
                                            'Assigned Qty': 0,
                                            'Remaining Qty': order_qty,
                                            'Status': 'NO STOCK'
                                        }
                                        # Add original columns if they exist
                                        for col in ['Sales Organization', 'Delivery Date', 'Sales Document', 'Material Description']:
                                            if col in row:
                                                result[col] = row[col]
                                        results.append(result)
                                        continue
                                    
                                    # Calculate total available stock
                                    total_available = material_stock['Unrestricted'].sum()
                                    
                                    if total_available == 0:
                                        # Stock exists but quantity is 0
                                        result = {
                                            'Material': material,
                                            'Order Quantity': order_qty,
                                            'Assigned Batch': 'OUT OF STOCK',
                                            'Assigned Qty': 0,
                                            'Remaining Qty': order_qty,
                                            'Status': 'OUT OF STOCK'
                                        }
                                        # Add original columns
                                        for col in ['Sales Organization', 'Delivery Date', 'Sales Document', 'Material Description']:
                                            if col in row:
                                                result[col] = row[col]
                                        results.append(result)
                                        continue
                                    
                                    # Assign batch based on allocation method
                                    remaining_qty = order_qty
                                    batch_assignments = []
                                    
                                    for _, stock_row in material_stock.iterrows():
                                        if remaining_qty <= 0:
                                            break
                                        
                                        batch_qty = min(stock_row['Unrestricted'], remaining_qty)
                                        if batch_qty > 0:
                                            batch_assignments.append({
                                                'Batch': str(stock_row['Batch']),
                                                'Qty': batch_qty,
                                                'Umur': stock_row['Umur (Bulan)']
                                            })
                                            remaining_qty -= batch_qty
                                    
                                    # Format batch assignments for easy copying
                                    if batch_assignments:
                                        # Simple format for easy copy-paste
                                        batch_str = ", ".join([f"{b['Batch']}" for b in batch_assignments])
                                        
                                        # Detailed format with quantities
                                        batch_details = ", ".join([f"{b['Batch']} ({b['Qty']}pcs)" for b in batch_assignments])
                                        
                                        result = {
                                            'Material': material,
                                            'Order Quantity': order_qty,
                                            'Assigned Batch': batch_str,  # Simple format for copying
                                            'Batch Details': batch_details,  # Detailed format
                                            'Assigned Qty': order_qty - remaining_qty,
                                            'Remaining Qty': remaining_qty,
                                            'Status': 'FULLFILLED' if remaining_qty == 0 else 'PARTIAL'
                                        }
                                        # Add original columns
                                        for col in ['Sales Organization', 'Delivery Date', 'Sales Document', 'Material Description']:
                                            if col in row:
                                                result[col] = row[col]
                                        results.append(result)
                                    else:
                                        # Should not happen, but just in case
                                        result = {
                                            'Material': material,
                                            'Order Quantity': order_qty,
                                            'Assigned Batch': 'ERROR',
                                            'Assigned Qty': 0,
                                            'Remaining Qty': order_qty,
                                            'Status': 'ERROR'
                                        }
                                        # Add original columns
                                        for col in ['Sales Organization', 'Delivery Date', 'Sales Document', 'Material Description']:
                                            if col in row:
                                                result[col] = row[col]
                                        results.append(result)
                                
                                # Create results dataframe
                                result_df = pd.DataFrame(results)
                                
                                return result_df
                            
                            # Process sales order
                            result_df = process_sales_order_simple(so_df, stock_for_allocation)
                            
                            if not result_df.empty:
                                # Display results
                                st.success("✅ Processing selesai!")
                                
                                # Summary metrics
                                total_lines = len(result_df)
                                fulfilled = len(result_df[result_df['Status'] == 'FULLFILLED'])
                                partial = len(result_df[result_df['Status'] == 'PARTIAL'])
                                no_stock = len(result_df[result_df['Status'].isin(['NO STOCK', 'OUT OF STOCK'])])
                                
                                sum1, sum2, sum3, sum4 = st.columns(4)
                                sum1.metric("Total Lines", total_lines)
                                sum2.metric("Fully Fulfilled", fulfilled)
                                sum3.metric("Partial", partial)
                                sum4.metric("No Stock", no_stock)
                                
                                # Display results table - SIMPLE VERSION FOR BATCH COPYING
                                st.markdown("### 📋 Hasil Alokasi Batch")
                                
                                # Create a simplified table for easy batch copying
                                display_cols = []
                                if 'Sales Document' in result_df.columns:
                                    display_cols.append('Sales Document')
                                if 'Material' in result_df.columns:
                                    display_cols.append('Material')
                                if 'Material Description' in result_df.columns:
                                    display_cols.append('Material Description')
                                if 'Order Quantity' in result_df.columns:
                                    display_cols.append('Order Quantity')
                                
                                display_cols.extend(['Assigned Batch', 'Status'])
                                
                                simple_df = result_df[display_cols].copy()
                                
                                # Make Assigned Batch column easy to copy
                                # Remove any empty strings or 'NO STOCK', 'OUT OF STOCK' for clean copying
                                def clean_batch_string(batch_str):
                                    if pd.isna(batch_str):
                                        return ""
                                    batch_str = str(batch_str)
                                    if batch_str in ['NO STOCK', 'OUT OF STOCK', 'ERROR']:
                                        return ""
                                    return batch_str
                                
                                simple_df['Assigned Batch'] = simple_df['Assigned Batch'].apply(clean_batch_string)
                                
                                st.dataframe(
                                    simple_df,
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        "Order Quantity": st.column_config.NumberColumn(
                                            "Order Qty",
                                            format="%d Pcs"
                                        ),
                                        "Assigned Batch": st.column_config.TextColumn(
                                            "Batch (siap di-copy)",
                                            help="Klik untuk select dan copy semua batch"
                                        ),
                                        "Status": st.column_config.SelectboxColumn(
                                            "Status",
                                            options=["FULLFILLED", "PARTIAL", "NO STOCK", "OUT OF STOCK", "ERROR"],
                                            required=True,
                                        )
                                    }
                                )
                                
                                # Show detailed view in expander
                                with st.expander("🔍 Lihat Detail Lengkap"):
                                    st.dataframe(
                                        result_df,
                                        use_container_width=True,
                                        hide_index=True,
                                        column_config={
                                            "Order Quantity": st.column_config.NumberColumn(
                                                "Order Qty",
                                                format="%d Pcs"
                                            ),
                                            "Assigned Qty": st.column_config.NumberColumn(
                                                "Assigned Qty",
                                                format="%d Pcs"
                                            ),
                                            "Remaining Qty": st.column_config.NumberColumn(
                                                "Remaining Qty",
                                                format="%d Pcs"
                                            ),
                                            "Status": st.column_config.SelectboxColumn(
                                                "Status",
                                                options=["FULLFILLED", "PARTIAL", "NO STOCK", "OUT OF STOCK", "ERROR"],
                                                required=True,
                                            )
                                        }
                                    )
                                
                                # Summary by status
                                st.markdown("### 📊 Summary by Status")
                                status_summary = result_df['Status'].value_counts().reset_index()
                                status_summary.columns = ['Status', 'Count']
                                
                                fig_status = px.bar(
                                    status_summary, 
                                    x='Status', 
                                    y='Count',
                                    text='Count',
                                    color='Status',
                                    color_discrete_sequence=px.colors.qualitative.Set3
                                )
                                fig_status.update_traces(texttemplate='%{text}', textposition='outside')
                                fig_status.update_layout(
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    font=dict(color="#1f2937"),
                                    xaxis_title=None,
                                    yaxis_title="Jumlah Line"
                                )
                                st.plotly_chart(fig_status, use_container_width=True)
                                
                                # Download button for results
                                csv = result_df.to_csv(index=False)
                                st.download_button(
                                    label="📥 Download Hasil Lengkap (CSV)",
                                    data=csv,
                                    file_name=f"SO_Allocation_Result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                    key="download_full"
                                )
                                
                                # Download simplified version for batch copying
                                simple_csv = simple_df.to_csv(index=False)
                                st.download_button(
                                    label="📥 Download Batch List (CSV)",
                                    data=simple_csv,
                                    file_name=f"Batch_List_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv",
                                    use_container_width=True,
                                    key="download_batch"
                                )
                                
                                # Quick batch copy feature
                                st.markdown("### 📋 Quick Batch Copy")
                                
                                # Extract all batches for easy copying
                                all_batches = []
                                for batch_str in result_df['Assigned Batch']:
                                    if pd.notna(batch_str) and batch_str not in ['NO STOCK', 'OUT OF STOCK', 'ERROR']:
                                        # Split by comma and clean
                                        batches = str(batch_str).split(',')
                                        for b in batches:
                                            b_clean = b.strip()
                                            if b_clean:
                                                all_batches.append(b_clean)
                                
                                if all_batches:
                                    # Create a text area with all batches
                                    batch_text = ', '.join(all_batches)
                                    st.text_area(
                                        "Semua Batch (siap di-copy):",
                                        value=batch_text,
                                        height=100,
                                        help="Select all text dan copy untuk paste ke Excel"
                                    )
                                    
                                    # Create batch list per material
                                    st.markdown("#### Batch per Material:")
                                    batch_by_material = {}
                                    for _, row in result_df.iterrows():
                                        if row['Status'] == 'FULLFILLED' or row['Status'] == 'PARTIAL':
                                            material = row['Material']
                                            batch_str = row['Assigned Batch']
                                            if pd.notna(batch_str) and batch_str not in ['NO STOCK', 'OUT OF STOCK', 'ERROR']:
                                                if material not in batch_by_material:
                                                    batch_by_material[material] = []
                                                batches = str(batch_str).split(',')
                                                for b in batches:
                                                    b_clean = b.strip()
                                                    if b_clean:
                                                        batch_by_material[material].append(b_clean)
                                    
                                    # Display batch per material
                                    for material, batches in batch_by_material.items():
                                        with st.expander(f"Material: {material}"):
                                            batch_text = ', '.join(batches)
                                            st.text_area(
                                                f"Batch untuk {material}:",
                                                value=batch_text,
                                                height=50,
                                                key=f"batch_{material}"
                                            )
                                
                                # Show problem lines
                                problem_lines = result_df[result_df['Status'].isin(['PARTIAL', 'NO STOCK', 'OUT OF STOCK'])]
                                if not problem_lines.empty:
                                    st.markdown("### ⚠️ Line dengan Masalah")
                                    st.dataframe(
                                        problem_lines[['Material', 'Material Description', 'Order Quantity', 'Assigned Qty', 'Remaining Qty', 'Status']],
                                        use_container_width=True,
                                        hide_index=True
                                    )
                            else:
                                st.error("❌ Gagal memproses Sales Order. Periksa format file.")
                    
                except Exception as e:
                    st.error(f"❌ Error membaca file: {str(e)}")
                    st.info("Pastikan file memiliki format yang benar dan kolom 'Material' atau 'SKU' ada.")
            else:
                # Show sample data format
                st.info("ℹ️ Upload file Sales Order untuk memulai processing")
                
                # Create sample data
                sample_data = {
                    'Sales Organization': ['ID01', 'ID01', 'ID01'],
                    'Delivery Date': ['2024-03-15', '2024-03-16', '2024-03-17'],
                    'Sales Document': ['SO001', 'SO002', 'SO003'],
                    'Material': ['MAT001', 'MAT002', 'MAT003'],
                    'Material Description': ['Product A', 'Product B', 'Product C'],
                    'Order Quantity': [100, 50, 200]
                }
                
                sample_df = pd.DataFrame(sample_data)
                
                with st.expander("📋 Contoh Format File SO"):
                    st.dataframe(sample_df, use_container_width=True)
                    st.markdown("""
                    **Tips:**
                    - File bisa Excel (.xlsx, .xls) atau CSV (.csv)
                    - Kolom **Material** (SKU code) wajib ada
                    - Kolom **Order Quantity** wajib ada
                    - Kolom lain opsional
                    """)
                    
                    # Download sample template
                    csv = sample_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Template SO (CSV)",
                        data=csv,
                        file_name="SO_Template.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="download_template"
                    )

if __name__ == "__main__":
    main()
