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

symbol = "SUIUSDT"
qty = 10
interval = "5m"  # Binance'ten veri çekerken kullanılacak zaman aralığı

# Bybit API bağlantısı
session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesaj hatası:", e)

def fetch_binance_data(symbol="SUIUSDT", interval="5m", limit=60):
    url = "https://api.binance.com/api/v3/klines"
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

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def get_current_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            size = float(p["size"])
            side = p["side"]
            if size > 0:
                return "long" if side == "Buy" else "short"
    except Exception as e:
        print("Pozisyon sorgu hatası:", e)
    return None

def close_position(current_pos):
    try:
        side = "Sell" if current_pos == "long" else "Buy"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        send_telegram_message(f"❌ Pozisyon kapatıldı: {current_pos.upper()}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_position(direction):
    try:
        side = "Buy" if direction == "long" else "Sell"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"✅ Yeni pozisyon açıldı: {direction.upper()}")
    except Exception as e:
        print("Pozisyon açma hatası:", e)

def run_bot():
    print("🚀 EMA21 vs EMA50 BOT AKTİF")
    last_checked_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.minute != last_checked_minute and now.second == 0:
            last_checked_minute = now.minute
            try:
                df = fetch_binance_data(symbol=symbol, interval=interval)
                df["ema21"] = calculate_ema(df["close"], 21)
                df["ema50"] = calculate_ema(df["close"], 50)

                ema21 = df["ema21"].iloc[-1]
                ema50 = df["ema50"].iloc[-1]
                price = df["close"].iloc[-1]

                signal = "long" if ema21 > ema50 else "short"
                current_pos = get_current_position()

                log = f"[{now.strftime('%H:%M')}] EMA21: {ema21:.4f} | EMA50: {ema50:.4f} | Fiyat: {price:.4f} | Sinyal: {signal.upper()} | Aktif: {current_pos}"
                print(log)
                send_telegram_message(log)

                if current_pos is None:
                    open_position(signal)
                elif current_pos != signal:
                    close_position(current_pos)
                    time.sleep(1)
                    open_position(signal)
                else:
                    open_position(signal)

            except Exception as e:
                print("Genel hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()