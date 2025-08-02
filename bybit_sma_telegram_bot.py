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
position_size = 2000
tp_percent = 0.006  # %0.6 TP
sl_percent = 0.01   # %1 SL
ema_cache_file = "ema_cache_magic_reverse.json"

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

def save_ema_cache(ema9_now, ema21_now):
    data = {
        "ema9_prev": ema9_now,
        "ema21_prev": ema21_now
    }
    with open(ema_cache_file, "w") as f:
        json.dump(data, f)

def detect_crossover_signal():
    df = fetch_binance_ohlcv(binance_symbol, interval)
    df["EMA9"] = calculate_ema(df, 9)
    df["EMA21"] = calculate_ema(df, 21)

    ema9_now = df.iloc[-1]["EMA9"]
    ema21_now = df.iloc[-1]["EMA21"]
    price = df.iloc[-1]["close"]

    cache = load_ema_cache()
    ema9_prev = cache.get("ema9_prev", df.iloc[-2]["EMA9"])
    ema21_prev = cache.get("ema21_prev", df.iloc[-2]["EMA21"])

    signal = None
    # ⛔️ TERS SİNYAL MANTIĞI
    if ema9_prev >= ema21_prev and ema9_now < ema21_now:
        signal = "long"
    elif ema9_prev <= ema21_prev and ema9_now > ema21_now:
        signal = "short"

    log = f"""📡 EMA9/21 REVERSE CROSSOVER
⏮ EMA9_prev: {ema9_prev:.5f}, EMA21_prev: {ema21_prev:.5f}
▶️ EMA9_now:  {ema9_now:.5f}, EMA21_now:  {ema21_now:.5f}
💰 Fiyat: {price:.5f}
📊 Sinyal: {signal.upper() if signal else "YOK"}
"""
    send_telegram(log)
    save_ema_cache(ema9_now, ema21_now)
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

def place_order_with_tp_sl(signal, entry_price):
    try:
        if signal == "long":
            side = "Buy"
            tp_price = round(entry_price * (1 + tp_percent), 5)
            sl_price = round(entry_price * (1 - sl_percent), 5)
        else:
            side = "Sell"
            tp_price = round(entry_price * (1 - tp_percent), 5)
            sl_price = round(entry_price * (1 + sl_percent), 5)

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=position_size,
            take_profit=str(tp_price),
            stop_loss=str(sl_price),
            time_in_force="GTC",
            position_idx=0
        )

        send_telegram(
            f"📈 POZİSYON AÇILDI (TERS): {side} @ {entry_price:.5f}\n🎯 TP: {tp_price} | 🛑 SL: {sl_price}"
        )
    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası: {e}")

# === Ana Döngü ===
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
                send_telegram(f"⏸ Pozisyon zaten açık ({signal.upper()}), yeni işlem yapılmadı.")
            elif position_side and position_side != signal:
                send_telegram("🔁 Ters sinyal algılandı. Pozisyon değiştiriliyor...")
                close_position(current_position["side"])
                time.sleep(1)
                place_order_with_tp_sl(signal, price)
            elif not current_position:
                place_order_with_tp_sl(signal, price)

        time.sleep(1)

    except Exception as e:
        send_telegram(f"🚨 BOT HATASI:\n{e}")
        time.sleep(60)