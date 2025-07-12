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
symbol = "SUIUSDT"
qty = 1000
interval = "1m"
binance_symbol = "SUIUSDT"
bybit_symbol = "SUIUSDT"

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

last_signal = None

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_klines(symbol, interval, limit=200):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
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

def get_current_price_binance(symbol):
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": symbol}
    response = requests.get(url, params=params).json()
    return float(response["price"])

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
        send_telegram_message(f"Pozisyon kapatıldı: {current_pos.upper()}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_limit_order(direction, current_price):
    try:
        price = round(current_price + 0.0005, 4) if direction == "long" else round(current_price - 0.0005, 4)
        side = "Buy" if direction == "long" else "Sell"
        session.place_order(
            category="linear",
            symbol=bybit_symbol,
            side=side,
            order_type="Limit",
            qty=qty,
            price=price,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"Limit emir ({side}) gönderildi: {price}")
    except Exception as e:
        print("Limit emir hatası:", e)

def run_bot():
    global last_signal
    print("✅ Bot çalışıyor...")

    last_checked_minute = -1

    while True:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        current_minute = now.minute

        if current_minute != last_checked_minute:
            last_checked_minute = current_minute

            try:
                df = fetch_binance_klines(binance_symbol, interval)
                df["sma100"] = calculate_sma(df, 100)
                df["sma200"] = calculate_sma(df, 200)

                sma100 = df["sma100"].iloc[-2]
                sma200 = df["sma200"].iloc[-2]
                current_price = get_current_price_binance(binance_symbol)

                log = f"[{now.strftime('%H:%M')}] SMA100: {sma100:.4f} | SMA200: {sma200:.4f} | Fiyat: {current_price:.4f}"
                print(log)
                send_telegram_message(log)

                # Yeni sinyali kontrol et (bir önceki kapanıştan)
                signal = None
                if sma100 > sma200:
                    signal = "long"
                elif sma100 < sma200:
                    signal = "short"

                if signal and signal != last_signal:
                    current_pos = get_position()
                    if current_pos != signal:
                        if current_pos:
                            close_position(current_pos)
                            time.sleep(1)
                        open_limit_order(signal, current_price)
                    else:
                        print("Zaten doğru yönde pozisyon açık.")
                    last_signal = signal

            except Exception as e:
                print("Genel hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()