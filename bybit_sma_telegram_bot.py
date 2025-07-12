from pybit.unified_trading import HTTP
import time
from datetime import datetime, timezone
import statistics
import os
import requests

# Bybit API
api_key = os.environ.get("BYBIT_API_KEY")
api_secret = os.environ.get("BYBIT_API_SECRET")

# Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Sabitler
symbol = "SUIUSDT"
qty = 1000
leverage = 50
interval_minutes = 5

# Canlı fiyat geçmişi
price_history = []

session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram hatası:", e)

def set_leverage():
    try:
        session.set_leverage(category="linear", symbol=symbol, buy_leverage=leverage, sell_leverage=leverage)
        print(f"Kaldıraç {leverage}x ayarlandı.")
    except Exception as e:
        print("Kaldıraç ayarlanamadı:", e)

def get_live_price():
    try:
        return float(session.get_ticker(category="linear", symbol=symbol)["result"]["list"][0]["lastPrice"])
    except Exception as e:
        print("Fiyat alınamadı:", e)
        return None

def calculate_sma(data, period):
    if len(data) < period:
        return None
    return statistics.mean(data[-period:])

def get_position_side():
    positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
    for pos in positions:
        if float(pos["size"]) > 0:
            return pos["side"]  # "Buy" or "Sell"
    return None

def close_position(current_side):
    try:
        opposite = "Sell" if current_side == "Buy" else "Buy"
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if float(pos["size"]) > 0:
                session.place_order(
                    category="linear",
                    symbol=symbol,
                    side=opposite,
                    order_type="Market",
                    qty=float(pos["size"]),
                    time_in_force="GoodTillCancel",
                    reduce_only=True
                )
                print("Pozisyon kapatıldı.")
                return
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def place_order(side):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{side} emri gönderildi.")
    except Exception as e:
        print("Emir hatası:", e)

def run_bot():
    set_leverage()
    print("📡 SMA Crossover botu başlatıldı.")

    last_minute = -1
    last_signal = None

    while True:
        now = datetime.now(timezone.utc)
        minute = now.minute
        second = now.second

        if minute % interval_minutes == 0 and second == 0 and minute != last_minute:
            last_minute = minute

            price = get_live_price()
            if price is None:
                continue

            price_history.append(price)

            sma9 = calculate_sma(price_history, 9)
            sma21 = calculate_sma(price_history, 21)

            if sma9 is None or sma21 is None:
                print("SMA verileri yetersiz.")
                continue

            # Bildirim
            msg = f"[{now.strftime('%H:%M:%S')}] Fiyat: {price:.4f}\nSMA9: {sma9:.4f} | SMA21: {sma21:.4f}"
            print(msg)
            send_telegram_message(msg)

            # İşlem sinyali (önceki veriye göre)
            if last_signal is not None:
                current_position = get_position_side()
                if last_signal == "Buy":
                    if current_position == "Sell":
                        close_position(current_position)
                    place_order("Buy")
                elif last_signal == "Sell":
                    if current_position == "Buy":
                        close_position(current_position)
                    place_order("Sell")

            # Yeni sinyal güncelle
            if sma9 > sma21:
                last_signal = "Buy"
            elif sma9 < sma21:
                last_signal = "Sell"

        time.sleep(1)

if __name__ == "__main__":
    run_bot()