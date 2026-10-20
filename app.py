import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import requests
from datetime import datetime

# ==================== 頁面設定 ====================
st.set_page_config(page_title="股票買賣記錄與監控系統", layout="wide")

# ==================== 登入密碼管控驗證 ====================
def check_password():
    """驗證使用者輸入的密碼是否正確"""
    def password_entered():
        # 從 secrets 取得設定密碼，若未設定則預設為 "admin"
        target_password = st.secrets.get("APP_PASSWORD", "admin")
        if st.session_state["password_input"] == target_password:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]  # 清除輸入暫存
        else:
            st.session_state["password_correct"] = False

    # 若尚未紀錄登入狀態，預設為 False
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    # 若尚未登入，顯示登入介面
    if not st.session_state["password_correct"]:
        st.title("🔒 系統登入認證")
        st.text_input(
            "請輸入系統存取密碼：",
            type="password",
            on_change=password_entered,
            key="password_input"
        )
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("❌ 密碼錯誤，請重新輸入！")
        return False
    else:
        return True

# 執行驗證；若驗證未通過則停止執行後續程式碼
if not check_password():
    st.stop()

# ==================== 主系統畫面 (登入成功後呈現) ====================
st.title("📈 股票買賣記錄與即時監控系統")

# 側邊欄增加登出按鈕
with st.sidebar:
    st.write("👤 登入狀態：已驗證")
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

# ==================== GAS Web App URL 設定 ====================
GAS_WEB_APP_URL = st.secrets.get("GAS_WEB_APP_URL", "請在此處貼上你的_GAS_WEB_APP_URL")

