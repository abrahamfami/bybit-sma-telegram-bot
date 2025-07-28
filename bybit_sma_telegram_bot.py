import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os

# --- Ortam Değişkenleri ---
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "SUIUSDT"
position_size = 200  # 200 SUI = ~800 USDT (30x kaldıraçla ~$27 margin)
leverage = 30

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except:
        pass

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

    if ema9_1m > ema21_1m and ema21_5m > ema200_5m:
        return "long", price
    elif ema9_1m < ema21_1m and ema21_5m < ema200_5m:
        return "short", price
    else:
        return None, price

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
        print("Pozisyon kapatma hatası:", e)

def open_position(direction, entry_price):
    try:
        if direction == "long":
            tp_price = round(entry_price * 1.02, 4)
            sl_price = round(entry_price * 0.99, 4)
            side = "Buy"
        else:
            tp_price = round(entry_price * 0.98, 4)
            sl_price = round(entry_price * 1.01, 4)
            side = "Sell"

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=position_size,
            take_profit=tp_price,
            stop_loss=sl_price,
            reduce_only=False
        )

        send_telegram(
            f"🟢 Pozisyon Açıldı: {direction.upper()}\n"
            f"🎯 TP: {tp_price}\n🛑 SL: {sl_price}\n"
            f"📌 Giriş Fiyatı: {entry_price:.4f}\n📊 Miktar: {position_size} SUI"
        )

    except Exception as e:
        print("Pozisyon açma hatası:", e)

# === Ana Döngü ===
last_signal = None

while True:
    try:
        signal, price = get_combined_signal()
        if signal and signal != last_signal:
            pos = get_current_position()

            if pos:
                if (
                    (signal == "long" and pos["side"] == "Sell")
                    or (signal == "short" and pos["side"] == "Buy")
                ):
                    close_position(pos["side"])
                    time.sleep(2)

            if not pos or (signal != pos["side"].lower()):
                open_position(signal, price)
                last_signal = signal

        time.sleep(60)

    except Exception as e:
        print("Bot hatası:", e)
        time.sleep(60)