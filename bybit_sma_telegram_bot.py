import requests
import pandas as pd
import time
from datetime import datetime, timezone
import os
from pybit.unified_trading import HTTP
from binance.client import Client

# API Key'leri
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Ayarlar
symbol = "SUIUSDT"
qty = 1000
interval = "1m"

# Oturumlar
bybit = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
binance = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)

last_signal = None

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("Telegram mesaj hatası:", response.text)
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_data():
    klines = binance.get_klines(symbol=symbol, interval=interval, limit=50)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['sma7'] = df['close'].rolling(window=7).mean()
    df['sma9'] = df['close'].rolling(window=9).mean()
    df['sma21'] = df['close'].rolling(window=21).mean()
    df['sma50'] = df['close'].rolling(window=50).mean()
    return df

def get_current_position():
    try:
        pos = bybit.get_positions(category="linear", symbol=symbol)["result"]["list"]
        if pos and float(pos[0]["size"]) > 0:
            return pos[0]["side"]  # "Buy" ya da "Sell"
        return None
    except Exception as e:
        print("Pozisyon sorgu hatası:", e)
        return None

def close_position():
    try:
        bybit.place_order(
            category="linear",
            symbol=symbol,
            side="Sell",
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
        bybit.place_order(
            category="linear",
            symbol=symbol,
            side="Buy",
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=True
        )
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def place_order(side):
    try:
        bybit.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{side} emri verildi.")
        send_telegram(f"📊 Yeni İşlem: {side}\nMiktar: {qty} SUI")
    except Exception as e:
        print("Emir gönderim hatası:", e)

def run_bot():
    global last_signal
    print("✅ Bot başlatıldı")
    while True:
        now = datetime.now(timezone.utc)
        if now.second == 0:
            try:
                df = fetch_binance_data()
                row = df.iloc[-2]  # bir önceki kapanış

                sma7 = row['sma7']
                sma9 = row['sma9']
                sma21 = row['sma21']
                sma50 = row['sma50']

                signal = None
                if sma7 > sma9 > sma21 > sma50:
                    signal = "Buy"
                elif sma7 < sma9 < sma21 < sma50:
                    signal = "Sell"

                # Telegram log
                msg = f"🕒 {now.strftime('%H:%M')} SMA Değerleri:\nSMA7: {sma7:.4f}\nSMA9: {sma9:.4f}\nSMA21: {sma21:.4f}\nSMA50: {sma50:.4f}"
                send_telegram(msg)

                # Sadece crossover'da işlem aç
                if signal and signal != last_signal:
                    last_signal = signal
                    current = get_current_position()

                    if current and ((current == "Buy" and signal == "Sell") or (current == "Sell" and signal == "Buy")):
                        print("Pozisyon ters, kapatılıyor.")
                        close_position()

                    if not current or current != signal:
                        place_order(signal)

            except Exception as e:
                print("Genel hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()