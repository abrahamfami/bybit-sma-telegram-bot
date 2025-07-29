import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os

# === API ve Telegram Bilgileri ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "SUIUSDT"
position_size = 500
tp_percent = 0.03
sl_percent = 0.01

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv(symbol, interval="5m", limit=200):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "_", "_", "_", "_", "_", "_"
    ])
    df["close"] = df["close"].astype(float)
    return df

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def detect_crossover_signal():
    df = fetch_ohlcv("SUIUSDT", "5m")
    df["EMA9"] = calculate_ema(df, 9)
    df["EMA21"] = calculate_ema(df, 21)
    df["EMA200"] = calculate_ema(df, 200)

    ema9_prev = df.iloc[-2]["EMA9"]
    ema21_prev = df.iloc[-2]["EMA21"]

    ema9_now = df.iloc[-1]["EMA9"]
    ema21_now = df.iloc[-1]["EMA21"]
    ema200_now = df.iloc[-1]["EMA200"]
    price = df.iloc[-1]["close"]

    signal = None

    # CROSS UP → LONG (EMA9 aşağıdan yukarı kesti) + trend doğrulaması
    if ema9_prev <= ema21_prev and ema9_now > ema21_now and ema21_now > ema200_now:
        signal = "long"

    # CROSS DOWN → SHORT (EMA9 yukarıdan aşağı kesti) + trend doğrulaması
    elif ema9_prev >= ema21_prev and ema9_now < ema21_now and ema21_now < ema200_now:
        signal = "short"

    log = f"""📡 EMA Crossover Log (5m)
🔁 Önceki:
  EMA9: {ema9_prev:.4f} | EMA21: {ema21_prev:.4f}
✅ Şimdi:
  EMA9: {ema9_now:.4f} | EMA21: {ema21_now:.4f} | EMA200: {ema200_now:.4f}
💰 Fiyat: {price:.4f}
📊 Sinyal: {signal.upper() if signal else 'YOK'}
"""
    send_telegram(log)
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
        send_telegram("📛 Açık TP/SL emirleri iptal edildi.")
    except Exception as e:
        send_telegram(f"⚠️ Emir iptal hatası: {e}")

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
            tp_price = round(entry_price * (1 + tp_percent), 4)
            sl_price = round(entry_price * (1 - sl_percent), 4)
        else:
            side = "Sell"
            tp_price = round(entry_price * (1 - tp_percent), 4)
            sl_price = round(entry_price * (1 + sl_percent), 4)

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
            f"🟢 Pozisyon Açıldı: {signal.upper()} @ {entry_price:.4f}\n🎯 TP: {tp_price} | 🛑 SL: {sl_price}"
        )
        return True
    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası: {e}")
        return False

# === Ana Döngü ===
while True:
    try:
        signal, price = detect_crossover_signal()
        if not signal:
            time.sleep(300)
            continue  # Sinyal yoksa atla

        current_position = get_current_position()
        position_side = None
        if current_position:
            position_side = "long" if current_position["side"] == "Buy" else "short"

        if position_side == signal:
            send_telegram(f"⏸ Pozisyon zaten açık ({signal.upper()}), işlem açılmadı.")
        else:
            if current_position:
                close_position(current_position["side"])
                time.sleep(2)

            place_order_with_tp_sl(signal, price)

        time.sleep(300)

    except Exception as e:
        send_telegram(f"🚨 Bot Hatası:\n{e}")
        time.sleep(300)