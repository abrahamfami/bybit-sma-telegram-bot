from pybit.unified_trading import HTTP
from datetime import datetime, timezone
import pandas as pd
import time
import os
import requests

# Bybit API
api_key = os.environ.get("BYBIT_API_KEY")
api_secret = os.environ.get("BYBIT_API_SECRET")
session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

# Telegram Ayarları
telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

# Bot ayarları
symbol = "SUIUSDT"
qty = 1000
leverage = 50
interval = "5"

last_signal = None
last_minute = -1

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        data = {"chat_id": telegram_chat_id, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def set_leverage():
    try:
        session.set_leverage(category="linear", symbol=symbol, buy_leverage=leverage, sell_leverage=leverage)
        print(f"Kaldıraç {leverage}x olarak ayarlandı.")
    except Exception as e:
        print("Kaldıraç ayarlanamadı:", e)

def get_sma_signal():
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=30)["result"]["list"]
    df = pd.DataFrame(candles)
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    df['close'] = df['close'].astype(float)

    sma9 = df['close'].rolling(window=9).mean()
    sma21 = df['close'].rolling(window=21).mean()

    prev_sma9 = sma9.iloc[-2]
    prev_sma21 = sma21.iloc[-2]

    return prev_sma9, prev_sma21

def get_position_side():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if float(pos["size"]) > 0:
                return pos["side"]  # "Buy" or "Sell"
        return None
    except Exception as e:
        print("Pozisyon bilgisi alınamadı:", e)
        return None

def close_position():
    try:
        side = get_position_side()
        if not side:
            return
        qty_to_close = qty * 100  # yüksek miktar veriyoruz ki tamamı kapansın
        close_side = "Sell" if side == "Buy" else "Buy"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=close_side,
            order_type="Market",
            qty=qty_to_close,
            reduce_only=True,
            time_in_force="GoodTillCancel"
        )
        print("Aktif pozisyon kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatılamadı:", e)

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
    global last_signal, last_minute
    set_leverage()
    print("Bybit SMA strateji botu başlatıldı.")
    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                sma9, sma21 = get_sma_signal()
                signal = "Buy" if sma9 < sma21 else "Sell"
                msg = f"[{now.strftime('%H:%M')}] SMA9: {sma9:.4f} | SMA21: {sma21:.4f} → {signal}"
                print(msg)
                send_telegram_message(msg)

                if signal != last_signal:
                    close_position()
                    place_order(signal)
                    last_signal = signal

                time.sleep(5)
            except Exception as e:
                print("HATA:", e)
        time.sleep(0.5)

if __name__ == "__main__":
    run_bot()