def load_data():
    try:
        response = requests.get(GAS_WEB_APP_URL)
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame(data)
            return df
        else:
            st.error(f"無法讀取 Google Sheet 資料，狀態碼: {response.status_code}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"連線至 Google Apps Script 失敗: {e}")
        return pd.DataFrame()

def save_to_google_sheet(row_data):
    try:
        response = requests.post(GAS_WEB_APP_URL, json={"row": row_data})
        if response.status_code == 200 and response.json().get("result") == "success":
            return True
        else:
            st.error(f"寫入失敗: {response.text}")
            return False
    except Exception as e:
        st.error(f"寫入 Google Sheet 發生錯誤: {e}")
        return False

df = load_data()

# ==================== Telegram 訊息發送 ====================
def send_telegram_msg(message):
    token = st.secrets.get("TELEGRAM_BOT_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        try:
            requests.post(url, json=payload)
        except Exception as e:
            st.error(f"Telegram 發送失敗: {e}")

# ==================== Yahoo 股市價格抓取 ====================
def get_stock_info(stock_id):
    ticker_symbol = f"{stock_id}.TW"
    ticker = yf.Ticker(ticker_symbol)
    try:
        info = ticker.info
        name = info.get("shortName") or info.get("longName") or f"台股{stock_id}"
        hist = ticker.history(period="1d")
        price = hist["Close"].iloc[-1] if not hist.empty else None
        return name, price
    except Exception:
        return f"台股{stock_id}", None

# ==================== 分頁頁籤 ====================
tab1, tab2, tab3 = st.tabs(["📝 新增買賣紀錄", "📊 買賣紀錄表與觸發點監控", "📈 統計圖表分析"])

# -------------------- TAB 1: 輸入表單 --------------------
with tab1:
    st.subheader("新增買賣交易數據")
    
    col_basic1, col_basic2, col_basic3, col_basic4 = st.columns(4)
    with col_basic1:
        stock_id = st.text_input("股號 (例如: 2330)", "2330")
    
    stock_name, current_price = get_stock_info(stock_id) if stock_id else ("-", None)
    with col_basic2:
        st.text_input("股名", value=stock_name, disabled=True)
    with col_basic3:
        category = st.text_input("類股 (例如: 電子股)", "電子股")
    with col_basic4:
        sub_category = st.text_input("種類 (例如: 晶圓代工)", "晶圓代工")

    st.markdown("---")
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("### 一、預計買股")
        p_buy_price = st.number_input("預計買股金額", value=0.0, step=0.5)
        p_buy_qty = st.number_input("預計買股數量", value=0, step=1000)
        p_buy_total = p_buy_price * p_buy_qty
        st.info(f"預計買股花費金額：{p_buy_total:,.0f}")

        st.markdown("### 二、實際買股")
        r_buy_date = st.text_input("實際買股日期 (YYYYMMDD)", datetime.now().strftime("%Y%m%d"))
        r_buy_price = st.number_input("實際買股金額", value=0.0, step=0.5)
        r_buy_qty = st.number_input("實際買股數量", value=0, step=1000)
        r_buy_fee = st.number_input("買股手續費", value=0, step=10)
        r_buy_total = r_buy_price * r_buy_qty
        st.success(f"實際買股花費金額：{r_buy_total:,.0f}")

    with c2:
        st.markdown("### 三、預計賣股")
        p_sell_price = st.number_input("預計賣股金額", value=0.0, step=0.5)
        p_sell_qty = st.number_input("預計賣股數量", value=0, step=1000)
        p_sell_total = p_sell_price * p_sell_qty
        st.info(f"預計賣股所得金額：{p_sell_total:,.0f}")

        st.markdown("### 四、實際賣股")
        r_sell_date = st.text_input("實際賣股日期 (YYYYMMDD)", datetime.now().strftime("%Y%m%d"))
        r_sell_price = st.number_input("實際賣股金額", value=0.0, step=0.5)
        r_sell_qty = st.number_input("實際賣股數量", value=0, step=1000)
        r_sell_fee = st.number_input("賣股手續費", value=0, step=10)
        r_sell_total = r_sell_price * r_sell_qty
        st.success(f"實際賣股所得金額：{r_sell_total:,.0f}")

    # 狀態判斷
    status = "結案" if (r_buy_qty == r_sell_qty and r_buy_qty > 0) else "進行中"
    st.write(f"**當前交易狀態：** `{status}`")

    if st.button("💾 儲存並寫入 Google Sheet"):
        new_row = [
            stock_id, stock_name, category, sub_category, status,
            p_buy_price, p_buy_qty, p_buy_total,
            r_buy_date, r_buy_price, r_buy_qty, r_buy_total, r_buy_fee,
            p_sell_price, p_sell_qty, p_sell_total,
            r_sell_date, r_sell_price, r_sell_qty, r_sell_total, r_sell_fee
        ]
        if save_to_google_sheet(new_row):
            st.success("成功寫入 Google Sheet！")
            st.rerun()

# -------------------- TAB 2: 資料展示與價格觸發Telegram通知 --------------------
with tab2:
    st.subheader("📋 股票買賣記錄表")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        
        st.markdown("---")
        st.subheader("🔔 即時觸發Telegram通知檢測")
        if st.button("⚡ 檢查 Yahoo 股市價格並觸發通知"):
            for idx, row in df.iterrows():
                s_id = str(row.get('股號', ''))
                s_name, market_p = get_stock_info(s_id)
                
                p_buy_p = float(row.get('預計買股金額', 0) or 0)
                p_sell_p = float(row.get('預計賣股金額', 0) or 0)

                if market_p:
                    if p_buy_p > 0 and market_p <= p_buy_p:
                        msg = f"🟢 【買入警報】{s_name}({s_id})\n當前股價: {market_p}\n已達到預計買入價: {p_buy_p}"
                        send_telegram_msg(msg)
                        st.info(msg)
                    
                    if p_sell_p > 0 and market_p >= p_sell_p:
                        msg = f"🔴 【賣出警報】{s_name}({s_id})\n當前股價: {market_p}\n已達到預計賣出價: {p_sell_p}"
                        send_telegram_msg(msg)
                        st.success(msg)
    else:
        st.warning("目前尚無歷史交易資料。")

# -------------------- TAB 3: 統計圖表分析 --------------------
with tab3:
    st.subheader("📊 統計分析圖表")
    if not df.empty and '實際賣股日期' in df.columns:
        df_chart = df.copy()
        df_chart['實際賣股YYYYMM'] = df_chart['實際賣股日期'].astype(str).str[:6]
        
        num_cols = ['實際買股花費金額', '實際賣股所得金額']
        for col in num_cols:
            if col in df_chart.columns:
                df_chart[col] = pd.to_numeric(df_chart[col], errors='coerce').fillna(0)
            else:
                df_chart[col] = 0

        grouped = df_chart.groupby('實際賣股YYYYMM').agg(
            總買金額=('實際買股花費金額', 'sum'),
            總賣金額=('實際賣股所得金額', 'sum')
        ).reset_index()
        
        grouped['總賣扣掉總買金額'] = grouped['總賣金額'] - grouped['總買金額']

        # 圖表 1: 每月買賣狀況 (柱狀圖)
        st.markdown("### 1. 每月買賣狀況 (整體統計)")
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(x=grouped['實際賣股YYYYMM'], y=grouped['總買金額'], name='總買金額'))
        fig1.add_trace(go.Bar(x=grouped['實際賣股YYYYMM'], y=grouped['總賣金額'], name='總賣金額'))
        fig1.add_trace(go.Bar(x=grouped['實際賣股YYYYMM'], y=grouped['總賣扣掉總買金額'], name='總賣扣掉總買金額 (淨利)'))
        
        fig1.update_layout(
            title="每月買賣狀況",
            xaxis_title="實際賣股 YYYYMM",
            yaxis_title="金額",
            barmode='group'
        )
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown("---")

        # 圖表 2: 個股每月表現 (曲線圖)
        st.markdown("### 2. 個股每月表現 (折線圖)")
        stock_list = df_chart['股號'].astype(str).unique()
        selected_stock = st.selectbox("選擇個股 (股號)", stock_list)

        df_single = df_chart[df_chart['股號'].astype(str) == selected_stock]
        grouped_single = df_single.groupby('實際賣股YYYYMM').agg(
            總買金額=('實際買股花費金額', 'sum'),
            總賣金額=('實際賣股所得金額', 'sum')
        ).reset_index()
        
        grouped_single['總賣扣掉總買金額'] = grouped_single['總賣金額'] - grouped_single['總買金額']

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=grouped_single['實際賣股YYYYMM'], y=grouped_single['總買金額'], mode='lines+markers', name='總買金額'))
        fig2.add_trace(go.Scatter(x=grouped_single['實際賣股YYYYMM'], y=grouped_single['總賣金額'], mode='lines+markers', name='總賣金額'))
        fig2.add_trace(go.Scatter(x=grouped_single['實際賣股YYYYMM'], y=grouped_single['總賣扣掉總買金額'], mode='lines+markers', name='總賣扣掉總買金額'))

        fig2.update_layout(
            title=f"個股每月表現 ({selected_stock})",
            xaxis_title="實際賣股 YYYYMM",
            yaxis_title="金額"
        )
        st.plotly_chart(fig2, use_container_width=True)