from pybit.unified_trading import HTTP
import pandas as pd
import time
from datetime import datetime, timezone
import requests
import os

# API anahtarları (Render'da environment variable olarak tanımlanmalı)
api_key = os.environ.get("BYBIT_API_KEY")
api_secret = os.environ.get("BYBIT_API_SECRET")
telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

# Bybit oturumu
session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

# Parametreler
symbol = "SUIUSDT"
qty = 10
leverage = 50
interval = "5"

# Pozisyon yönü takibi
current_position = None  # "long", "short", or None

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": message
        }
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def set_leverage():
    try:
        session.set_leverage(category="linear", symbol=symbol,
                             buy_leverage=leverage, sell_leverage=leverage)
        print(f"Kaldıraç {leverage}x ayarlandı.")
    except Exception as e:
        print("Kaldıraç ayarlanamadı:", e)

def get_sma_signal():
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=21)["result"]["list"]
    df = pd.DataFrame(candles)
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    df['close'] = df['close'].astype(float)

    sma9 = df['close'].rolling(window=9).mean().iloc[-2]
    sma21 = df['close'].rolling(window=21).mean().iloc[-2]
    close = df['close'].iloc[-2]

    return close, sma9, sma21

def close_all_positions():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            size = float(pos['size'])
            side = pos['side']
            if size > 0:
                opposite = "Sell" if side == "Buy" else "Buy"
                session.place_order(
                    category="linear",
                    symbol=symbol,
                    side=opposite,
                    order_type="Market",
                    qty=size,
                    time_in_force="GoodTillCancel"
                )
                print(f"Pozisyon kapatıldı: {side} {size}")
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
    global current_position
    set_leverage()
    print("SMA9 / SMA21 botu başlatıldı (her dakika kontrol).")

    while True:
        now = datetime.now(timezone.utc)
        if now.second == 0:
            try:
                close, sma9, sma21 = get_sma_signal()

                # Telegram bildirimi
                msg = f"[{now.strftime('%H:%M:%S')}] Close: {close:.4f}\nSMA9: {sma9:.4f}\nSMA21: {sma21:.4f}"
                send_telegram_message(msg)

                # Sinyal kontrolü ve pozisyon yönetimi
                if sma9 > sma21 and current_position != "long":
                    close_all_positions()
                    place_order("Buy")
                    current_position = "long"
                    send_telegram_message("📈 SMA9 > SMA21 → LONG açıldı.")

                elif sma9 < sma21 and current_position != "short":
                    close_all_positions()
                    place_order("Sell")
                    current_position = "short"
                    send_telegram_message("📉 SMA9 < SMA21 → SHORT açıldı.")

                else:
                    print("Pozisyon değişmedi.")
            except Exception as e:
                print("HATA:", e)
        time.sleep(1)

if __name__ == "__main__":
    run_bot()