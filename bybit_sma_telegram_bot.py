import requests
import time
from datetime import datetime, timezone
from pybit.unified_trading import HTTP
import os
import json

# BYBIT API
api_key = os.environ.get("BYBIT_API_KEY")
api_secret = os.environ.get("BYBIT_API_SECRET")
session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

# Telegram
telegram_token = os.environ.get("TELEGRAM_TOKEN")
telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

# Ayarlar
symbol = "SUIUSDT"
binance_symbol = "SUIUSDT"
qty = 1000
interval = "5m"
limit = 30  # SMA21 için yeterli

def get_binance_klines(symbol, interval, limit):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    closes = [float(candle[4]) for candle in data]
    return closes

def calculate_sma(data, period):
    if len(data) < period:
        return None
    return sum(data[-period:]) / period

def get_signal():
    closes = get_binance_klines(binance_symbol, interval, limit)
    sma9 = calculate_sma(closes, 9)
    sma21 = calculate_sma(closes, 21)
    return sma9, sma21

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            if p["symbol"] == symbol:
                size = float(p["size"])
                side = "Buy" if float(p["side"].lower() == "buy") else "Sell"
                return size, side
        return 0, None
    except:
        return 0, None

def close_position(current_side):
    opposite = "Sell" if current_side == "Buy" else "Buy"
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=opposite,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        print("Pozisyon kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def place_order(side):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{side} emri gönderildi.")
    except Exception as e:
        print("Emir gönderilemedi:", e)

def run_bot():
    print("⏳ Binance verisi ile Bybit botu başlatıldı.")
    last_checked = -1

    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.minute != last_checked and now.second == 0:
            last_checked = now.minute

            sma9, sma21 = get_signal()
            if sma9 is None or sma21 is None:
                print("SMA hesaplanamadı.")
                continue

            message = f"*{now.strftime('%H:%M')} SMA Verileri:*\nSMA9: `{sma9:.4f}`\nSMA21: `{sma21:.4f}`"
            send_telegram_message(message)
            print(message)

            signal = "Buy" if sma9 > sma21 else "Sell"
            position_size, current_side = get_position()

            if current_side == signal:
                print("Aynı yönde pozisyon var, işlem yapılmadı.")
            else:
                if position_size > 0:
                    print("Pozisyon yönü ters, pozisyon kapatılıyor.")
                    close_position(current_side)
                    time.sleep(2)
                print(f"Yeni işlem açılıyor: {signal}")
                place_order(signal)
                send_telegram_message(f"*Yeni Pozisyon Açıldı: {signal}*")

        time.sleep(1)

if __name__ == "__main__":
    run_bot()