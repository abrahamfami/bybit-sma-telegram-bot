import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from pybit.unified_trading import HTTP
from binance.client import Client as BinanceClient

# ENV
bybit_key = os.environ.get("BYBIT_API_KEY")
bybit_secret = os.environ.get("BYBIT_API_SECRET")
telegram_token = os.environ.get("TELEGRAM_TOKEN")
telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

# Bybit ve Binance bağlantısı
bybit = HTTP(api_key=bybit_key, api_secret=bybit_secret)
binance = BinanceClient()

symbol_binance = "SUIUSDT"
symbol_bybit = "SUIUSDT"
interval = "5m"
qty = 1000
leverage = 50

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print("Telegram mesaj hatası:", response.text)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def set_leverage():
    try:
        bybit.set_leverage(category="linear", symbol=symbol_bybit,
                           buy_leverage=leverage, sell_leverage=leverage)
    except Exception as e:
        print("Kaldıraç ayarlanamadı:", e)

def fetch_binance_sma():
    klines = binance.get_klines(symbol=symbol_binance, interval=interval, limit=21)
    closes = [float(k[4]) for k in klines]
    df = pd.DataFrame({'close': closes})
    df['sma9'] = df['close'].rolling(window=9).mean()
    df['sma21'] = df['close'].rolling(window=21).mean()
    sma9 = df['sma9'].iloc[-2]
    sma21 = df['sma21'].iloc[-2]
    return sma9, sma21

def get_current_position():
    try:
        pos = bybit.get_positions(category="linear", symbol=symbol_bybit)["result"]["list"][0]
        size = float(pos["size"])
        side = pos["side"]
        return size, side
    except:
        return 0, None

def close_position():
    size, side = get_current_position()
    if size == 0:
        return
    opposite = "Sell" if side == "Buy" else "Buy"
    try:
        bybit.place_order(
            category="linear",
            symbol=symbol_bybit,
            side=opposite,
            order_type="Market",
            qty=size,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        print(f"Pozisyon kapatıldı: {side} {size}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_position(side):
    try:
        bybit.place_order(
            category="linear",
            symbol=symbol_bybit,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{side} pozisyon açıldı.")
    except Exception as e:
        print("Pozisyon açma hatası:", e)

def run_bot():
    set_leverage()
    last_minute = -1
    print("Bot başladı (5 dakikalık SMA kontrolleri).")
    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                sma9, sma21 = fetch_binance_sma()
                msg = f"🟩 *SMA9*: {sma9:.4f}\n🟥 *SMA21*: {sma21:.4f}"
                print(msg)
                send_telegram_message(msg)

                size, side = get_current_position()

                if sma9 > sma21:
                    if side == "Sell":
                        close_position()
                    if side != "Buy":
                        open_position("Buy")
                        send_telegram_message("📈 SMA9 > SMA21 → LONG açıldı")
                elif sma9 < sma21:
                    if side == "Buy":
                        close_position()
                    if side != "Sell":
                        open_position("Sell")
                        send_telegram_message("📉 SMA9 < SMA21 → SHORT açıldı")

                time.sleep(5)
            except Exception as e:
                print("Hata:", e)
        time.sleep(1)

if __name__ == "__main__":
    run_bot()