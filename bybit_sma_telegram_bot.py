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
qty = 100
interval = "1m"

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def fetch_binance_data(symbol, interval="1m", limit=100):
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

def calculate_ema(df, period):
    return df["close"].ewm(span=period, adjust=False).mean()

def place_order(direction):
    side = "Buy" if direction == "long" else "Sell"
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{direction.upper()} işlemi açıldı.")
        send_telegram_message(f"{direction.upper()} işlemi açıldı.")
    except Exception as e:
        print("İşlem açılamadı:", e)

def run_bot():
    print("📡 Bot başlatıldı...")
    last_minute = -1
    last_trend = None
    crossover_minute = None

    while True:
        now = datetime.now(timezone.utc)
        if now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                df = fetch_binance_data(symbol, interval="1m")
                ema21 = calculate_ema(df, 21).iloc[-1]
                ema34 = calculate_ema(df, 34).iloc[-1]

                # Trend tespiti
                current_trend = "long" if ema21 > ema34 else "short"

                # Crossover kontrolü
                if current_trend != last_trend:
                    crossover_minute = now
                    last_trend = current_trend
                    print("🔁 Crossover algılandı:", current_trend)

                # Kaç dakika geçtiğini hesapla
                minutes_since_crossover = (now - crossover_minute).total_seconds() / 60 if crossover_minute else None

                # Log
                log = f"[{now.strftime('%H:%M')}] EMA21: {ema21:.4f} | EMA34: {ema34:.4f} | Trend: {current_trend} | Kesişimden sonra geçen dakika: {minutes_since_crossover:.1f}" if minutes_since_crossover else "Bekleniyor..."
                print(log)
                send_telegram_message(log)

                # Sadece crossover'dan sonra 10 dakikadan küçükse işlem aç
                if minutes_since_crossover is not None and minutes_since_crossover <= 10:
                    place_order(current_trend)

            except Exception as e:
                print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()