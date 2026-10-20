import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import requests
from datetime import datetime

SHEET_COLUMNS = [
    "股號", "股名", "類股", "種類", "交易狀態",
    "預計買股金額", "預計買股數量", "預計買股花費金額",
    "實際買股日期", "實際買股金額", "實際買股數量", "實際買股花費金額", "買股手續費",
    "預計賣股金額", "預計賣股數量", "預計賣股所得金額",
    "實際賣股日期", "實際賣股金額", "實際賣股數量", "實際賣股所得金額", "賣股手續費",
    "英文股名",
]

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
version_number = "v1.2.0"
update_date = "2026-10-20"

st.write(f"📊 系統版本: {version_number} ({update_date})")

# 側邊欄增加登出按鈕
with st.sidebar:
    st.write("👤 登入狀態：已驗證")
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

# ==================== GAS Web App URL 設定 ====================
GAS_WEB_APP_URL = st.secrets.get("GAS_WEB_APP_URL", "請在此處貼上你的_GAS_WEB_APP_URL")


def normalize_sheet_data(data):
    if isinstance(data, dict):
        for key in ("data", "values", "rows"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if data is None or (isinstance(data, list) and not data):
        return pd.DataFrame(columns=SHEET_COLUMNS)

    if isinstance(data, dict):
        try:
            df = pd.DataFrame(data)
        except ValueError:
            df = pd.DataFrame([data])
        if not set(SHEET_COLUMNS).intersection(str(column) for column in df.columns):
            values = [list(data)]
            values.extend(df.astype(object).values.tolist())
            df = pd.DataFrame(values)
    elif isinstance(data, list):
        if data and all(isinstance(row, dict) for row in data):
            response_columns = list(data[0])
            known_columns = set(SHEET_COLUMNS)
            if not known_columns.intersection(response_columns):
                # Some GAS implementations use the first sheet row as JSON keys,
                # so restore that row and map each returned row to known fields.
                values = [response_columns]
                values.extend([[row.get(column) for column in response_columns] for row in data])
                df = pd.DataFrame(values)
            else:
                df = pd.DataFrame(data)
        else:
            df = pd.DataFrame(data)
    else:
        raise ValueError("Google Apps Script 回傳的資料格式不是表格資料。")

    if df.empty:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    if all(str(column).isdigit() for column in df.columns):
        columns = SHEET_COLUMNS + [
            f"其他欄位_{index + 1}"
            for index in range(max(0, len(df.columns) - len(SHEET_COLUMNS)))
        ]
        df.columns = columns[:len(df.columns)]
    else:
        df.columns = [str(column).strip() for column in df.columns]

    return df


def load_data():
    try:
        response = requests.get(GAS_WEB_APP_URL, timeout=15)
        if response.status_code == 200:
            return normalize_sheet_data(response.json())
        else:
            st.error(f"無法讀取 Google Sheet 資料，狀態碼: {response.status_code}")
            return pd.DataFrame()
    except (requests.RequestException, ValueError) as e:
        st.error(f"連線至 Google Apps Script 失敗: {e}")
        return pd.DataFrame()

def save_to_google_sheet(row_data):
    try:
        response = requests.post(
            GAS_WEB_APP_URL,
            json={"headers": SHEET_COLUMNS, "row": row_data},
            timeout=15,
        )
        if response.status_code == 200 and response.json().get("result") == "success":
            return True
        else:
            st.error(f"寫入失敗: {response.text}")
            return False
    except (requests.RequestException, ValueError) as e:
        st.error(f"寫入 Google Sheet 發生錯誤: {e}")
        return False

df = load_data()

# ==================== Telegram 訊息發送 ====================
def send_telegram_msg(message):
    token = st.secrets.get("TELEGRAM_BOT_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "請先在 Streamlit secrets 設定 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID。"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message},
            timeout=15,
        )
        result = response.json()
        if response.ok and result.get("ok"):
            return True, "Telegram 測試訊息已成功送出。"
        description = result.get("description", f"Telegram 回應狀態碼 {response.status_code}")
        if description == "Bad Request: chat not found":
            description = (
                "Telegram 找不到這個 chat。若為私人對話，請先開啟機器人並傳送 /start；"
                "若為群組，請先將機器人加入群組並在群組傳送一則訊息，"
                "再確認 TELEGRAM_CHAT_ID 是該對話的正確 ID。"
            )
        return False, description
    except (requests.RequestException, ValueError) as e:
        return False, f"Telegram 發送失敗：{e}"

# ==================== Yahoo 股市價格抓取 ====================
@st.cache_data(ttl=300, show_spinner=False)
def get_stock_info(stock_id):
    stock_id = str(stock_id).strip()
    if stock_id.endswith(".0") and stock_id[:-2].isdigit():
        stock_id = stock_id[:-2]
    english_name = ""
    price = None

    for suffix in (".TW", ".TWO"):
        ticker = yf.Ticker(f"{stock_id}{suffix}")
        try:
            hist = ticker.history(period="1d")
        except Exception:
            continue
        try:
            info = ticker.info
        except Exception:
            info = {}

        english_name = info.get("shortName") or info.get("longName") or english_name
        if not hist.empty and price is None:
            price = float(hist["Close"].iloc[-1])

    stock_names, _ = load_taiwan_stock_names()
    chinese_name, listed_english_name = stock_names.get(stock_id, ("", ""))
    english_name = english_name or listed_english_name
    chinese_name = chinese_name or f"台股{stock_id}"
    return chinese_name, english_name or f"Taiwan stock {stock_id}", price


@st.cache_data(ttl=86400, show_spinner=False)
def load_taiwan_stock_names():
    sources = (
        (
            "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "公司代號",
            "公司簡稱",
            "英文簡稱",
        ),
        (
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
            "SecuritiesCompanyCode",
            "CompanyAbbreviation",
            "Symbol",
        ),
    )
    names = {}
    errors = []
    for url, code_key, chinese_key, english_key in sources:
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            companies = response.json()
            for company in companies:
                code = str(company.get(code_key, "")).strip()
                if code:
                    names[code] = (
                        str(company.get(chinese_key, "")).strip(),
                        str(company.get(english_key, "")).strip(),
                    )
        except (requests.RequestException, ValueError) as e:
            errors.append(f"{url}: {e}")
    return names, errors

# ==================== 分頁頁籤 ====================
tab1, tab2, tab3 = st.tabs(["📝 新增買賣紀錄", "📊 買賣紀錄表與觸發點監控", "📈 統計圖表分析"])

# -------------------- TAB 1: 輸入表單 --------------------
with tab1:
    st.subheader("新增買賣交易數據")
    
    col_basic1, col_basic2, col_basic3, col_basic4 = st.columns(4)
    with col_basic1:
        stock_id = st.text_input("股號 (例如: 2330)", "2330")
    
    stock_chinese_name, stock_english_name, current_price = (
        get_stock_info(stock_id) if stock_id else ("-", "-", None)
    )
    if stock_id:
        _, stock_name_errors = load_taiwan_stock_names()
        if stock_name_errors:
            st.warning("無法連線至部分臺灣交易所公司資料，中文股名可能暫時以股號代替。")
    with col_basic2:
        st.text_input("中文股名", value=stock_chinese_name, disabled=True)
        st.text_input("英文股名", value=stock_english_name, disabled=True)
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
            stock_id, stock_chinese_name, category, sub_category, status,
            p_buy_price, p_buy_qty, p_buy_total,
            r_buy_date, r_buy_price, r_buy_qty, r_buy_total, r_buy_fee,
            p_sell_price, p_sell_qty, p_sell_total,
            r_sell_date, r_sell_price, r_sell_qty, r_sell_total, r_sell_fee,
            stock_english_name,
        ]
        if save_to_google_sheet(new_row):
            st.success("成功寫入 Google Sheet！")
            st.rerun()

