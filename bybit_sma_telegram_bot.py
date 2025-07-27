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
interval = "1m"
order_size = 25        # ✅ HER işlemde 25 SUI
max_position = 1000    # ✅ 1000’e ulaşıldığında pozisyon kapat

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def fetch_binance_data(symbol, interval="1m", limit=100):
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

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            side = p["side"]
            size = float(p["size"])
            if size > 0:
                return side.lower(), size
    except Exception as e:
        print("Pozisyon sorgulanamadı:", e)
    return None, 0

def close_position(current_side):
    try:
        close_side = "Sell" if current_side == "buy" else "Buy"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=close_side,
            order_type="Market",
            qty=max_position,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        send_telegram_message(f"🔻 Pozisyon kapatıldı: {current_side.upper()}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_order(direction):
    side = "Buy" if direction == "long" else "Sell"
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=order_size,
            time_in_force="GoodTillCancel"
        )
        msg = f"✅ {direction.upper()} işlemi açıldı (qty: {order_size})"
        print(msg)
        send_telegram_message(msg)
    except Exception as e:
        print("İşlem açılamadı:", e)

def run_bot():
    print("🚀 EMA21 Bot başlatıldı... 1 dakikalık kontrol")
    last_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        if now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                df = fetch_binance_data(symbol, interval="1m", limit=100)
                ema21 = calculate_ema(df, 21).iloc[-1]
                price = df["close"].iloc[-1]

                log = f"[{now.strftime('%H:%M')}] EMA21: {ema21:.4f} | Fiyat: {price:.4f}"
                print(log)
                send_telegram_message(log)

                direction = "long" if price > ema21 else "short"
                current_side, current_size = get_position()

                if current_size >= max_position:
                    close_position(current_side)
                    time.sleep(1)

                open_order(direction)

            except Exception as e:
                print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()