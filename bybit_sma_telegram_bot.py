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
qty = 20
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
    print("📡 EMA100/200 Bot başlatıldı...")
    last_minute = -1
    last_signal = None
    crossover_time = None

    while True:
        now = datetime.now(timezone.utc)
        if now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                df = fetch_binance_data(symbol, interval="1m", limit=250)
                ema100 = calculate_ema(df, 100).iloc[-1]
                ema200 = calculate_ema(df, 200).iloc[-1]

                log = f"[{now.strftime('%H:%M')}] EMA100: {ema100:.4f} | EMA200: {ema200:.4f}"
                print(log)
                send_telegram_message(log)

                signal = "long" if ema100 > ema200 else "short"

                # Kesişim tespiti
                if signal != last_signal:
                    crossover_time = now
                    last_signal = signal
                    print("🔁 EMA100/200 crossover:", signal)
                    send_telegram_message(f"Kesişim: {signal.upper()}")

                # Crossover sonrası 50 dakikada işlem aç
                if crossover_time is not None:
                    minutes_since_crossover = (now - crossover_time).total_seconds() / 60
                    if minutes_since_crossover <= 50:
                        place_order(signal)

            except Exception as e:
                print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()