# -------------------- TAB 2: 資料展示與價格觸發Telegram通知 --------------------
with tab2:
    st.subheader("📋 股票買賣記錄表")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("目前尚無歷史交易資料。")

    st.markdown("---")
    st.subheader("🔔 Telegram 通知測試與即時觸發")
    if st.button("📨 傳送 Telegram 測試訊息"):
        sent, result = send_telegram_msg("✅ 股票買賣記錄系統 Telegram 測試訊息")
        if sent:
            st.success(result)
        else:
            st.error(result)

    if st.button("⚡ 檢查 Yahoo 股市價格並觸發通知") and not df.empty:
        for _, row in df.iterrows():
            s_id = str(row.get("股號", "")).strip()
            if s_id.endswith(".0") and s_id[:-2].isdigit():
                s_id = s_id[:-2]
            s_chinese_name, s_english_name, market_p = get_stock_info(s_id)
            stock_label = f"{s_chinese_name} / {s_english_name}"
            p_buy_p = pd.to_numeric(row.get("預計買股金額", 0), errors="coerce")
            p_sell_p = pd.to_numeric(row.get("預計賣股金額", 0), errors="coerce")
            p_buy_p = 0 if pd.isna(p_buy_p) else p_buy_p
            p_sell_p = 0 if pd.isna(p_sell_p) else p_sell_p

            if market_p is None:
                st.warning(f"無法取得 {stock_label}（{s_id}）的 Yahoo 股價。")
                continue

            if p_buy_p > 0 and market_p <= p_buy_p:
                msg = f"🟢 【買入警報】{stock_label}({s_id})\n當前股價: {market_p}\n已達到預計買入價: {p_buy_p}"
                sent, result = send_telegram_msg(msg)
                if sent:
                    st.success(msg)
                else:
                    st.error(result)

            if p_sell_p > 0 and market_p >= p_sell_p:
                msg = f"🔴 【賣出警報】{stock_label}({s_id})\n當前股價: {market_p}\n已達到預計賣出價: {p_sell_p}"
                sent, result = send_telegram_msg(msg)
                if sent:
                    st.success(msg)
                else:
                    st.error(result)

