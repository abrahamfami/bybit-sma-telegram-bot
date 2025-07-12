import requests
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timezone
import time
import os

# Çevresel değişkenler
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "SUIUSDT"
qty = 1000
interval = "1m"
price_offset = 0.0005

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

last_signal = None

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except:
        pass

def fetch_binance_klines(symbol, interval, limit=200):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    response = requests.get(url)
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

def get_position():
    try:
        pos = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in pos:
            if float(p["size"]) > 0:
                return "long" if p["side"] == "Buy" else "short"
    except:
        return None
    return None

def close_position(pos):
    side = "Sell" if pos == "long" else "Buy"
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        send_telegram_message(f"Pozisyon kapatıldı: {pos.upper()}")
    except Exception as e:
        send_telegram_message(f"Pozisyon kapatma hatası: {e}")

def open_limit_order(direction, price):
    side = "Buy" if direction == "long" else "Sell"
    try:
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Limit",
            qty=qty,
            price=round(price, 4),
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"{direction.upper()} LIMIT emri gönderildi → Fiyat: {round(price, 4)}")
    except Exception as e:
        send_telegram_message(f"Limit emir hatası: {e}")

def run_bot():
    global last_signal
    print("✅ Bot başlatıldı")

    while True:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        try:
            df = fetch_binance_klines(symbol, interval)
            df["sma100"] = calculate_sma(df, 100)
            df["sma200"] = calculate_sma(df, 200)

            sma100 = df["sma100"].iloc[-2]
            sma200 = df["sma200"].iloc[-2]
            live_price = df["close"].iloc[-1]

            timestamp = now.strftime("%H:%M")
            log = f"[{timestamp}] SMA100: {sma100:.4f} | SMA200: {sma200:.4f} | Fiyat: {live_price:.4f}"
            print(log)
            send_telegram_message(log)

            # Sinyal belirleme
            if pd.notna(sma100) and pd.notna(sma200):
                signal = "long" if sma100 > sma200 else "short" if sma100 < sma200 else None

                if signal and signal != last_signal:
                    current_pos = get_position()
                    if current_pos and current_pos != signal:
                        close_position(current_pos)
                        time.sleep(1)

                    # limit emir fiyatı
                    if signal == "long":
                        order_price = live_price - price_offset
                    else:
                        order_price = live_price + price_offset

                    open_limit_order(signal, order_price)
                    last_signal = signal

        except Exception as e:
            print("Genel hata:", e)

        time.sleep(60)

if __name__ == "__main__":
    run_bot()