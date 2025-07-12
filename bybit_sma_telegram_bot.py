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
qty = 1000
interval = "1m"
last_signal = None

session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_klines(symbol, interval, limit=250):
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

def calculate_sma(df, period):
    return df["close"].rolling(window=period).mean()

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            if float(p["size"]) > 0:
                return p["side"].lower(), float(p["avgPrice"])
    except Exception as e:
        print("Pozisyon alınamadı:", e)
    return None, None

def close_position(current_side):
    try:
        reverse = "Buy" if current_side == "Sell" else "Sell"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=reverse,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        send_telegram_message(f"❌ Mevcut pozisyon kapatıldı: {current_side.upper()}")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_market_order(direction):
    side = "Buy" if direction == "long" else "Sell"
    try:
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        price = float(response['result']['avgPrice'])
        send_telegram_message(f"✅ Yeni {direction.upper()} işlemi açıldı. Giriş fiyatı: {price}")
        return price
    except Exception as e:
        print("Market order hatası:", e)
        return None

def set_tp_sl(direction, entry_price):
    try:
        # Sabit farkla belirlenmiş TP/SL
        tp = round(entry_price + 0.03, 4) if direction == "long" else round(entry_price - 0.03, 4)
        sl = round(entry_price - 0.01, 4) if direction == "long" else round(entry_price + 0.01, 4)
        side = "Sell" if direction == "long" else "Buy"

        # TP
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Limit",
            qty=qty,
            price=str(tp),
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        # SL
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Limit",
            qty=qty,
            price=str(sl),
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        send_telegram_message(f"🎯 TP: {tp} | 🛑 SL: {sl}")
    except Exception as e:
        print("TP/SL ayarlanamadı:", e)

def run_bot():
    global last_signal
    print("📡 SMA100/200 Bot başlatıldı.")
    while True:
        now = datetime.now(timezone.utc)
        if now.second == 0:
            try:
                df = fetch_binance_klines(symbol, interval)
                df["sma100"] = calculate_sma(df, 100)
                df["sma200"] = calculate_sma(df, 200)

                sma100 = df["sma100"].iloc[-2]
                sma200 = df["sma200"].iloc[-2]
                current_price = df["close"].iloc[-1]

                if pd.isna(sma100) or pd.isna(sma200):
                    print("Yeterli veri yok.")
                    time.sleep(1)
                    continue

                log_msg = f"[{now.strftime('%H:%M')}] SMA100: {sma100:.4f} | SMA200: {sma200:.4f} | Fiyat: {current_price:.4f}"
                print(log_msg)
                send_telegram_message(log_msg)

                signal = "long" if sma100 > sma200 else "short"
                if signal != last_signal:
                    pos_side, _ = get_position()
                    if pos_side and pos_side != signal:
                        close_position("Buy" if pos_side == "long" else "Sell")
                        time.sleep(1)
                    entry = open_market_order(signal)
                    if entry:
                        time.sleep(20)
                        set_tp_sl(signal, entry)
                    last_signal = signal

            except Exception as e:
                print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()