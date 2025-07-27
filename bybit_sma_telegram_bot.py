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
qty_per_trade = 25
max_position_size = 999
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
    url = "https://api.binance.com/api/v3/klines"
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
            size = float(p["size"])
            if size > 0:
                return {
                    "size": size,
                    "side": p["side"],
                    "entry_price": float(p["entryPrice"])
                }
        return {"size": 0, "side": "-", "entry_price": 0}
    except Exception as e:
        print("Pozisyon bilgisi alınamadı:", e)
        return {"size": 0, "side": "-", "entry_price": 0}

def close_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            size = float(p["size"])
            if size > 0:
                side = "Sell" if p["side"] == "Buy" else "Buy"
                session.place_order(
                    category="linear",
                    symbol=symbol,
                    side=side,
                    order_type="Market",
                    qty=size,
                    time_in_force="GoodTillCancel",
                    reduce_only=True
                )
        send_telegram_message("Pozisyon kapatıldı.")
        print("🔻 Pozisyon kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatılamadı:", e)

def place_order(direction):
    side = "Buy" if direction == "long" else "Sell"
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty_per_trade,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"{direction.upper()} işlemi açıldı - {qty_per_trade} SUI")
        print(f"✅ {direction.upper()} işlemi açıldı.")
    except Exception as e:
        print("İşlem açılamadı:", e)

def run_bot():
    print("📡 Bot başlatıldı...")
    last_minute = -1

    while True:
        now = datetime.now(timezone.utc)
        if now.minute != last_minute and now.second == 0:
            last_minute = now.minute
            try:
                df = fetch_binance_data(symbol)
                ema21 = calculate_ema(df, 21).iloc[-1]
                price = df["close"].iloc[-1]

                position = get_position_info()
                pos_log = f"{position['side']} | {position['size']} SUI @ {position['entry_price']:.4f}" if position['size'] > 0 else "Açık pozisyon yok"

                log = (
                    f"[{now.strftime('%H:%M')}] EMA21: {ema21:.4f} | Fiyat: {price:.4f}\n"
                    f"Pozisyon: {pos_log}"
                )
                print(log)
                send_telegram_message(log)

                direction = "long" if price > ema21 else "short"

                if position["size"] > max_position_size:
                    close_position()
                    time.sleep(1)

                place_order(direction)

            except Exception as e:
                print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()