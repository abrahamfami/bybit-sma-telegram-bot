import time
import os
import requests
import pandas as pd
from datetime import datetime, timezone
from pybit.unified_trading import HTTP

# API keys
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Trade config
symbol = "SUIUSDT"
qty = 1000
interval = "1m"

# Setup sessions
bybit = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram Hatası:", e)

def fetch_binance_klines():
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=50"
    r = requests.get(url)
    data = r.json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close",
        "volume", "close_time", "quote_asset_volume",
        "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    return df

def get_signal():
    df = fetch_binance_klines()
    closes = df["close"]

    sma7 = closes.rolling(window=7).mean().iloc[-2]
    sma9 = closes.rolling(window=9).mean().iloc[-2]
    sma21 = closes.rolling(window=21).mean().iloc[-2]
    sma50 = closes.rolling(window=50).mean().iloc[-2]

    timestamp = datetime.utcnow().strftime("%H:%M:%S")
    log = f"[{timestamp}] SMA7: {sma7:.2f} | SMA9: {sma9:.2f} | SMA21: {sma21:.2f} | SMA50: {sma50:.2f}"

    if sma7 > sma9 > sma21 > sma50:
        return "Buy", log + "\n→ Sinyal: LONG"
    elif sma50 > sma21 > sma9 > sma7:
        return "Sell", log + "\n→ Sinyal: SHORT"
    else:
        return None, log + "\n→ Sinyal: YOK"

def get_position():
    positions = bybit.get_positions(category="linear")["result"]["list"]
    for p in positions:
        if p["symbol"] == symbol:
            side = p["side"]
            size = float(p["size"])
            return side, size
    return None, 0

def close_position(side, size):
    if size == 0:
        return
    close_side = "Sell" if side == "Buy" else "Buy"
    try:
        bybit.place_order(
            category="linear",
            symbol=symbol,
            side=close_side,
            order_type="Market",
            qty=size,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        print(f"{side} pozisyonu kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def place_order(side):
    try:
        bybit.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=False
        )
        print(f"{side} emri gönderildi.")
    except Exception as e:
        print("Emir gönderilemedi:", e)

def run_bot():
    print("🚀 Gecikmeli Çoklu SMA botu başladı...")
    send_telegram_message("🚀 Gecikmeli SMA botu başlatıldı.")
    
    last_signal = None
    pending_signal = None
    signal_detected_minute = None

    while True:
        now = datetime.now(timezone.utc)
        current_minute = now.minute

        if now.second == 0:
            try:
                signal, log = get_signal()
                send_telegram_message(log)

                if signal and signal != last_signal:
                    pending_signal = signal
                    signal_detected_minute = current_minute

                # İşlem açma zamanı geldi mi kontrolü
                if pending_signal is not None and (current_minute == (signal_detected_minute + 1) % 60):
                    current_side, size = get_position()

                    if size > 0:
                        if current_side != pending_signal:
                            close_position(current_side, size)
                            time.sleep(2)
                            place_order(pending_signal)
                            last_signal = pending_signal
                    else:
                        place_order(pending_signal)
                        last_signal = pending_signal

                    pending_signal = None
                    signal_detected_minute = None

            except Exception as e:
                print("HATA:", e)

            time.sleep(60)
        time.sleep(1)

if __name__ == "__main__":
    run_bot()