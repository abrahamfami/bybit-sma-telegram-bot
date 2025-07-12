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
binance_symbol = "SUIUSDT"
bybit_symbol = "SUIUSDT"
interval = "1m"
qty = 1000
price_offset = 0.0005

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

last_signal = None

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_klines(symbol, interval, limit=210):
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

def calculate_sma(df, period):
    return df["close"].rolling(window=period).mean()

def get_binance_price():
    try:
        url = f"https://api.binance.com/api/v3/ticker/price"
        params = {"symbol": binance_symbol.upper()}
        response = requests.get(url, params=params)
        return float(response.json()["price"])
    except Exception as e:
        print("Fiyat çekme hatası:", e)
        return None

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=bybit_symbol)["result"]["list"]
        for p in positions:
            if p["side"] == "Buy" and float(p["size"]) > 0:
                return "long"
            elif p["side"] == "Sell" and float(p["size"]) > 0:
                return "short"
    except Exception as e:
        print("Pozisyon alınamadı:", e)
    return None

def close_position(current_pos):
    try:
        side = "Sell" if current_pos == "long" else "Buy"
        session.place_order(
            category="linear",
            symbol=bybit_symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        send_telegram_message(f"❌ Pozisyon kapatıldı: {current_pos.upper()}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_limit_order(direction, current_price):
    try:
        side = "Buy" if direction == "long" else "Sell"
        limit_price = round(current_price - price_offset, 4) if direction == "long" else round(current_price + price_offset, 4)

        session.place_order(
            category="linear",
            symbol=bybit_symbol,
            side=side,
            order_type="Limit",
            price=str(limit_price),
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"🟢 Yeni LIMIT emir ({direction.upper()}): {limit_price}")
    except Exception as e:
        print("Limit emir hatası:", e)

def run_bot():
    global last_signal
    print("✅ Bot çalışıyor...")

    last_logged_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        minute_now = now.minute

        try:
            df = fetch_binance_klines(binance_symbol, interval)
            df["sma100"] = calculate_sma(df, 100)
            df["sma200"] = calculate_sma(df, 200)

            sma100 = df["sma100"].iloc[-2]
            sma200 = df["sma200"].iloc[-2]
            price = get_binance_price()

            if minute_now != last_logged_minute:
                last_logged_minute = minute_now
                log_msg = f"[{now.strftime('%H:%M')}] SMA100: {sma100:.4f} | SMA200: {sma200:.4f} | Fiyat: {price}"
                print(log_msg)
                send_telegram_message(log_msg)

            if pd.notna(sma100) and pd.notna(sma200) and price:
                signal = "long" if sma100 > sma200 else "short" if sma100 < sma200 else None

                if signal and signal != last_signal:
                    current_pos = get_position()
                    if current_pos and current_pos != signal:
                        close_position(current_pos)
                        time.sleep(1)
                    open_limit_order(signal, price)
                    last_signal = signal

        except Exception as e:
            print("Genel hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()