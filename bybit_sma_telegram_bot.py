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

# Ayarlar
symbol = "SUIUSDT"
qty = 1000
interval = "1m"
binance_symbol = "SUIUSDT"
last_signal = None
pending_signal = None
pending_minute = None
limit_offset = 0.0005
tp_offset = 0.03

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_klines(symbol, interval, limit=210):
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
    df.dropna(inplace=True)
    return df

def calculate_sma(df, period):
    return df["close"].rolling(window=period).mean()

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

def close_position(current_pos, price):
    try:
        if current_pos == "long":
            close_price = round(price + limit_offset, 4)
            side = "Sell"
        else:
            close_price = round(price - limit_offset, 4)
            side = "Buy"

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Limit",
            price=str(close_price),
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        send_telegram_message(f"Pozisyon kapatılıyor: {current_pos.upper()} | Fiyat: {close_price}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_position(direction, price):
    try:
        if direction == "long":
            entry_price = round(price - limit_offset, 4)
            tp_price = round(entry_price + tp_offset, 4)
            side = "Buy"
            tp_side = "Sell"
        else:
            entry_price = round(price + limit_offset, 4)
            tp_price = round(entry_price - tp_offset, 4)
            side = "Sell"
            tp_side = "Buy"

        # Pozisyon açma (limit)
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Limit",
            price=str(entry_price),
            qty=qty,
            time_in_force="GoodTillCancel"
        )

        # TP emri (limit)
        session.place_order(
            category="linear",
            symbol=symbol,
            side=tp_side,
            order_type="Limit",
            price=str(tp_price),
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )

        send_telegram_message(
            f"İşlem açılıyor: {direction.upper()} | Giriş: {entry_price} | TP: {tp_price}"
        )
    except Exception as e:
        print("İşlem açma hatası:", e)

def run_bot():
    global last_signal, pending_signal, pending_minute
    print("✅ Bot limit order ile çalışıyor...")

    last_checked_minute = -1

    while True:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        current_minute = now.minute

        if current_minute != last_checked_minute:
            last_checked_minute = current_minute

            try:
                df = fetch_binance_klines(binance_symbol, interval, limit=210)
                df["sma100"] = calculate_sma(df, 100)
                df["sma200"] = calculate_sma(df, 200)
                df.dropna(inplace=True)

                sma100 = df["sma100"].iloc[-2]
                sma200 = df["sma200"].iloc[-2]
                price = df["close"].iloc[-1]

                log_msg = f"[{now.strftime('%H:%M')}] SMA100: {sma100:.4f} | SMA200: {sma200:.4f} | Fiyat: {price:.4f}"
                print(log_msg)
                send_telegram_message(log_msg)

                current_pos = get_position()
                if current_pos == "long" and price < sma200:
                    close_position("long", price)
                elif current_pos == "short" and price > sma200:
                    close_position("short", price)

                signal = "long" if sma100 > sma200 else "short"
                if signal != last_signal:
                    pending_signal = signal
                    pending_minute = (now + timedelta(minutes=1)).minute
                    last_signal = signal

                if pending_signal and current_minute == pending_minute:
                    current_pos = get_position()
                    if current_pos != pending_signal:
                        if current_pos:
                            close_position(current_pos, price)
                            time.sleep(1)
                        open_position(pending_signal, price)
                    pending_signal = None
                    pending_minute = None

            except Exception as e:
                print("Genel hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()