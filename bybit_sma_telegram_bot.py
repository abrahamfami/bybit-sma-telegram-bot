import requests
import pandas as pd
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta, timezone
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
bybit_symbol = "SUIUSDT"
last_signal = None
last_signal_time = None

# Bybit oturumu
session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# Telegram mesajı gönder
def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

# Binance verisini çek
def fetch_binance_klines(symbol, interval, limit=50):
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

# SMA hesapla
def calculate_sma(df, period):
    return df["close"].rolling(window=period).mean()

# Mevcut pozisyonu al
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

# Pozisyonu kapat
def close_position(current_pos):
    try:
        if current_pos == "long":
            session.place_order(
                category="linear",
                symbol=bybit_symbol,
                side="Sell",
                order_type="Market",
                qty=qty,
                time_in_force="GoodTillCancel",
                reduce_only=True
            )
        elif current_pos == "short":
            session.place_order(
                category="linear",
                symbol=bybit_symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
                time_in_force="GoodTillCancel",
                reduce_only=True
            )
        send_telegram_message(f"Pozisyon kapatıldı: {current_pos.upper()}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

# Pozisyon aç
def open_position(direction):
    try:
        side = "Buy" if direction == "long" else "Sell"
        session.place_order(
            category="linear",
            symbol=bybit_symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"Yeni işlem açıldı: {direction.upper()}")
    except Exception as e:
        print("İşlem açma hatası:", e)

# Ana döngü
def run_bot():
    global last_signal, last_signal_time
    print("✅ Bot çalışıyor...")

    while True:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

        try:
            df = fetch_binance_klines(symbol, interval)
            df["sma9"] = calculate_sma(df, 9)
            df["sma21"] = calculate_sma(df, 21)

            sma9 = df["sma9"].iloc[-2]
            sma21 = df["sma21"].iloc[-2]

            log_msg = f"[{now.strftime('%H:%M')}] SMA9: {sma9:.4f} | SMA21: {sma21:.4f}"
            print(log_msg)
            send_telegram_message(log_msg)

            # Sinyal üret
            if sma9 > sma21:
                signal = "long"
            elif sma9 < sma21:
                signal = "short"
            else:
                signal = None

            # Sinyal değiştiyse zamanı kaydet
            if signal and signal != last_signal:
                last_signal = signal
                last_signal_time = now

            # Sinyal 1 dakika önce geldiyse işlem aç
            if last_signal and last_signal_time and now == last_signal_time + timedelta(minutes=1):
                current_pos = get_position()
                if current_pos != last_signal:
                    if current_pos:
                        close_position(current_pos)
                        time.sleep(1)
                    open_position(last_signal)

        except Exception as e:
            print("Genel hata:", e)

        time.sleep(60)

if __name__ == "__main__":
    run_bot()