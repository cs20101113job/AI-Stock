from datetime import datetime
from io import StringIO

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import requests

SHEET_COLUMNS = [
    "股號", "股名", "類股", "種類", "交易狀態",
    "預計買股金額", "預計買股數量", "預計買股花費金額",
    "實際買股日期", "實際買股金額", "實際買股數量", "實際買股花費金額", "買股手續費",
    "預計賣股金額", "預計賣股數量", "預計賣股所得金額",
    "實際賣股日期", "實際賣股金額", "實際賣股數量", "實際賣股所得金額", "賣股手續費",
    "英文股名", "當天收盤價／現價",
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


version_number = "20261021. CS. V1.0 最終版"
st.write(f"📊 系統版本: {version_number}")

# 側邊欄增加登出按鈕
with st.sidebar:
    st.write("👤 登入狀態：已驗證")
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

# ==================== GAS Web App URL 設定 ====================
GAS_WEB_APP_URL = st.secrets.get("GAS_WEB_APP_URL", "請在此處貼上你的_GAS_WEB_APP_URL")
STOCK_REFERENCE_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1DTOV9f3WSzu4sRksO6VpU8zIEU0fVqs_ZWaStEnAYeI/"
    "export?format=csv&gid=0&range=B:E"
)


@st.cache_data(ttl=3600, show_spinner=False)
def load_stock_categories():
    response = requests.get(STOCK_REFERENCE_CSV_URL, timeout=15)
    response.raise_for_status()
    if "text/html" in response.headers.get("Content-Type", "").lower():
        raise ValueError("試算表回傳登入頁面，請將來源試算表設為知道連結的使用者可檢視。")
    response.encoding = "utf-8-sig"

    if response.text.lstrip().lower().startswith(("<!doctype html", "<html")):
        raise ValueError("試算表回傳登入頁面，請將來源試算表設為知道連結的使用者可檢視。")

    reference = pd.read_csv(
        StringIO(response.text),
        header=None,
        dtype=str,
        keep_default_na=False,
    )
    if reference.shape[1] >= 5:
        reference = reference.iloc[:, 1:5]
    elif reference.shape[1] != 4:
        raise ValueError("試算表 B:E 必須依序包含股號、股名、類股、種類。")

    if not reference.empty and str(reference.iloc[0, 0]).strip() in {
        "股號", "股票代號", "股票代碼", "證券代號", "代號"
    }:
        reference = reference.iloc[1:]

    categories = {}
    for _, row in reference.iterrows():
        stock_id = str(row.iloc[0]).strip()
        if stock_id.endswith(".0") and stock_id[:-2].isdigit():
            stock_id = stock_id[:-2]
        if stock_id:
            categories[stock_id] = (
                str(row.iloc[2]).strip(),
                str(row.iloc[3]).strip(),
            )
    return categories


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


def parse_trade_dates(values):
    def parse_date(value):
        if pd.isna(value):
            return pd.NaT
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not pd.notna(value):
                return pd.NaT
            numeric_value = int(value)
            value_text = str(numeric_value)
            if len(value_text) == 8:
                return pd.to_datetime(value_text, format="%Y%m%d", errors="coerce")
            if 1 <= numeric_value <= 100000:
                return pd.Timestamp("1899-12-30") + pd.to_timedelta(numeric_value, unit="D")
            return pd.NaT

        value_text = str(value).strip()
        if not value_text:
            return pd.NaT
        if value_text.endswith(".0") and value_text[:-2].isdigit():
            value_text = value_text[:-2]
        if len(value_text) == 8 and value_text.isdigit():
            return pd.to_datetime(value_text, format="%Y%m%d", errors="coerce")
        if value_text.isdigit():
            serial = int(value_text)
            if 1 <= serial <= 100000:
                return pd.Timestamp("1899-12-30") + pd.to_timedelta(serial, unit="D")
            return pd.NaT
        return pd.to_datetime(value_text, errors="coerce")

    return values.map(parse_date)


