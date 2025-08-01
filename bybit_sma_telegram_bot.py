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
max_position_size = 1000
trade_qty = 1000

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": f"🕒 {now}\n{text}"})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_ohlcv():
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit=50"
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
                return pos
    except Exception as e:
        send_telegram(f"⚠️ Pozisyon sorgulama hatası: {e}")
    return None

def open_position(signal):
    try:
        side = "Buy" if signal == "long" else "Sell"
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=trade_qty,
            time_in_force="GTC",
            position_idx=0
        )
        send_telegram(f"🟢 İşlem açıldı: {signal.upper()} ({trade_qty} VINE)")
    except Exception as e:
        send_telegram(f"⛔️ Pozisyon açma hatası: {e}")

def determine_signal(price, ema9):
    return "short" if price > ema9 else "long"

# === Ana Döngü ===
while True:
    try:
        now = datetime.now(timezone.utc)
        if now.second < 10:
            df = fetch_ohlcv()
            if df is None or len(df) < 10:
                time.sleep(60)
                continue

            df["EMA9"] = calculate_ema(df, 9)
            ema9_now = df["EMA9"].iloc[-1]
            price = df["close"].iloc[-1]
            signal = determine_signal(price, ema9_now)

            pos = get_position()
            current_size = float(pos["size"]) if pos else 0
            new_total_size = current_size + trade_qty

            send_telegram(f"""📈 EMA9 İşlem Kontrolü:
Fiyat: {price:.5f} | EMA9: {ema9_now:.5f}
Sinyal: {signal.upper()}
Aktif Pozisyon: {current_size} VINE
Yeni Toplam Pozisyon: {new_total_size} VINE""")

            if new_total_size <= max_position_size:
                open_position(signal)
            else:
                send_telegram("⛔️ Maksimum pozisyon limitine ulaşıldı. Yeni işlem açılmadı.")

            time.sleep(60)
        else:
            time.sleep(5)

    except Exception as e:
        send_telegram(f"🚨 Bot Hatası: {e}")
        time.sleep(60)