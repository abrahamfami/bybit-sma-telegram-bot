
from pybit.unified_trading import HTTP
import pandas as pd
import time
from datetime import datetime, timezone
import os
import requests

api_key = os.environ.get("BYBIT_API_KEY")
api_secret = os.environ.get("BYBIT_API_SECRET")
telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

symbol = "SUIUSDT"
qty = 10
leverage = 50
interval = "5"

pozisyon = None

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    data = {"chat_id": telegram_chat_id, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram mesajı gönderilemedi:", e)

def set_leverage():
    try:
        session.set_leverage(category="linear", symbol=symbol, buy_leverage=leverage, sell_leverage=leverage)
    except Exception as e:
        print("Kaldıraç ayarlanamadı:", e)

def get_sma_values():
    candles = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=30)["result"]["list"]
    df = pd.DataFrame(candles)
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    df['close'] = df['close'].astype(float)
    sma9 = df['close'].rolling(window=9).mean().iloc[-2]
    sma21 = df['close'].rolling(window=21).mean().iloc[-2]
    return sma9, sma21

def place_order(side):
    try:
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        send_telegram_message(f"{side} emri gönderildi: {response}")
    except Exception as e:
        send_telegram_message("Emir gönderilemedi: " + str(e))

def pozisyonu_kapat():
    try:
        position_info = session.get_positions(category="linear", symbol=symbol)["result"]["list"][0]
        pozisyon_miktar = float(position_info["size"])
        pozisyon_tipi = position_info["side"]
        if pozisyon_miktar > 0:
            ters_yon = "Sell" if pozisyon_tipi == "Buy" else "Buy"
            response = session.place_order(
                category="linear",
                symbol=symbol,
                side=ters_yon,
                order_type="Market",
                qty=pozisyon_miktar,
                time_in_force="GoodTillCancel"
            )
            send_telegram_message(f"Pozisyon kapatıldı: {ters_yon} {pozisyon_miktar}")
    except Exception as e:
        send_telegram_message("Pozisyon kapatılamadı: " + str(e))

def run_bot():
    global pozisyon
    set_leverage()
    send_telegram_message("📡 SMA Crossover botu başlatıldı.")
    while True:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.second == 0:
            try:
                sma9, sma21 = get_sma_values()
                send_telegram_message(f"[{now.strftime('%H:%M:%S')}] SMA9: {sma9:.4f}, SMA21: {sma21:.4f}")
                if sma9 < sma21 and pozisyon != "LONG":
                    pozisyonu_kapat()
                    place_order("Buy")
                    pozisyon = "LONG"
                elif sma9 > sma21 and pozisyon != "SHORT":
                    pozisyonu_kapat()
                    place_order("Sell")
                    pozisyon = "SHORT"
                time.sleep(5)
            except Exception as e:
                send_telegram_message("Genel HATA: " + str(e))
        time.sleep(0.5)

if __name__ == "__main__":
    run_bot()
