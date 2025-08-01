import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os
from datetime import datetime, timezone

# === API ve Telegram Bilgileri ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

symbol = "VINEUSDT"
qty = 5000
tp_percent = 0.1
sl_percent = 0.015

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": f"🕒 {now}\n{text}"})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv():
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=5m&limit=200"
    try:
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "_"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        send_telegram(f"❌ Binance verisi alınamadı: {e}")
        return None

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return pos
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon sorgulama hatası: {e}")
    return None

def close_position(side):
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
        send_telegram(f"🔴 Pozisyon kapatıldı ({side})")
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon kapama hatası: {e}")

def open_position(signal, entry_price):
    try:
        side = "Buy" if signal == "long" else "Sell"
        if signal == "long":
            tp = round(entry_price * (1 + tp_percent), 5)
            sl = round(entry_price * (1 - sl_percent), 5)
        else:
            tp = round(entry_price * (1 - tp_percent), 5)
            sl = round(entry_price * (1 + sl_percent), 5)

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
        send_telegram(f"🟢 Pozisyon açıldı: {signal.upper()} @ {entry_price:.5f}\n🎯 TP: {tp} | 🛑 SL: {sl}")
    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası: {e}")

def check_signal():
    df = fetch_ohlcv()
    if df is None or len(df) < 3:
        return None, None, None

    df["EMA9"] = calculate_ema(df, 9)
    df["EMA21"] = calculate_ema(df, 21)
    df["EMA250"] = calculate_ema(df, 250)

    ema9_prev = df["EMA9"].iloc[-2]
    ema21_prev = df["EMA21"].iloc[-2]
    ema250_prev = df["EMA250"].iloc[-2]
    ema9_now = df["EMA9"].iloc[-1]
    ema21_now = df["EMA21"].iloc[-1]
    price = df["close"].iloc[-1]

    signal = None
    if ema9_prev >= ema21_prev and ema9_now < ema21_now and ema21_prev > ema250_prev:
        signal = "short"
    elif ema9_prev <= ema21_prev and ema9_now > ema21_now and ema21_prev < ema250_prev:
        signal = "long"

    send_telegram(f"""📡 VINEUSDT EMA Sinyali:
Önceki EMA9: {ema9_prev:.5f} | EMA21: {ema21_prev:.5f} | EMA250: {ema250_prev:.5f}
Şimdi EMA9: {ema9_now:.5f} | EMA21: {ema21_now:.5f}
Fiyat: {price:.5f}
Sinyal: {signal.upper() if signal else "YOK"}""")

    return signal, price, signal is not None

# === Ana Döngü ===
while True:
    try:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.second < 10:
            signal, price, valid = check_signal()
            if not valid:
                time.sleep(60)
                continue

            pos = get_position()
            pos_side = None
            if pos:
                pos_side = "long" if pos["side"] == "Buy" else "short"

            if pos and pos_side != signal:
                close_position(pos["side"])
                time.sleep(2)
                open_position(signal, price)
            elif not pos:
                open_position(signal, price)
            else:
                send_telegram(f"⏸ Mevcut pozisyon zaten açık ({signal.upper()})")
            time.sleep(60)
        else:
            time.sleep(5)
    except Exception as e:
        send_telegram(f"🚨 Bot Hatası: {e}")
        time.sleep(60)