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
qty = 2000
TP_PERCENT = 0.20
SL_PERCENT = 0.05
CACHE_FILE = "ema_cache.json"

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": f"🕒 {now}\n{text}"})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv(symbol, interval="5m", limit=100):
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
    return df["close"].ewm(span=period).mean().iloc[-1]

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return pos
    except:
        return None
    return None

def close_position(side):
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
        send_telegram(f"🔴 Pozisyon kapatıldı ({side})")
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon kapama hatası: {e}")

def open_position(side, price):
    try:
        if side == "Buy":
            tp = round(price * (1 + TP_PERCENT), 5)
            sl = round(price * (1 - SL_PERCENT), 5)
        else:
            tp = round(price * (1 - TP_PERCENT), 5)
            sl = round(price * (1 + SL_PERCENT), 5)

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

        send_telegram(f"🟢 Pozisyon Açıldı: {side} @ {price:.5f}\n🎯 TP: {tp} | 🛑 SL: {sl}")
    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası: {e}")

def run_bot():
    df = fetch_ohlcv(symbol)
    if df is None or df.shape[0] < 2:
        send_telegram(f"⚠️ {symbol} için veri alınamadı.")
        return

    ema9_now = calculate_ema(df, 9)
    ema21_now = calculate_ema(df, 21)
    price = df.iloc[-1]["close"]

    cache = load_cache()
    prev_ema9 = cache.get("EMA9")
    prev_ema21 = cache.get("EMA21")

    signal = None
    if prev_ema9 is not None and prev_ema21 is not None:
        if prev_ema9 <= prev_ema21 and ema9_now > ema21_now:
            signal = "long"
        elif prev_ema9 >= prev_ema21 and ema9_now < ema21_now:
            signal = "short"

    prev_ema9_str = f"{prev_ema9:.5f}" if prev_ema9 is not None else "---"
    prev_ema21_str = f"{prev_ema21:.5f}" if prev_ema21 is not None else "---"

    send_telegram(f"""📊 {symbol} Sinyal Kontrolü:
🔁 Önceki EMA9: {prev_ema9_str} | EMA21: {prev_ema21_str}
✅ Şimdi EMA9: {ema9_now:.5f} | EMA21: {ema21_now:.5f}
💰 Fiyat: {price:.5f}
📌 Sinyal: {signal.upper() if signal else 'YOK'}""")

    # Cache güncelle
    cache["EMA9"] = ema9_now
    cache["EMA21"] = ema21_now
    save_cache(cache)

    if not signal:
        return

    current_pos = get_position()
    if current_pos:
        current_side = "long" if current_pos["side"] == "Buy" else "short"
        if current_side != signal:
            close_position(current_pos["side"])
            time.sleep(2)
            open_position("Buy" if signal == "long" else "Sell", price)
        else:
            send_telegram(f"⏸ Pozisyon zaten açık ({signal.upper()})")
    else:
        open_position("Buy" if signal == "long" else "Sell", price)

# === Ana Döngü ===
while True:
    try:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.second < 10:
            run_bot()
            time.sleep(60)
        else:
            time.sleep(5)
    except Exception as e:
        send_telegram(f"🚨 Genel Hata: {e}")
        time.sleep(60)