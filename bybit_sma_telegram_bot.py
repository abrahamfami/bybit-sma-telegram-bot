import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os
from datetime import datetime

# === API ve Telegram Bilgileri ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "VINEUSDT"  # Binance futures için
bybit_symbol = "VINEUSDT"  # Bybit için sembol (VINEUSDT.P ile çalışır)
position_size = 4000
tp_percent = 0.1
sl_percent = 0.05

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_text = f"🕒 {now}\n{text}"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": full_text})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv(symbol="VINEUSDT", interval="5m", limit=200):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list):
            send_telegram(f"❌ Binance OHLCV format hatası: {data}")
            return None
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "_"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        send_telegram(f"❌ Binance OHLCV alınamadı: {e}")
        return None

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def detect_crossover_signal():
    df = fetch_ohlcv(symbol, "5m")
    if df is None or df.shape[0] < 2:
        send_telegram("⚠️ Yetersiz veri: EMA için en az 2 mum gerekiyor.")
        return None, None

    df["EMA9"] = calculate_ema(df, 9)
    df["EMA21"] = calculate_ema(df, 21)

    ema9_prev = df.iloc[-2]["EMA9"]
    ema21_prev = df.iloc[-2]["EMA21"]
    ema9_now = df.iloc[-1]["EMA9"]
    ema21_now = df.iloc[-1]["EMA21"]
    price = df.iloc[-1]["close"]

    signal = None
    if ema9_prev <= ema21_prev and ema9_now > ema21_now:
        signal = "long"
    elif ema9_prev >= ema21_prev and ema9_now < ema21_now:
        signal = "short"

    log = f"""📡 EMA Crossover Log (5m)
🔁 Önceki:
  EMA9: {ema9_prev:.4f} | EMA21: {ema21_prev:.4f}
✅ Şimdi:
  EMA9: {ema9_now:.4f} | EMA21: {ema21_now:.4f}
💰 Fiyat: {price:.4f}
📊 Sinyal: {signal.upper() if signal else 'YOK'}
"""
    send_telegram(log)
    return signal, price

def get_current_position():
    try:
        positions = session.get_positions(category="linear", symbol=bybit_symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return pos
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon sorgulama hatası: {e}")
    return None

def cancel_all_open_orders():
    try:
        session.cancel_all_orders(category="linear", symbol=bybit_symbol)
        send_telegram("📛 Açık emirler iptal edildi.")
    except Exception as e:
        send_telegram(f"⚠️ Emir iptal hatası: {e}")

def close_position(side):
    try:
        session.place_order(
            category="linear",
            symbol=bybit_symbol,
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
            tp_price = round(entry_price * (1 + tp_percent), 6)
            sl_price = round(entry_price * (1 - sl_percent), 6)
        else:
            side = "Sell"
            tp_price = round(entry_price * (1 - tp_percent), 6)
            sl_price = round(entry_price * (1 + sl_percent), 6)

        session.place_order(
            category="linear",
            symbol=bybit_symbol,
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
        now = datetime.utcnow()
        minute = now.minute
        second = now.second

        if minute % 5 == 0 and second < 10:
            signal, price = detect_crossover_signal()

            if not signal:
                time.sleep(60)
                continue

            current_position = get_current_position()
            position_side = None
            if current_position:
                position_side = "long" if current_position["side"] == "Buy" else "short"

            if position_side != signal:
                if current_position:
                    close_position(current_position["side"])
                    time.sleep(2)
                place_order_with_tp_sl(signal, price)
            else:
                send_telegram(f"⏸ Pozisyon zaten açık ({signal.upper()}), işlem yapılmadı.")

            time.sleep(60)
        else:
            time.sleep(5)

    except Exception as e:
        send_telegram(f"🚨 Bot Hatası:\n{e}")
        time.sleep(60)