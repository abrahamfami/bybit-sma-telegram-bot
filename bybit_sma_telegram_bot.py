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
interval = "1"
position_size = 100
usdt_pair = "SUIUSDT"

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def calculate_emas(df):
    df["EMA9"] = df["close"].ewm(span=9).mean()
    df["EMA21"] = df["close"].ewm(span=21).mean()
    df["EMA200"] = df["close"].ewm(span=200).mean()
    return df

def get_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if (
        last["EMA9"] > last["EMA21"]
        and last["EMA21"] > last["EMA200"]
        and prev["EMA9"] <= prev["EMA21"]
    ):
        return "long"
    elif (
        last["EMA9"] < last["EMA21"]
        and last["EMA21"] < last["EMA200"]
        and prev["EMA9"] >= prev["EMA21"]
    ):
        return "short"
    else:
        return None

def fetch_ohlcv():
    url = f"https://api.binance.com/api/v3/klines?symbol={usdt_pair}&interval={interval}m&limit=250"
    res = requests.get(url).json()
    df = pd.DataFrame(res, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "_"
    ])
    df["close"] = df["close"].astype(float)
    return calculate_emas(df)

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
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_position(direction):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Buy" if direction == "long" else "Sell",
            order_type="Market",
            qty=position_size,
            reduce_only=False
        )
        send_telegram(f"📈 Yeni pozisyon: {direction.upper()} açıldı – {position_size} SUI")
    except Exception as e:
        print("Pozisyon açma hatası:", e)

# --- Ana Bot Döngüsü ---
last_signal = None

while True:
    try:
        df = fetch_ohlcv()
        signal = get_signal(df)

        if signal and signal != last_signal:
            current_position = get_current_position()

            if current_position:
                if (
                    (signal == "long" and current_position["side"] == "Sell")
                    or (signal == "short" and current_position["side"] == "Buy")
                ):
                    close_position(current_position["side"])
                    send_telegram(f"🛑 Pozisyon kapatıldı ({current_position['side']})")

            open_position(signal)
            last_signal = signal

            last = df.iloc[-1]
            send_telegram(
                f"📊 EMA Bilgisi:\nEMA9: {last['EMA9']:.4f}\nEMA21: {last['EMA21']:.4f}\nEMA200: {last['EMA200']:.4f}"
            )

        time.sleep(60)
    except Exception as e:
        print("Hata oluştu:", e)
        time.sleep(60)