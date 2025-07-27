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
order_size = 20
max_position = 1000

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def fetch_binance_klines(symbol, interval="1m", limit=100):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume", "close_time",
        "quote_asset_volume", "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    return df

def calculate_ema(df, period):
    return df["close"].ewm(span=period, adjust=False).mean()

def get_live_price(symbol="SUIUSDT"):
    try:
        response = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
        return float(response.json()["price"])
    except:
        return None

def get_position_info():
    try:
        result = session.get_positions(category="linear", symbol=symbol)
        pos_data = result['result']['list'][0]
        size = float(pos_data['size'])
        side = pos_data['side']
        return size, side
    except Exception as e:
        print("Pozisyon bilgisi alınamadı:", e)
        return 0.0, None

def close_position(current_side):
    try:
        opposite = "Sell" if current_side == "Buy" else "Buy"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=opposite,
            order_type="Market",
            qty=max_position,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        msg = f"Pozisyon kapatıldı ({current_side})"
        print(msg)
        send_telegram_message(msg)
    except Exception as e:
        print("Pozisyon kapatılamadı:", e)

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
        msg = f"{direction.upper()} işlemi açıldı (qty: {order_size})"
        print(msg)
        send_telegram_message(msg)
    except Exception as e:
        print("İşlem açılamadı:", e)

def run_bot():
    print("📡 Bot başlatıldı...")
    last_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        if now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                df = fetch_binance_klines(symbol, interval, limit=100)
                ema21 = calculate_ema(df, 21).iloc[-1]
                price = get_live_price(symbol)
                if price is None or pd.isna(ema21):
                    continue

                direction = "long" if price > ema21 else "short"
                size, side = get_position_info()

                log = f"[{now.strftime('%H:%M')}] EMA21: {ema21:.4f} | Fiyat: {price:.4f} | Yön: {direction.upper()}"
                print(log)
                send_telegram_message(log)

                if size >= max_position:
                    close_position("Buy" if side == "long" else "Sell")
                    size = 0

                open_order(direction)

            except Exception as e:
                print("Bot hatası:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()