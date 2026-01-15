import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Reseller Stock Dashboard (F213)", layout="wide")

# --- LOAD DATA FUNCTION ---
@st.cache_data(ttl=600)  # Cache data for 10 mins to speed up
def load_data():
    # Define scopes
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

    # Load credentials from secrets
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)

    # Open Spreadsheet
    # Pastikan link ini benar dan Service Account sudah jadi Editor/Viewer
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1HfC0mLgfSaRa64dd3II6HFY1gTTeVt9WBTBUC5nfwac/edit?usp=sharing"
    sh = client.open_by_url(spreadsheet_url)
    worksheet = sh.get_worksheet(0)  # Assuming data is in Sheet1

    # Get all values and convert to DataFrame
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    
    return df

# --- PREPROCESSING FUNCTION ---
def preprocess_data(df):
    # 1. Filter Location F213
    df_filtered = df[df['Storage Location'] == 'F213'].copy()
    
    # 2. Convert Data Types
    # Handle numeric columns logic
    numeric_cols = ['Unrestricted', 'Remaining Expiry Date']
    for col in numeric_cols:
        if col in df_filtered.columns:
            df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce').fillna(0)
            
    # 3. Create Expiry Status Grouping
    def categorize_expiry(days):
        if days < 0: return "Expired"
        elif days <= 90: return "Critical (< 3 Mos)"
        elif days <= 180: return "Warning (< 6 Mos)"
        else: return "Safe (> 6 Mos)"
    
    if 'Remaining Expiry Date' in df_filtered.columns:
        df_filtered['Expiry Status'] = df_filtered['Remaining Expiry Date'].apply(categorize_expiry)
    
    return df_filtered

# --- MAIN UI ---
try:
    with st.spinner('Loading live data from Google Sheets...'):
        raw_df = load_data()
        df = preprocess_data(raw_df)

    st.title("📦 Reseller Stock Dashboard (Location: F213)")
    st.markdown(f"**Last Updated:** {datetime.now().strftime('%d-%b-%Y %H:%M')}")
    st.markdown("---")

    # --- SIDEBAR FILTERS ---
    st.sidebar.header("🔍 Filter Options")
    
    # Filter by Product Hierarchy 2 (Category/Brand) if exists
    if 'Product Hierarchy 2' in df.columns:
        categories = ['All'] + sorted(list(df['Product Hierarchy 2'].unique()))
        selected_cat = st.sidebar.selectbox("Select Category (Hierarchy 2):", categories)
        if selected_cat != 'All':
            df = df[df['Product Hierarchy 2'] == selected_cat]

    # Filter by Expiry Status
    if 'Expiry Status' in df.columns:
        expiry_opts = ['All'] + sorted(list(df['Expiry Status'].unique()))
        selected_expiry = st.sidebar.multiselect("Filter Expiry Status:", expiry_opts, default='All')
        if 'All' not in selected_expiry and selected_expiry:
            df = df[df['Expiry Status'].isin(selected_expiry)]

    # --- TOP METRICS ---
    total_qty = df['Unrestricted'].sum()
    total_sku = df['Material'].nunique()
    
    # Calculate Critical Stock (Less than 90 days)
    critical_stock = df[df['Remaining Expiry Date'] <= 90]['Unrestricted'].sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Stock Qty", f"{total_qty:,.0f}")
    col2.metric("Total SKU Variant", f"{total_sku}")
    col3.metric("Critical Stock (<90 Days)", f"{critical_stock:,.0f}", delta_color="inverse")

    st.markdown("---")

    # --- CHARTS SECTION ---
    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("📊 Top 10 Products by Quantity")
        # Group by Material Desc to handle batches
        top_products = df.groupby('Material Description')['Unrestricted'].sum().nlargest(10).reset_index()
        fig_bar = px.bar(top_products, x='Unrestricted', y='Material Description', orientation='h', 
                         text='Unrestricted', color='Unrestricted', color_continuous_scale='Blues')
        fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bar, use_container_width=True)

    with c2:
        st.subheader("⚠️ Stock Health (Expiry)")
        if 'Expiry Status' in df.columns:
            expiry_counts = df.groupby('Expiry Status')['Unrestricted'].sum().reset_index()
            # Custom colors for safety
            color_map = {
                "Expired": "red",
                "Critical (< 3 Mos)": "orange",
                "Warning (< 6 Mos)": "yellow",
                "Safe (> 6 Mos)": "green"
            }
            fig_pie = px.pie(expiry_counts, values='Unrestricted', names='Expiry Status', 
                             color='Expiry Status', color_discrete_map=color_map, hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

    # --- DETAILED TABLE ---
    st.subheader("📋 Detailed Stock List")
    
    # Rename columns for better display
    display_cols = ['Material', 'Material Description', 'Batch', 'Unrestricted', 
                    'Expiry Date', 'Remaining Expiry Date', 'Expiry Status', 'Product Hierarchy 2']
    
    # Filter columns that actually exist
    final_cols = [c for c in display_cols if c in df.columns]
    
    st.dataframe(
        df[final_cols].sort_values(by='Unrestricted', ascending=False),
        use_container_width=True,
        hide_index=True
    )

except Exception as e:
    st.error(f"Terjadi kesalahan koneksi atau data: {e}")
    st.info("Pastikan file Google Sheet sudah di-share ke email Service Account dan structure kolom sesuai.")
