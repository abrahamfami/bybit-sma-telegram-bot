import time
import requests
import pandas as pd
from datetime import datetime, timezone
from pybit.unified_trading import HTTP
import os

# API Anahtarları (Render'da env olarak tanımlanmalı)
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Ayarlar
symbol = "SUIUSDT"
qty = 1000
leverage = 50
interval = "1m"
binance_symbol = "SUIUSDT"
binance_limit = 50

# Bybit oturumu
session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram hatası:", e)

def set_leverage():
    try:
        session.set_leverage(category="linear", symbol=symbol, buy_leverage=leverage, sell_leverage=leverage)
        print(f"Kaldıraç {leverage}x ayarlandı.")
    except Exception as e:
        print("Kaldıraç ayarlanamadı:", e)

def fetch_binance_klines():
    url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={binance_limit}"
    response = requests.get(url)
    data = response.json()
    closes = [float(candle[4]) for candle in data]
    return closes

def calculate_sma(data, period):
    if len(data) < period:
        return None
    return sum(data[-period:]) / period

def get_signal():
    closes = fetch_binance_klines()
    sma7 = calculate_sma(closes, 7)
    sma9 = calculate_sma(closes, 9)
    sma21 = calculate_sma(closes, 21)
    sma50 = calculate_sma(closes, 50)
    
    signal = None
    if sma7 and sma9 and sma21 and sma50:
        if sma7 > sma9 > sma21 > sma50:
            signal = "LONG"
        elif sma50 > sma21 > sma9 > sma7:
            signal = "SHORT"

    return signal, sma7, sma9, sma21, sma50

def get_position():
    positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
    for p in positions:
        if p["side"] == "Buy" and float(p["size"]) > 0:
            return "LONG"
        elif p["side"] == "Sell" and float(p["size"]) > 0:
            return "SHORT"
    return None

def close_position(current_position):
    side = "Sell" if current_position == "LONG" else "Buy"
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
        print(f"{current_position} pozisyon kapatıldı.")
        send_telegram_message(f"❌ {current_position} pozisyon kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatılamadı:", e)

def open_position(signal):
    try:
        side = "Buy" if signal == "LONG" else "Sell"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{signal} pozisyon açıldı.")
        send_telegram_message(f"✅ {signal} pozisyon açıldı.")
    except Exception as e:
        print("Pozisyon açılamadı:", e)

def run_bot():
    print("⏳ Bot çalışıyor...")
    set_leverage()
    last_signal = None
    last_action_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        current_minute = now.minute

        # Her dakika başı
        if now.second == 0 and current_minute != last_action_minute:
            last_action_minute = current_minute
            signal, sma7, sma9, sma21, sma50 = get_signal()

            timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
            log_message = (
                f"[{timestamp}] SMA7: {sma7:.4f}, SMA9: {sma9:.4f}, SMA21: {sma21:.4f}, SMA50: {sma50:.4f}\n"
                f"Sinyal: {signal or 'YOK'}"
            )
            print(log_message)
            send_telegram_message(log_message)

            if signal and signal != last_signal:
                current_position = get_position()

                if current_position and current_position != signal:
                    close_position(current_position)
                    time.sleep(1)

                open_position(signal)
                last_signal = signal

        time.sleep(0.5)

if __name__ == "__main__":
    run_bot()