def prepare_monthly_trade_data(data):
    chart_data = data.copy()
    required_columns = [
        "股號", "股名", "實際買股日期", "實際買股金額", "實際買股數量",
        "實際買股花費金額", "實際賣股日期", "實際賣股金額", "實際賣股數量",
        "實際賣股所得金額",
    ]
    for column in required_columns:
        if column not in chart_data.columns:
            chart_data[column] = pd.NA

    for column in (
        "實際買股金額",
        "實際買股數量",
        "實際買股花費金額",
        "實際賣股金額",
        "實際賣股數量",
        "實際賣股所得金額",
    ):
        chart_data[column] = pd.to_numeric(
            chart_data[column].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )

    for price_column, quantity_column, total_column in (
        ("實際買股金額", "實際買股數量", "實際買股花費金額"),
        ("實際賣股金額", "實際賣股數量", "實際賣股所得金額"),
    ):
        calculated_total = chart_data[price_column] * chart_data[quantity_column]
        missing_total = chart_data[total_column].isna() | chart_data[total_column].eq(0)
        has_trade_data = chart_data[price_column].gt(0) & chart_data[quantity_column].gt(0)
        chart_data.loc[missing_total & has_trade_data, total_column] = calculated_total
        chart_data[total_column] = chart_data[total_column].fillna(0)

    chart_data["_買入日期"] = parse_trade_dates(chart_data["實際買股日期"])
    chart_data["_賣出日期"] = parse_trade_dates(chart_data["實際賣股日期"])
    chart_data["_買入月份"] = chart_data["_買入日期"].dt.strftime("%Y-%m")
    chart_data["_賣出月份"] = chart_data["_賣出日期"].dt.strftime("%Y-%m")

    buy_monthly = (
        chart_data.dropna(subset=["_買入月份"])
        .groupby("_買入月份")["實際買股花費金額"]
        .sum()
        .rename("實際買入金額")
    )
    sell_monthly = (
        chart_data.dropna(subset=["_賣出月份"])
        .groupby("_賣出月份")["實際賣股所得金額"]
        .sum()
        .rename("實際賣出金額")
    )
    monthly = pd.concat([buy_monthly, sell_monthly], axis=1).fillna(0).sort_index()
    return chart_data, monthly


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