# -------------------- TAB 3: 統計圖表分析 --------------------
with tab3:
    st.subheader("📊 統計分析圖表")
    if not df.empty:
        df_chart = df.copy()
        required_columns = [
            "股號", "股名", "實際買股日期", "實際買股花費金額",
            "實際賣股日期", "實際賣股所得金額",
        ]
        for column in required_columns:
            if column not in df_chart.columns:
                df_chart[column] = pd.NA

        for column in ("實際買股花費金額", "實際賣股所得金額"):
            df_chart[column] = pd.to_numeric(df_chart[column], errors="coerce").fillna(0)

        def parse_trade_dates(values):
            values = values.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            parsed = pd.to_datetime(values, format="%Y%m%d", errors="coerce")
            missing_dates = parsed.isna()
            if missing_dates.any():
                parsed.loc[missing_dates] = values.loc[missing_dates].map(
                    lambda value: pd.to_datetime(value, errors="coerce")
                )
            return parsed

        df_chart["_買入月份"] = parse_trade_dates(df_chart["實際買股日期"]).dt.strftime("%Y-%m")
        df_chart["_賣出月份"] = parse_trade_dates(df_chart["實際賣股日期"]).dt.strftime("%Y-%m")

        buy_monthly = (
            df_chart.dropna(subset=["_買入月份"])
            .groupby("_買入月份")["實際買股花費金額"]
            .sum()
            .rename("實際買入金額")
        )
        sell_monthly = (
            df_chart.dropna(subset=["_賣出月份"])
            .groupby("_賣出月份")["實際賣股所得金額"]
            .sum()
            .rename("實際賣出金額")
        )
        monthly = pd.concat([buy_monthly, sell_monthly], axis=1).fillna(0).sort_index()

        if monthly.empty or not monthly.to_numpy().any():
            st.info("目前沒有可繪製的實際買賣金額與有效日期，請確認 Google Sheet 的日期及金額欄位。")
        else:
            monthly["當月現金流"] = monthly["實際賣出金額"] - monthly["實際買入金額"]
            st.markdown("### 每月實際買賣金額")
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(x=monthly.index, y=monthly["實際買入金額"], name="實際買入金額"))
            fig1.add_trace(go.Bar(x=monthly.index, y=monthly["實際賣出金額"], name="實際賣出金額"))
            fig1.add_trace(go.Scatter(
                x=monthly.index,
                y=monthly["當月現金流"],
                mode="lines+markers",
                name="當月現金流（賣出 - 買入，非已實現損益）",
            ))
            fig1.update_layout(title="每月實際買賣統計", xaxis_title="月份", yaxis_title="金額", barmode="group")
            st.plotly_chart(fig1, use_container_width=True)

            stock_options = df_chart[["股號", "股名"]].dropna(subset=["股號"]).drop_duplicates()
            if not stock_options.empty:
                stock_options["_顯示名稱"] = (
                    stock_options["股號"].astype(str)
                    + " "
                    + stock_options["股名"].fillna("").astype(str)
                ).str.strip()
                selected_stock = st.selectbox("選擇個股", stock_options["_顯示名稱"].tolist())
                selected_id = stock_options.loc[
                    stock_options["_顯示名稱"] == selected_stock, "股號"
                ].iloc[0]
                df_single = df_chart[df_chart["股號"].astype(str) == str(selected_id)]
                single_buy = (
                    df_single.dropna(subset=["_買入月份"])
                    .groupby("_買入月份")["實際買股花費金額"]
                    .sum()
                    .rename("實際買入金額")
                )
                single_sell = (
                    df_single.dropna(subset=["_賣出月份"])
                    .groupby("_賣出月份")["實際賣股所得金額"]
                    .sum()
                    .rename("實際賣出金額")
                )
                single_monthly = pd.concat([single_buy, single_sell], axis=1).fillna(0).sort_index()
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=single_monthly.index,
                    y=single_monthly["實際買入金額"],
                    mode="lines+markers",
                    name="實際買入金額",
                ))
                fig2.add_trace(go.Scatter(
                    x=single_monthly.index,
                    y=single_monthly["實際賣出金額"],
                    mode="lines+markers",
                    name="實際賣出金額",
                ))
                fig2.update_layout(
                    title=f"個股每月買賣金額（{selected_stock}）",
                    xaxis_title="月份",
                    yaxis_title="金額",
                )
                st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("新增交易資料後，這裡會顯示每月及個股買賣統計圖表。")