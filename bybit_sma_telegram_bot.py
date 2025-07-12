import os
import time
import requests
from datetime import datetime, timezone
from binance.client import Client
from pybit.unified_trading import HTTP

# Çevresel değişkenlerden API anahtarları
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Ayarlar
symbol_binance = "SUIUSDT"
symbol_bybit = "SUIUSDT"
interval = Client.KLINE_INTERVAL_1MINUTE
qty = 1000  # işlem miktarı (SUI)
sma_period_short = 9
sma_period_long = 21

# API istemcileri
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)
bybit_client = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

last_signal = None  # crossover kontrolü için
last_minute = -1

def get_binance_sma_values():
    klines = binance_client.get_klines(symbol=symbol_binance, interval=interval, limit=sma_period_long + 1)
    closes = [float(kline[4]) for kline in klines]

    sma9 = sum(closes[-sma_period_short:]) / sma_period_short
    sma21 = sum(closes[-sma_period_long:]) / sma_period_long

    return sma9, sma21

def get_bybit_position():
    try:
        pos = bybit_client.get_positions(category="linear", symbol=symbol_bybit)["result"]["list"][0]
        size = float(pos["size"])
        side = pos["side"]
        return size, side
    except Exception as e:
        print("Pozisyon bilgisi alınamadı:", e)
        return 0, None

def close_position(current_side):
    try:
        side = "Sell" if current_side == "Buy" else "Buy"
        bybit_client.place_order(
            category="linear",
            symbol=symbol_bybit,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        print("Aktif pozisyon kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_position(side):
    try:
        bybit_client.place_order(
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

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram mesaj hatası:", e)

def run_bot():
    global last_signal, last_minute

    print("✅ SMA Crossover botu başlatıldı (1 dakikalık).")

    while True:
        now = datetime.now(timezone.utc)
        if now.minute != last_minute and now.second == 0:
            last_minute = now.minute

            try:
                sma9, sma21 = get_binance_sma_values()
                msg = f"[{now.strftime('%H:%M')}] SMA9: {sma9:.4f} | SMA21: {sma21:.4f}"
                print(msg)
                send_telegram_message(msg)

                signal = "long" if sma9 > sma21 else "short"

                if signal != last_signal:
                    last_signal = signal
                    size, side = get_bybit_position()

                    if size > 0:
                        if (signal == "long" and side == "Sell") or (signal == "short" and side == "Buy"):
                            close_position(side)
                            time.sleep(2)

                    current_side = "Buy" if signal == "long" else "Sell"
                    if (size == 0) or (side != current_side):
                        open_position(current_side)

            except Exception as e:
                print("HATA:", e)

        time.sleep(0.5)

if __name__ == "__main__":
    run_bot()