import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os
import json
from datetime import datetime

# === API & Telegram Bilgileri ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "MAGICUSDT"
binance_symbol = "MAGICUSDT"
interval = "1m"
position_size = 600
ema_cache_file = "ema_cache_magic_4_15.json"

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"🕒 {now}\n{text}"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_ohlcv(symbol, interval="1m", limit=500):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "_"
    ])
    df["close"] = df["close"].astype(float)
    return df

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def load_ema_cache():
    if os.path.exists(ema_cache_file):
        with open(ema_cache_file, "r") as f:
            return json.load(f)
    return {}

def save_ema_cache(ema4_now, ema15_now):
    data = {
        "ema4_prev": ema4_now,
        "ema15_prev": ema15_now
    }
    with open(ema_cache_file, "w") as f:
        json.dump(data, f)

def detect_crossover_signal():
    df = fetch_binance_ohlcv(binance_symbol, interval)
    if len(df) < 2:
        send_telegram("⚠️ Yetersiz veri: EMA hesaplaması için en az 2 mum gerekiyor.")
        return None, None

    df["EMA4"] = calculate_ema(df, 4)
    df["EMA15"] = calculate_ema(df, 15)

    ema4_now = df.iloc[-1]["EMA4"]
    ema15_now = df.iloc[-1]["EMA15"]
    price = df.iloc[-1]["close"]

    cache = load_ema_cache()
    ema4_prev = cache.get("ema4_prev", df.iloc[-2]["EMA4"])
    ema15_prev = cache.get("ema15_prev", df.iloc[-2]["EMA15"])

    signal = None
    if ema4_prev <= ema15_prev and ema4_now > ema15_now:
        signal = "long"
    elif ema4_prev >= ema15_prev and ema4_now < ema15_now:
        signal = "short"

    log = f"""📡 EMA4/15 CROSSOVER
⏮ EMA4_prev: {ema4_prev:.5f}, EMA15_prev: {ema15_prev:.5f}
▶️ EMA4_now:  {ema4_now:.5f}, EMA15_now:  {ema15_now:.5f}
💰 Fiyat: {price:.5f}
📊 Sinyal: {signal.upper() if signal else "YOK"}
"""
    send_telegram(log)
    save_ema_cache(ema4_now, ema15_now)
    return signal, price

def get_current_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return pos
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon sorgulama hatası: {e}")
    return None

def cancel_all_open_orders():
    try:
        session.cancel_all_orders(category="linear", symbol=symbol)
    except:
        pass

def close_position(side):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",
            order_type="Market",
            qty=position_size,
            reduce_only=True
        )
        time.sleep(1)
        cancel_all_open_orders()
        send_telegram(f"🔴 Pozisyon kapatıldı ({side})")
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon kapama hatası: {e}")

def place_market_order(signal, entry_price):
    try:
        side = "Buy" if signal == "long" else "Sell"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=position_size,
            time_in_force="GTC",
            position_idx=0
        )
        send_telegram(f"📈 POZİSYON AÇILDI: {side} @ {entry_price:.5f}")
    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası: {e}")

# === Ana Döngü (Dakikada bir, sadece crossover'da işlem açar) ===
last_minute = -1

while True:
    try:
        now = datetime.utcnow()
        current_minute = now.minute

        if current_minute != last_minute:
            last_minute = current_minute

            signal, price = detect_crossover_signal()
            if not signal:
                continue

            current_position = get_current_position()
            position_side = None
            if current_position:
                position_side = "long" if current_position["side"] == "Buy" else "short"

            if position_side == signal:
                send_telegram(f"⏸ Aynı yönde pozisyon zaten açık, yeni işlem yapılmadı.")
            else:
                if current_position:
                    close_position(current_position["side"])
                    time.sleep(1)

                place_market_order(signal, price)

        time.sleep(1)

    except Exception as e:
        send_telegram(f"🚨 BOT HATASI:\n{e}")
        time.sleep(60)