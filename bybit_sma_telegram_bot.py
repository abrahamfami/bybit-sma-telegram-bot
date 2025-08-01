import time
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os
from datetime import datetime, timezone

# === API ve Telegram Bilgileri ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

symbol = "VINEUSDT"
qty = 1000  # AÇILACAK işlem miktarı = MAX pozisyon

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": f"🕒 {now}\n{text}"})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv():
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit=10"
    try:
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "_"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        send_telegram(f"❌ Binance verisi alınamadı: {e}")
        return None

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean()

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return {
                    "side": pos["side"],  # "Buy" or "Sell"
                    "size": float(pos["size"])
                }
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon sorgulama hatası: {e}")
    return None

def close_position(current_side):
    try:
        closing_side = "Sell" if current_side == "Buy" else "Buy"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=closing_side,
            order_type="Market",
            qty=qty,
            reduce_only=True
        )
        send_telegram(f"🔴 Pozisyon kapatıldı: {current_side}")
    except Exception as e:
        send_telegram(f"❌ Pozisyon kapama hatası: {e}")

def open_position(signal):
    try:
        side = "Buy" if signal == "long" else "Sell"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GTC",
            position_idx=0  # düz pozisyon (hedge değil)
        )
        send_telegram(f"🟢 Pozisyon açıldı: {signal.upper()} | Miktar: {qty} VINE")
    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası: {e}")

def determine_signal(price, ema9):
    return "short" if price > ema9 else "long"

# === Ana Döngü ===
wait_for_next_signal = False

while True:
    try:
        now = datetime.now(timezone.utc)
        if now.second < 10:
            df = fetch_ohlcv()
            if df is None or len(df) < 5:
                time.sleep(60)
                continue

            df["EMA9"] = calculate_ema(df, 9)
            ema9_now = df["EMA9"].iloc[-1]
            price = df["close"].iloc[-1]
            signal = determine_signal(price, ema9_now)

            pos = get_position()
            status = f"""📊 EMA9 KONTROL:
Fiyat: {price:.5f} | EMA9: {ema9_now:.5f}
Sinyal: {signal.upper()}
Pozisyon: {"YOK" if not pos else pos['side'] + " - " + str(pos['size'])}
"""
            send_telegram(status)

            if wait_for_next_signal:
                wait_for_next_signal = False
                send_telegram("✅ Yeni mum geldi, işlem açılabilir.")
                if not pos:
                    open_position(signal)
                time.sleep(60)
                continue

            if not pos:
                open_position(signal)
            else:
                current_side = "long" if pos["side"] == "Buy" else "short"
                if current_side != signal:
                    close_position(pos["side"])
                    wait_for_next_signal = True
                else:
                    send_telegram("⏸ Aynı yönde pozisyon açık, işlem yapılmadı.")

            time.sleep(60)
        else:
            time.sleep(5)
    except Exception as e:
        send_telegram(f"🚨 Bot Hatası: {e}")
        time.sleep(60)