import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os

# --- API ve Telegram bilgileri ---
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "SUIUSDT"
position_size = 200
tp_percent = 0.02
sl_percent = 0.01

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv(symbol, interval, limit=200):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "_"
    ])
    df["close"] = df["close"].astype(float)
    return df

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def get_combined_signal():
    df_1m = fetch_ohlcv("SUIUSDT", "1m")
    df_5m = fetch_ohlcv("SUIUSDT", "5m")

    df_1m["EMA9"] = calculate_ema(df_1m, 9)
    df_1m["EMA21"] = calculate_ema(df_1m, 21)
    df_5m["EMA21"] = calculate_ema(df_5m, 21)
    df_5m["EMA200"] = calculate_ema(df_5m, 200)

    ema9_1m = df_1m.iloc[-1]["EMA9"]
    ema21_1m = df_1m.iloc[-1]["EMA21"]
    ema21_5m = df_5m.iloc[-1]["EMA21"]
    ema200_5m = df_5m.iloc[-1]["EMA200"]
    price = df_1m.iloc[-1]["close"]

    signal = None
    if ema9_1m > ema21_1m and ema21_5m > ema200_5m:
        signal = "long"
    elif ema9_1m < ema21_1m and ema21_5m < ema200_5m:
        signal = "short"

    log = f"""📡 EMA Kontrol (1m/5m)
🟩 1m EMA:
  EMA9: {ema9_1m:.4f}
  EMA21: {ema21_1m:.4f}
  ➕ {'EMA9 > EMA21 → BUY' if ema9_1m > ema21_1m else 'EMA9 < EMA21 → SELL'}

🟦 5m EMA:
  EMA21: {ema21_5m:.4f}
  EMA200: {ema200_5m:.4f}
  ➕ {'EMA21 > EMA200 → UP TREND' if ema21_5m > ema200_5m else 'EMA21 < EMA200 → DOWN TREND'}

💰 Fiyat: {price:.4f}
📊 Combo Sinyali: {signal.upper() if signal else 'YOK'}
"""
    send_telegram(log)
    return signal, price

def get_current_position():
    positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
    for pos in positions:
        if pos["size"] != "0":
            return pos
    return None

def close_position(side):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",
            order_type="Market",
            qty=position_size,
            reduce_only=True
        )
        send_telegram(f"🔴 Pozisyon kapatıldı ({side})")
    except Exception as e:
        send_telegram(f"⚠️ Kapatma hatası: {e}")

def place_order_with_tp_sl(signal, entry_price):
    try:
        if signal == "long":
            side = "Buy"
            tp_price = round(entry_price * (1 + tp_percent), 4)
            sl_price = round(entry_price * (1 - sl_percent), 4)
        else:
            side = "Sell"
            tp_price = round(entry_price * (1 - tp_percent), 4)
            sl_price = round(entry_price * (1 + sl_percent), 4)

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=position_size,
            take_profit=tp_price,
            stop_loss=sl_price,
            time_in_force="GTC",
            position_idx=0
        )

        send_telegram(f"🟢 Pozisyon açıldı: {signal.upper()} @ {entry_price:.4f}
🎯 TP: {tp_price}
🛑 SL: {sl_price}")
        return True

    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası (TP/SL dahil): {e}")
        return False

last_signal = None

while True:
    try:
        signal, price = get_combined_signal()

        if signal and signal != last_signal:
            pos = get_current_position()
            if pos:
                close_position(pos["side"])
                time.sleep(2)

            if place_order_with_tp_sl(signal, price):
                last_signal = signal

        time.sleep(60)

    except Exception as e:
        send_telegram(f"🚨 Genel bot hatası:
{e}")
        time.sleep(60)
