import time
import json
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os
from datetime import datetime, timezone

# === API ve Telegram ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# === Ayarlar ===
symbol = "VINEUSDT"
qty = 5000
TP_PERCENT = 0.10
SL_PERCENT = 0.015
CACHE_FILE = "ema_combo_cache.json"

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": f"[{now}]\n{text}"})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv(symbol, interval="5m", limit=300):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list): return None
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "_"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except:
        return None

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def get_position(symbol):
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return pos
    except:
        return None
    return None

def close_position(symbol, side, qty):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",
            order_type="Market",
            qty=qty,
            reduce_only=True
        )
        time.sleep(1)
        session.cancel_all_orders(category="linear", symbol=symbol)
        send_telegram(f"{symbol} pozisyon kapatıldı ({side})")
    except Exception as e:
        send_telegram(f"{symbol} pozisyon kapama hatası: {e}")

def open_position(symbol, side, qty, entry_price):
    try:
        if side == "Buy":
            tp = round(entry_price * (1 + TP_PERCENT), 5)
            sl = round(entry_price * (1 - SL_PERCENT), 5)
        else:
            tp = round(entry_price * (1 - TP_PERCENT), 5)
            sl = round(entry_price * (1 + SL_PERCENT), 5)

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            take_profit=str(tp),
            stop_loss=str(sl),
            time_in_force="GTC",
            position_idx=0
        )

        send_telegram(f"{symbol} pozisyon açıldı: {side} @ {entry_price:.5f}\nTP: {tp} | SL: {sl}")
    except Exception as e:
        send_telegram(f"{symbol} işlem açma hatası: {e}")

def process_signal(cache):
    df = fetch_ohlcv(symbol)
    if df is None or df.shape[0] < 250:
        send_telegram(f"{symbol} için yeterli veri alınamadı.")
        return

    ema9 = calculate_ema(df, 9)
    ema21 = calculate_ema(df, 21)
    ema250 = calculate_ema(df, 250)

    ema9_now = ema9.iloc[-1]
    ema21_now = ema21.iloc[-1]
    ema250_now = ema250.iloc[-1]

    prev = cache.get(symbol, {})
    ema9_prev = prev.get("EMA9")
    ema21_prev = prev.get("EMA21")

    price = df.iloc[-1]["close"]
    signal = None

    if ema9_prev is not None and ema21_prev is not None:
        if ema9_prev <= ema21_prev and ema9_now > ema21_now and ema9_now > ema250_now and ema21_now < ema250_now:
            signal = "long"
        elif ema9_prev >= ema21_prev and ema9_now < ema21_now and ema9_now < ema250_now and ema21_now > ema250_now:
            signal = "short"

    send_telegram(f"""{symbol} EMA Sinyali:
Önceki EMA9: {ema9_prev if ema9_prev else '---'} | EMA21: {ema21_prev if ema21_prev else '---'}
Şimdi EMA9: {ema9_now:.5f} | EMA21: {ema21_now:.5f} | EMA250: {ema250_now:.5f}
Fiyat: {price:.5f}
Sinyal: {signal.upper() if signal else 'YOK'}""")

    cache[symbol] = {
        "EMA9": ema9_now,
        "EMA21": ema21_now
    }

    if not signal:
        return

    pos = get_position(symbol)
    if pos:
        pos_side = "long" if pos["side"] == "Buy" else "short"
        if pos_side != signal:
            close_position(symbol, pos["side"], qty)
            time.sleep(2)
            open_position(symbol, "Buy" if signal == "long" else "Sell", qty, price)
        else:
            send_telegram(f"{symbol} pozisyon zaten açık ({signal.upper()})")
    else:
        open_position(symbol, "Buy" if signal == "long" else "Sell", qty, price)

# === Ana Döngü ===
while True:
    try:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.second < 10:
            cache = load_cache()
            process_signal(cache)
            save_cache(cache)
            time.sleep(60)
        else:
            time.sleep(5)
    except Exception as e:
        send_telegram(f"Genel Hata: {e}")
        time.sleep(60)