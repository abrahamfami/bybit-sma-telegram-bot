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
qty = 500
interval = "1m"

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def fetch_binance_data(symbol, interval="1m", limit=250):
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

def calculate_ema_tvstyle(close_prices, period):
    ema = [close_prices[0]]
    alpha = 2 / (period + 1)
    for price in close_prices[1:]:
        ema.append((price - ema[-1]) * alpha + ema[-1])
    return pd.Series(ema, index=close_prices.index)

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            if p["side"] == "Buy" and float(p["size"]) > 0:
                return "long"
            elif p["side"] == "Sell" and float(p["size"]) > 0:
                return "short"
    except Exception as e:
        print("Pozisyon alınamadı:", e)
    return None

def close_position(current_pos):
    try:
        if current_pos == "long":
            session.place_order(
                category="linear",
                symbol=symbol,
                side="Sell",
                order_type="Market",
                qty=qty,
                time_in_force="GoodTillCancel",
                reduce_only=True
            )
        elif current_pos == "short":
            session.place_order(
                category="linear",
                symbol=symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
                time_in_force="GoodTillCancel",
                reduce_only=True
            )
        send_telegram_message(f"Pozisyon kapatıldı: {current_pos.upper()}")
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
        send_telegram_message(f"Yeni işlem açıldı: {direction.upper()}")
    except Exception as e:
        print("İşlem açma hatası:", e)

def run_bot():
    print("🚀 EMA100/200 TradingView Stili Bot Başlatıldı")
    last_signal = None
    while True:
        now = datetime.now(timezone.utc)
        if now.second == 0:
            try:
                df = fetch_binance_data(symbol, interval="1m", limit=250)
                close_prices = df["close"]
                ema100 = calculate_ema_tvstyle(close_prices, 100).iloc[-1]
                ema200 = calculate_ema_tvstyle(close_prices, 200).iloc[-1]

                log = f"[{now.strftime('%H:%M')}] EMA100: {ema100:.4f} | EMA200: {ema200:.4f}"
                print(log)
                send_telegram_message(log)

                signal = "long" if ema100 > ema200 else "short"

                if signal != last_signal:
                    current_pos = get_position()
                    if current_pos and current_pos != signal:
                        close_position(current_pos)
                        time.sleep(1)
                    open_position(signal)
                    last_signal = signal

            except Exception as e:
                print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()