import requests
import pandas as pd
import time
from datetime import datetime, timezone
import os
from pybit.unified_trading import HTTP

# API bilgileri
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Ayarlar
symbol_binance = "SUIUSDT"
symbol_bybit = "SUIUSDT"
interval = "5m"
qty = 1000

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def get_binance_sma():
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol_binance}&interval={interval}&limit=30"
    response = requests.get(url)
    df = pd.DataFrame(response.json(), columns=[
        "timestamp", "open", "high", "low", "close",
        "volume", "close_time", "quote_asset_volume",
        "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    df["sma9"] = df["close"].rolling(window=9).mean()
    df["sma21"] = df["close"].rolling(window=21).mean()
    return df

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol_bybit)["result"]["list"]
        for pos in positions:
            side = pos["side"]
            size = float(pos["size"])
            if size > 0:
                return side, size
        return None, 0
    except Exception as e:
        print("Pozisyon alınamadı:", e)
        return None, 0

def close_position(current_side):
    opp_side = "Sell" if current_side == "Buy" else "Buy"
    _, size = get_position()
    if size > 0:
        try:
            session.place_order(
                category="linear",
                symbol=symbol_bybit,
                side=opp_side,
                order_type="Market",
                qty=size,
                time_in_force="GoodTillCancel",
                reduce_only=True
            )
            print(f"Mevcut pozisyon kapatıldı: {current_side}")
        except Exception as e:
            print("Pozisyon kapatılamadı:", e)

def place_order(side):
    try:
        session.place_order(
            category="linear",
            symbol=symbol_bybit,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{side} emri gönderildi.")
    except Exception as e:
        print("Emir gönderilemedi:", e)

def run_bot():
    print("🚀 SMA Crossover botu başladı.")
    last_signal = None
    last_minute_telegram = -1

    while True:
        now = datetime.now(timezone.utc)
        try:
            df = get_binance_sma()
            sma9 = df["sma9"].iloc[-2]
            sma21 = df["sma21"].iloc[-2]
            signal = "Buy" if sma9 > sma21 else "Sell"

            # Telegram bildirimi yalnızca dakikada bir
            if now.minute != last_minute_telegram and now.second == 0:
                send_telegram(f"[{now.strftime('%H:%M')}] SMA9: {sma9:.4f} | SMA21: {sma21:.4f}")
                last_minute_telegram = now.minute

            # Her 5 dakikada bir işlem kontrolü
            if now.minute % 5 == 0 and now.second == 0:
                if signal != last_signal:
                    current_pos, _ = get_position()
                    if current_pos and current_pos != signal:
                        close_position(current_pos)
                        time.sleep(1)
                        place_order(signal)
                    elif not current_pos:
                        place_order(signal)
                    last_signal = signal

        except Exception as e:
            print("Genel HATA:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()