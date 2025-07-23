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

# Sabitler
symbol_binance = "SUIUSDT"
symbol_bybit = "SUIUSDT"
qty = 30
interval = "5m"

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as e:
        print("Telegram hatası:", e)

def fetch_binance_ema():
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol_binance.upper(), "interval": interval, "limit": 30}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close",
        "volume", "close_time", "quote_asset_volume",
        "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    return df

def open_position(direction):
    try:
        side = "Buy" if direction == "long" else "Sell"
        session.place_order(
            category="linear",
            symbol=symbol_bybit,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        send_telegram(f"🟢 Yeni işlem açıldı: {direction.upper()}")
    except Exception as e:
        print("İşlem açma hatası:", e)

def run_bot():
    print("🚀 EMA21 TERS strateji başlatıldı")
    last_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.minute != last_minute and now.second == 0:
            last_minute = now.minute

            try:
                df = fetch_binance_ema()
                price = df["close"].iloc[-2]
                ema21 = df["ema21"].iloc[-2]

                log = f"[{now.strftime('%H:%M')}] Fiyat: {price:.4f} | EMA21: {ema21:.4f}"
                print(log)
                send_telegram(log)

                # EMA21'in üstünde ise long, altında ise short aç
                direction = "long" if price > ema21 else "short"
                open_position(direction)

            except Exception as e:
                print("Genel hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()