def save_to_google_sheet(
    row_data, row_number=None, expected_stock_id=None, expected_status=None
):
    payload = {"headers": SHEET_COLUMNS, "row": row_data}
    if row_number is not None:
        payload.update({
            "action": "update",
            "rowNumber": row_number,
            "expectedStockId": expected_stock_id,
            "expectedStatus": expected_status,
        })

    try:
        response = requests.post(
            GAS_WEB_APP_URL,
            json=payload,
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
        elif description == "Forbidden: the bot can't send messages to the bot":
            description = (
                "目前的 TELEGRAM_CHAT_ID 指向另一個 Telegram 機器人；Telegram 不允許機器人互相傳訊。"
                "請用自己的個人 Telegram 帳號開啟 AI 股票機器人、傳送 /start，"
                "並將個人對話的 chat.id 設為 TELEGRAM_CHAT_ID。"
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

    open_trades = pd.DataFrame()
    if not df.empty and {"交易狀態", "_sheet_row"}.issubset(df.columns):
        open_trades = df[
            df["交易狀態"].astype(str).str.strip().eq("進行中")
            & pd.to_numeric(df["_sheet_row"], errors="coerce").notna()
        ].copy()

    trade_options = [0] + (
        pd.to_numeric(open_trades["_sheet_row"], errors="raise").astype(int).tolist()
        if not open_trades.empty
        else []
    )
    pending_trade_row = st.session_state.pop("pending_open_trade", None)
    if pending_trade_row in trade_options:
        st.session_state["selected_open_trade"] = pending_trade_row
    if st.session_state.get("selected_open_trade", 0) not in trade_options:
        st.session_state["selected_open_trade"] = 0
    if "_loaded_open_trade" not in st.session_state:
        st.session_state["_loaded_open_trade"] = None

    def trade_option_label(row_number):
        if row_number == 0:
            return "新增空白交易"
        record = open_trades.loc[
            pd.to_numeric(open_trades["_sheet_row"], errors="coerce").eq(row_number)
        ].iloc[0]
        stock_id_label = str(record.get("股號", "")).strip()
        stock_name_label = str(record.get("股名", "")).strip()
        return f"{stock_id_label} {stock_name_label}（進行中，第 {row_number} 列）".strip()

    selected_trade_row = st.selectbox(
        "載入進行中交易",
        options=trade_options,
        format_func=trade_option_label,
        key="selected_open_trade",
    )

    def form_number(value, default=0):
        parsed = pd.to_numeric(value, errors="coerce")
        return default if pd.isna(parsed) else float(parsed)

    def form_text(value):
        return "" if pd.isna(value) else str(value)

    def form_date(value, default_today=True):
        if pd.isna(value) or str(value).strip() == "":
            return datetime.now().strftime("%Y%m%d") if default_today else ""
        parsed = parse_trade_dates(pd.Series([value])).iloc[0]
        return parsed.strftime("%Y%m%d") if pd.notna(parsed) else str(value)

    if selected_trade_row != st.session_state["_loaded_open_trade"]:
        if selected_trade_row == 0:
            st.session_state.update({
                "form_stock_id": "2330",
                "form_p_buy_price": 0.0,
                "form_p_buy_qty": 0,
                "form_r_buy_date": datetime.now().strftime("%Y%m%d"),
                "form_r_buy_price": 0.0,
                "form_r_buy_qty": 0,
                "form_r_buy_fee": 0,
                "form_p_sell_price": 0.0,
                "form_p_sell_qty": 0,
                "form_r_sell_date": datetime.now().strftime("%Y%m%d"),
                "form_r_sell_price": 0.0,
                "form_r_sell_qty": 0,
                "form_r_sell_fee": 0,
            })
        else:
            selected_record = open_trades.loc[
                pd.to_numeric(open_trades["_sheet_row"], errors="coerce").eq(
                    selected_trade_row
                )
            ].iloc[0]
            st.session_state.update({
                "form_stock_id": str(selected_record.get("股號", "")).strip(),
                "form_p_buy_price": form_number(selected_record.get("預計買股金額")),
                "form_p_buy_qty": int(form_number(selected_record.get("預計買股數量"))),
                "form_r_buy_date": form_date(
                    selected_record.get("實際買股日期"), default_today=False
                ),
                "form_r_buy_price": form_number(selected_record.get("實際買股金額")),
                "form_r_buy_qty": int(form_number(selected_record.get("實際買股數量"))),
                "form_r_buy_fee": int(form_number(selected_record.get("買股手續費"))),
                "form_p_sell_price": form_number(selected_record.get("預計賣股金額")),
                "form_p_sell_qty": int(form_number(selected_record.get("預計賣股數量"))),
                "form_r_sell_date": form_date(
                    selected_record.get("實際賣股日期"), default_today=False
                ),
                "form_r_sell_price": form_number(selected_record.get("實際賣股金額")),
                "form_r_sell_qty": int(form_number(selected_record.get("實際賣股數量"))),
                "form_r_sell_fee": int(form_number(selected_record.get("賣股手續費"))),
            })
        st.session_state["_loaded_open_trade"] = selected_trade_row

    if not df.empty and "_sheet_row" not in df.columns:
        st.info("進行中交易載入與更新功能需先部署最新版 Google Apps Script。")

    col_basic1, col_basic2, col_basic3, col_basic4, col_basic5 = st.columns(5)
    with col_basic1:
        stock_id = st.text_input("股號 (例如: 2330)", key="form_stock_id")
    
    category = ""
    sub_category = ""
    stock_reference_error = None
    stock_category_found = False
    if stock_id:
        try:
            stock_categories = load_stock_categories()
        except (
            requests.RequestException,
            ValueError,
            pd.errors.ParserError,
            pd.errors.EmptyDataError,
        ) as error:
            stock_reference_error = error
            st.warning(f"無法讀取股號對照資料：{error}")
        else:
            lookup_stock_id = str(stock_id).strip()
            if lookup_stock_id.endswith(".0") and lookup_stock_id[:-2].isdigit():
                lookup_stock_id = lookup_stock_id[:-2]
            stock_category_found = lookup_stock_id in stock_categories
            category, sub_category = stock_categories.get(lookup_stock_id, ("", ""))
            if not stock_category_found:
                st.info(f"對照資料中查無股號「{lookup_stock_id}」的類股與種類。")

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
        st.text_input("類股", value=category, disabled=True)
    with col_basic4:
        st.text_input("種類", value=sub_category, disabled=True)
    with col_basic5:
        st.text_input(
            "當天收盤價／現價",
            value=f"{current_price:,.2f}" if current_price is not None else "暫無報價",
            disabled=True,
        )

    st.markdown("---")
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("### 一、預計買股")
        p_buy_price = st.number_input("預計買股金額", step=0.5, key="form_p_buy_price")
        p_buy_qty = st.number_input("預計買股數量", step=1000, key="form_p_buy_qty")
        p_buy_total = p_buy_price * p_buy_qty
        st.info(f"預計買股花費金額：{p_buy_total:,.0f}")

        st.markdown("### 二、實際買股")
        r_buy_date = st.text_input("實際買股日期 (YYYYMMDD)", key="form_r_buy_date")
        r_buy_price = st.number_input("實際買股金額", step=0.5, key="form_r_buy_price")
        r_buy_qty = st.number_input("實際買股數量", step=1000, key="form_r_buy_qty")
        r_buy_fee = st.number_input("買股手續費", step=10, key="form_r_buy_fee")
        r_buy_total = r_buy_price * r_buy_qty
        st.success(f"實際買股花費金額：{r_buy_total:,.0f}")

    with c2:
        st.markdown("### 三、預計賣股")
        p_sell_price = st.number_input("預計賣股金額", step=0.5, key="form_p_sell_price")
        p_sell_qty = st.number_input("預計賣股數量", step=1000, key="form_p_sell_qty")
        p_sell_total = p_sell_price * p_sell_qty
        st.info(f"預計賣股所得金額：{p_sell_total:,.0f}")

        st.markdown("### 四、實際賣股")
        r_sell_date = st.text_input("實際賣股日期 (YYYYMMDD)", key="form_r_sell_date")
        r_sell_price = st.number_input("實際賣股金額", step=0.5, key="form_r_sell_price")
        r_sell_qty = st.number_input("實際賣股數量", step=1000, key="form_r_sell_qty")
        r_sell_fee = st.number_input("賣股手續費", step=10, key="form_r_sell_fee")
        r_sell_total = r_sell_price * r_sell_qty
        st.success(f"實際賣股所得金額：{r_sell_total:,.0f}")

    # 狀態判斷
    status = "結案" if (r_buy_qty == r_sell_qty and r_buy_qty > 0) else "進行中"
    st.write(f"**當前交易狀態：** `{status}`")

    if st.button(
        "💾 儲存並寫入 Google Sheet",
        disabled=bool(stock_id and (stock_reference_error or not stock_category_found)),
    ):
        new_row = [
            stock_id, stock_chinese_name, category, sub_category, status,
            p_buy_price, p_buy_qty, p_buy_total,
            r_buy_date, r_buy_price, r_buy_qty, r_buy_total, r_buy_fee,
            p_sell_price, p_sell_qty, p_sell_total,
            r_sell_date, r_sell_price, r_sell_qty, r_sell_total, r_sell_fee,
            stock_english_name, current_price if current_price is not None else "",
        ]
        if save_to_google_sheet(
            new_row,
            row_number=selected_trade_row if selected_trade_row else None,
            expected_stock_id=(
                str(
                    open_trades.loc[
                        pd.to_numeric(open_trades["_sheet_row"], errors="coerce").eq(
                            selected_trade_row
                        ),
                        "股號",
                    ].iloc[0]
                ).strip()
                if selected_trade_row
                else None
            ),
            expected_status="進行中" if selected_trade_row else None,
        ):
            st.success(
                "已更新 Google Sheet 原交易紀錄！"
                if selected_trade_row
                else "成功寫入 Google Sheet！"
            )
            st.rerun()

# -------------------- TAB 2: 資料展示與價格觸發Telegram通知 --------------------
with tab2:
    st.subheader("📋 股票買賣記錄表")
    if not df.empty:
        status_filter = st.selectbox(
            "依交易狀態篩選",
            ["全部", "進行中", "結案"],
            key="records_status_filter",
        )
        displayed_df = df
        if status_filter != "全部" and "交易狀態" in df.columns:
            displayed_df = df[
                df["交易狀態"].astype(str).str.strip().eq(status_filter)
            ]
        st.dataframe(
            displayed_df.drop(columns=["_sheet_row"], errors="ignore"),
            use_container_width=True,
        )
        if not open_trades.empty:
            selected_open_trade = st.selectbox(
                "選擇要帶入新增交易表單的進行中紀錄",
                options=trade_options[1:],
                format_func=trade_option_label,
                key="table_open_trade",
            )
            if st.button("帶入新增買賣交易數據"):
                st.session_state["pending_open_trade"] = selected_open_trade
                st.rerun()
        elif "交易狀態" in df.columns and df["交易狀態"].astype(str).str.strip().eq("進行中").any():
            st.info("進行中交易載入功能需先部署最新版 Google Apps Script。")
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
            actual_buy_qty = pd.to_numeric(row.get("實際買股數量", 0), errors="coerce")
            p_buy_p = 0 if pd.isna(p_buy_p) else p_buy_p
            p_sell_p = 0 if pd.isna(p_sell_p) else p_sell_p
            actual_buy_qty = 0 if pd.isna(actual_buy_qty) else actual_buy_qty

            if market_p is None:
                st.warning(f"無法取得 {stock_label}（{s_id}）的 Yahoo 股價。")
                continue

            if actual_buy_qty <= 0 and p_buy_p > 0 and market_p <= p_buy_p:
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
        df_chart, monthly = prepare_monthly_trade_data(df)

        if monthly.empty or not monthly.to_numpy().any():
            st.info(
                "目前資料中找不到同時具備有效日期與實際交易金額的買賣紀錄。"
                "日期可使用 YYYYMMDD、YYYY-MM-DD 或 Google 試算表日期格式；"
                "金額可由實際成交價 × 股數計算。請檢查下方資料對照。"
            )
            diagnostic_columns = [
                column for column in (
                    "股號", "股名", "實際買股日期", "實際買股金額",
                    "實際買股數量", "實際買股花費金額", "實際賣股日期",
                    "實際賣股金額", "實際賣股數量", "實際賣股所得金額",
                ) if column in df_chart.columns
            ]
            st.dataframe(df_chart[diagnostic_columns], use_container_width=True)
        else:
            monthly["當月現金流"] = monthly["實際賣出金額"] - monthly["實際買入金額"]
            st.markdown("### 每月實際買賣金額")
            chart_values = monthly[
                ["實際買入金額", "實際賣出金額", "當月現金流"]
            ].to_numpy(dtype=float)
            data_min = min(0.0, float(chart_values.min()))
            data_max = max(0.0, float(chart_values.max()))
            padding = max((data_max - data_min) * 0.1, 1.0)
            default_y_min = data_min - padding
            default_y_max = data_max + padding
            custom_y_range = st.checkbox("自訂圖表 Y 軸上下限")
            y_range = None
            if custom_y_range:
                y_min_col, y_max_col = st.columns(2)
                with y_min_col:
                    y_min = st.number_input(
                        "Y 軸下限",
                        value=default_y_min,
                        step=max(padding, 1.0),
                        format="%.2f",
                    )
                with y_max_col:
                    y_max = st.number_input(
                        "Y 軸上限",
                        value=default_y_max,
                        step=max(padding, 1.0),
                        format="%.2f",
                    )
                if y_min >= y_max:
                    st.error("Y 軸下限必須小於上限。")
                else:
                    y_range = [y_min, y_max]

            if not custom_y_range or y_range is not None:
                monthly_labels = monthly.index.astype(str).tolist()
                fig1 = go.Figure()
                fig1.add_trace(go.Bar(x=monthly_labels, y=monthly["實際買入金額"], name="實際買入金額"))
                fig1.add_trace(go.Bar(
                    x=monthly_labels,
                    y=monthly["實際賣出金額"],
                    name="實際賣出金額",
                    marker_color="green",
                ))
                fig1.add_trace(go.Scatter(
                    x=monthly_labels,
                    y=monthly["當月現金流"],
                    mode="lines+markers",
                    name="當月現金流（賣出 - 買入，非已實現損益）",
                    marker={"size": 12},
                ))
                fig1.update_layout(
                    title="每月實際買賣統計",
                    xaxis_title="月份",
                    yaxis_title="金額",
                    barmode="group",
                    xaxis={"type": "category"},
                    yaxis={"range": y_range},
                )
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
                    if single_monthly.empty:
                        st.info("這檔股票尚無有效交易日期，無法繪製個股月圖。")
                    else:
                        st.markdown("### 個股圖表 Y 軸範圍")
                        single_chart_values = single_monthly[
                            ["實際買入金額", "實際賣出金額"]
                        ].to_numpy(dtype=float)
                        single_data_min = min(0.0, float(single_chart_values.min()))
                        single_data_max = max(0.0, float(single_chart_values.max()))
                        single_padding = max(
                            (single_data_max - single_data_min) * 0.1, 1.0
                        )
                        single_default_y_min = single_data_min - single_padding
                        single_default_y_max = single_data_max + single_padding
                        single_chart_key = str(selected_id).replace(".", "_")
                        custom_single_y_range = st.checkbox(
                            "自訂個股圖表 Y 軸上下限",
                            key=f"custom_single_y_range_{single_chart_key}",
                        )
                        single_y_range = None
                        if custom_single_y_range:
                            single_y_min_col, single_y_max_col = st.columns(2)
                            with single_y_min_col:
                                single_y_min = st.number_input(
                                    "個股圖表 Y 軸下限",
                                    value=single_default_y_min,
                                    step=max(single_padding, 1.0),
                                    format="%.2f",
                                    key=f"single_y_min_{single_chart_key}",
                                )
                            with single_y_max_col:
                                single_y_max = st.number_input(
                                    "個股圖表 Y 軸上限",
                                    value=single_default_y_max,
                                    step=max(single_padding, 1.0),
                                    format="%.2f",
                                    key=f"single_y_max_{single_chart_key}",
                                )
                            if single_y_min >= single_y_max:
                                st.error("個股圖表 Y 軸下限必須小於上限。")
                            else:
                                single_y_range = [single_y_min, single_y_max]

                        if not custom_single_y_range or single_y_range is not None:
                            single_labels = single_monthly.index.astype(str).tolist()
                            fig2 = go.Figure()
                            fig2.add_trace(go.Scatter(
                                x=single_labels,
                                y=single_monthly["實際買入金額"],
                                mode="lines+markers",
                                name="實際買入金額",
                                marker={"size": 12},
                            ))
                            fig2.add_trace(go.Scatter(
                                x=single_labels,
                                y=single_monthly["實際賣出金額"],
                                mode="lines+markers",
                                name="實際賣出金額",
                                marker={"color": "green", "symbol": "diamond", "size": 12},
                                line={"color": "green"},
                            ))
                            fig2.update_layout(
                                title=f"個股每月買賣金額（{selected_stock}）",
                                xaxis_title="月份",
                                yaxis_title="金額",
                                xaxis={"type": "category"},
                                yaxis={"range": single_y_range},
                            )
                            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("新增交易資料後，這裡會顯示每月及個股買賣統計圖表。")