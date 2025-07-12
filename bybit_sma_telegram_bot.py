import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import os
from pybit.unified_trading import HTTP
from binance.client import Client as BinanceClient

# ENV değişkenleri
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")

# Sabitler
symbol = "SUIUSDT"
binance_symbol = "SUIUSDT"
qty = 1000
interval = "1m"

# Oturumlar
bybit = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
binance = BinanceClient(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)

last_signal = None
last_trade_minute = None

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        r = requests.post(url, data=data)
        if r.status_code != 200:
            print("Telegram gönderim hatası:", r.text)
        else:
            print("Telegram gönderildi.")
    except Exception as e:
        print("Telegram hatası:", e)

def fetch_binance_data():
    candles = binance.get_klines(symbol=binance_symbol, interval=interval, limit=50)
    df = pd.DataFrame(candles, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    df["sma7"] = df["close"].rolling(7).mean()
    df["sma9"] = df["close"].rolling(9).mean()
    df["sma21"] = df["close"].rolling(21).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    return df

def get_position_side():
    try:
        pos = bybit.get_positions(category="linear", symbol=symbol)["result"]["list"][0]
        side = pos["side"]
        size = float(pos["size"])
        return side if size > 0 else None
    except Exception as e:
        print("Pozisyon kontrol hatası:", e)
        return None

def close_position(current_side):
    try:
        opposite = "Sell" if current_side == "Buy" else "Buy"
        bybit.place_order(category="linear", symbol=symbol, side=opposite, order_type="Market", qty=qty, time_in_force="GoodTillCancel", reduce_only=True)
        print("Pozisyon kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def open_position(side):
    try:
        bybit.place_order(category="linear", symbol=symbol, side=side, order_type="Market", qty=qty, time_in_force="GoodTillCancel")
        print(f"{side} işlemi açıldı.")
    except Exception as e:
        print("İşlem açma hatası:", e)

def run_bot():
    global last_signal, last_trade_minute
    print("✅ Bot çalışıyor (Binance SMA tabanlı, Bybit işlem)")
    send_telegram("✅ Bot başlatıldı.")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            minute_now = now.replace(second=0, microsecond=0)

            df = fetch_binance_data()
            last = df.iloc[-2]  # Önceki kapanış mumu
            sma7, sma9, sma21, sma50 = last["sma7"], last["sma9"], last["sma21"], last["sma50"]

            message = f"[{now.strftime('%H:%M:%S')}] SMA7: {sma7:.4f} | SMA9: {sma9:.4f} | SMA21: {sma21:.4f} | SMA50: {sma50:.4f}"
            print(message)
            send_telegram(message)

            if pd.isna(sma7) or pd.isna(sma9) or pd.isna(sma21) or pd.isna(sma50):
                time.sleep(60)
                continue

            # Sinyal belirleme
            if sma7 > sma9 > sma21 > sma50:
                current_signal = "LONG"
            elif sma50 > sma21 > sma9 > sma7:
                current_signal = "SHORT"
            else:
                current_signal = None

            # Sinyal değişmişse ve trade zamanıysa
            if current_signal != last_signal and now.second == 0:
                position = get_position_side()
                print(f"Aktif pozisyon: {position}, Yeni sinyal: {current_signal}")

                if current_signal == "LONG":
                    if position == "Sell":
                        close_position("Sell")
                        open_position("Buy")
                    elif position is None:
                        open_position("Buy")

                elif current_signal == "SHORT":
                    if position == "Buy":
                        close_position("Buy")
                        open_position("Sell")
                    elif position is None:
                        open_position("Sell")

                last_signal = current_signal
                last_trade_minute = minute_now

            time.sleep(1)
        except Exception as e:
            print("Genel bot hatası:", e)
            time.sleep(5)

if __name__ == "__main__":
    run_bot()