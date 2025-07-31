import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os
from datetime import datetime, timezone

# === API & Telegram Bilgileri ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# === Pariteler ve Güncellenmiş Miktarlar ===
PAIRS = [
    {"symbol": "VINEUSDT", "bybit_symbol": "VINEUSDT", "qty": 1600},
    {"symbol": "SWARMSUSDT", "bybit_symbol": "SWARMSUSDT", "qty": 8000},
    {"symbol": "CHILLGUYUSDT", "bybit_symbol": "CHILLGUYUSDT", "qty": 3200},
    {"symbol": "GRIFFAINUSDT", "bybit_symbol": "GRIFFAINUSDT", "qty": 6400},
    {"symbol": "ZEREBROUSDT", "bybit_symbol": "ZEREBROUSDT", "qty": 6000}
]

TP_PERCENT = 0.03
SL_PERCENT = 0.05

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": f"🕒 {now}\n{text}"})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_ohlcv(symbol, interval="5m", limit=200):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list):
            return None
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "_"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except:
        return None

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def get_position(symbol):
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return pos
    except:
        return None
    return None

def close_position(symbol, side, qty):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",
            order_type="Market",
            qty=qty,
            reduce_only=True
        )
        time.sleep(1)
        session.cancel_all_orders(category="linear", symbol=symbol)
        send_telegram(f"🔴 {symbol} pozisyon kapatıldı ({side})")
    except Exception as e:
        send_telegram(f"⚠️ {symbol} pozisyon kapama hatası: {e}")

def open_position(symbol, side, qty, entry_price):
    try:
        if side == "Buy":
            tp = round(entry_price * (1 + TP_PERCENT), 5)
            sl = round(entry_price * (1 - SL_PERCENT), 5)
        else:
            tp = round(entry_price * (1 - TP_PERCENT), 5)
            sl = round(entry_price * (1 + SL_PERCENT), 5)

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            take_profit=str(tp),
            stop_loss=str(sl),
            time_in_force="GTC",
            position_idx=0
        )

        send_telegram(f"🟢 {symbol} pozisyon açıldı: {side} @ {entry_price:.5f}\n🎯 TP: {tp} | 🛑 SL: {sl}")
    except Exception as e:
        send_telegram(f"⛔️ {symbol} işlem açma hatası: {e}")

def process_pair(pair):
    symbol = pair["symbol"]
    bybit_symbol = pair["bybit_symbol"]
    qty = pair["qty"]

    df = fetch_binance_ohlcv(symbol)
    if df is None or df.shape[0] < 2:
        send_telegram(f"⚠️ {symbol} için veri alınamadı veya yetersiz.")
        return

    df["EMA9"] = calculate_ema(df, 9)
    df["EMA21"] = calculate_ema(df, 21)

    ema9_prev = df.iloc[-2]["EMA9"]
    ema21_prev = df.iloc[-2]["EMA21"]
    ema9_now = df.iloc[-1]["EMA9"]
    ema21_now = df.iloc[-1]["EMA21"]
    close = df.iloc[-1]["close"]

    signal = None
    if ema9_prev <= ema21_prev and ema9_now > ema21_now:
        signal = "long"
    elif ema9_prev >= ema21_prev and ema9_now < ema21_now:
        signal = "short"

    log = f"""📊 {symbol} Sinyal Kontrolü:
🔁 Önceki:
 EMA9: {ema9_prev:.5f} | EMA21: {ema21_prev:.5f}
✅ Şimdi:
 EMA9: {ema9_now:.5f} | EMA21: {ema21_now:.5f}
💰 Kapanış: {close:.5f}
📊 Sinyal: {signal.upper() if signal else 'YOK'}
"""
    send_telegram(log)

    if not signal:
        return

    current_pos = get_position(bybit_symbol)
    current_side = None
    if current_pos:
        current_side = "long" if current_pos["side"] == "Buy" else "short"

    if not current_pos or current_side != signal:
        if current_pos:
            close_position(bybit_symbol, current_pos["side"], qty)
            time.sleep(2)
        open_position(bybit_symbol, "Buy" if signal == "long" else "Sell", qty, close)
    else:
        send_telegram(f"⏸ {symbol} pozisyon zaten açık ({signal.upper()})")

# === Ana Döngü ===
while True:
    try:
        now = datetime.now(timezone.utc)
        minute = now.minute
        second = now.second

        if minute % 5 == 0 and second < 10:
            for pair in PAIRS:
                process_pair(pair)
            time.sleep(60)
        else:
            time.sleep(5)

    except Exception as e:
        send_telegram(f"🚨 Genel Bot Hatası: {e}")
        time.sleep(60)