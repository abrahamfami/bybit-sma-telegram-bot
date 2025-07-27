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
qty_per_order = 10
max_position = 200
interval = "5m"

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def fetch_binance_data(symbol, interval="5m", limit=100):
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

def get_position_info():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            if p["side"] == "Buy":
                size = float(p["size"])
                pnl = float(p["unrealisedPnl"])
                return size, pnl
    except Exception as e:
        print("Pozisyon bilgisi alınamadı:", e)
    return 0, 0

def place_long_order(qty):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Buy",
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"✅ LONG pozisyon açıldı: {qty} SUI")
    except Exception as e:
        print("Long işlemi açılırken hata:", e)

def close_position(qty):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell",
            order_type="Market",
            qty=qty,
            reduce_only=True,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"🚨 Pozisyon kapatıldı: {qty} SUI")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def run_bot():
    print("📡 Bot çalışıyor...")
    last_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.minute != last_minute and now.second == 0:
            last_minute = now.minute

            try:
                df = fetch_binance_data(symbol, interval)
                ema21 = calculate_ema(df, 21).iloc[-1]
                current_price = df["close"].iloc[-1]

                size, pnl = get_position_info()

                log_msg = (
                    f"[{now.strftime('%H:%M')}] EMA21: {ema21:.4f} | "
                    f"Fiyat: {current_price:.4f} | Pozisyon: {size} SUI | PnL: {pnl:.2f}$"
                )
                print(log_msg)
                send_telegram_message(log_msg)

                # PnL 10$'ı geçtiyse pozisyon kapat
                if pnl > 10:
                    close_position(size)
                    continue

                # Pozisyon limiti altındaysa ve fiyat ema21 altında ise long aç
                if size + qty_per_order <= max_position and current_price < ema21:
                    place_long_order(qty_per_order)

            except Exception as e:
                print("Genel hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()