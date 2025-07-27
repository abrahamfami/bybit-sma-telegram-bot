import requests
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timezone
import time
import os

# Ortam değişkenleri
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "SUIUSDT"
qty = 1000  # Güncellendi
interval = "1m"

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def fetch_binance_data(symbol, interval="1m", limit=250):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close",
        "volume", "close_time", "quote_asset_volume",
        "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    return df

def calculate_ema(df, period):
    return df["close"].ewm(span=period, adjust=False).mean()

def get_active_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            if float(p["size"]) > 0:
                return p["side"].lower()  # "Buy" -> "buy", "Sell" -> "sell"
    except Exception as e:
        print("Pozisyon sorgulanamadı:", e)
    return None

def close_position(side):
    reverse = "Sell" if side == "buy" else "Buy"
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=reverse,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        print(f"{side.upper()} pozisyonu kapatıldı.")
        send_telegram_message(f"{side.upper()} pozisyonu kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatılamadı:", e)

def place_order(direction):
    side = "Buy" if direction == "long" else "Sell"
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{direction.upper()} işlemi açıldı.")
        send_telegram_message(f"{direction.upper()} işlemi açıldı.")
    except Exception as e:
        print("İşlem açılamadı:", e)

def run_bot():
    print("📡 EMA100/200 crossover botu çalışıyor...")
    last_signal = None

    while True:
        now = datetime.now(timezone.utc)
        if now.second == 0:
            try:
                df = fetch_binance_data(symbol, interval="1m", limit=250)
                ema100 = calculate_ema(df, 100).iloc[-1]
                ema200 = calculate_ema(df, 200).iloc[-1]

                log = f"[{now.strftime('%H:%M')}] EMA100: {ema100:.4f} | EMA200: {ema200:.4f}"
                print(log)
                send_telegram_message(log)

                # Yeni sinyali belirle
                signal = "long" if ema100 > ema200 else "short"

                if signal != last_signal:
                    print(f"🔁 Crossover tespit edildi → {signal.upper()}")
                    send_telegram_message(f"🔁 Crossover: {signal.upper()}")

                    active_pos = get_active_position()
                    if active_pos:
                        if (signal == "long" and active_pos == "sell") or (signal == "short" and active_pos == "buy"):
                            close_position(active_pos)
                            time.sleep(1)

                    place_order(signal)
                    last_signal = signal

            except Exception as e:
                print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()