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
qty = 10
interval = "5m"

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def fetch_binance_data(symbol, interval="5m", limit=100):
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

def calculate_ema(df, period=21):
    return df["close"].ewm(span=period, adjust=False).mean()

def get_live_price(symbol="SUIUSDT"):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price"
        params = {"symbol": symbol.upper()}
        response = requests.get(url, params=params)
        return float(response.json()["price"])
    except Exception as e:
        print("Canlı fiyat alınamadı:", e)
        return None

def place_order(direction):
    side = "Buy" if direction == "long" else "Sell"
    try:
        response = session.place_order(
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
    print("📡 Bot başlatıldı...")
    last_minute = -1
    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                df = fetch_binance_data(symbol)
                ema21 = calculate_ema(df).iloc[-1]
                price = get_live_price(symbol)

                if price is None or pd.isna(ema21):
                    continue

                log = f"[{now.strftime('%H:%M')}] EMA21: {ema21:.4f} | Fiyat: {price:.4f}"
                print(log)
                send_telegram_message(log)

                if price > ema21:
                    place_order("long")
                elif price < ema21:
                    place_order("short")

            except Exception as e:
                print("Hata:", e)
        time.sleep(1)

if __name__ == "__main__":
    run_bot()