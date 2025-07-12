import requests
import time
import pandas as pd
from datetime import datetime, timezone
from pybit.unified_trading import HTTP
import os

# Ortam değişkenleri
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Bybit API oturumu
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

symbol = "SUIUSDT"
qty = 1000
leverage = 50

binance_symbol = "suiusdt"
binance_interval = "1m"
sma_periods = [7, 9, 21, 50]

prev_signal = None
last_trade_minute = None

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print("Telegram mesajı gönderilemedi:", response.text)
    except Exception as e:
        print("Telegram bağlantı hatası:", e)

def fetch_binance_ohlcv():
    url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol.upper()}&interval={binance_interval}&limit=60"
    response = requests.get(url)
    data = response.json()
    closes = [float(candle[4]) for candle in data]
    return closes

def calculate_smas(closes):
    df = pd.DataFrame({"close": closes})
    for p in sma_periods:
        df[f"sma{p}"] = df["close"].rolling(window=p).mean()
    return df.iloc[-2]  # Son kapanıştan bir önceki bar

def get_position():
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for p in positions:
            side = p["side"]
            size = float(p["size"])
            if size > 0:
                return side, size
        return None, 0
    except Exception as e:
        print("Pozisyon sorgulama hatası:", e)
        return None, 0

def close_position(current_side):
    opposite = "Sell" if current_side == "Buy" else "Buy"
    _, size = get_position()
    if size > 0:
        try:
            session.place_order(
                category="linear",
                symbol=symbol,
                side=opposite,
                order_type="Market",
                qty=size,
                time_in_force="GoodTillCancel",
                reduce_only=True
            )
            print(f"Pozisyon kapatıldı: {size} {opposite}")
        except Exception as e:
            print("Pozisyon kapatılamadı:", e)

def place_order(signal):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Buy" if signal == "LONG" else "Sell",
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel"
        )
        print(f"{signal} pozisyonu açıldı.")
    except Exception as e:
        print("Emir açma hatası:", e)

def run_bot():
    global prev_signal, last_trade_minute

    try:
        session.set_leverage(category="linear", symbol=symbol, buy_leverage=leverage, sell_leverage=leverage)
        print(f"Kaldıraç {leverage}x ayarlandı.")
    except Exception as e:
        print("Kaldıraç ayarlanamadı:", e)

    print("📡 SMA Sinyal Botu başladı (Binance verisiyle, Bybit işlemiyle)")

    while True:
        now = datetime.now(timezone.utc)
        minute = now.minute

        try:
            closes = fetch_binance_ohlcv()
            sma_data = calculate_smas(closes)

            sma7 = sma_data["sma7"]
            sma9 = sma_data["sma9"]
            sma21 = sma_data["sma21"]
            sma50 = sma_data["sma50"]

            signal = None
            if sma7 > sma9 > sma21 > sma50:
                signal = "LONG"
            elif sma50 > sma21 > sma9 > sma7:
                signal = "SHORT"

            log_msg = (
                f"[{now.strftime('%H:%M:%S')}] SMA7: {sma7:.4f}, SMA9: {sma9:.4f}, "
                f"SMA21: {sma21:.4f}, SMA50: {sma50:.4f}\nSinyal: {signal or 'YOK'}"
            )
            print(log_msg)
            send_telegram_message(log_msg)

            if signal and signal != prev_signal:
                print("→ Sinyal değişti, işlem hazırlanıyor...")
                prev_signal = signal
                last_trade_minute = (minute + 1) % 60  # Sonraki dakika başında işlem

            elif signal == prev_signal and minute == last_trade_minute and now.second == 0:
                print(f"→ Sinyal aktif: {signal}, işlem başlatılıyor...")
                current_side, _ = get_position()

                if current_side:
                    if (signal == "LONG" and current_side == "Sell") or (signal == "SHORT" and current_side == "Buy"):
                        close_position(current_side)
                        time.sleep(2)

                if current_side != ("Buy" if signal == "LONG" else "Sell"):
                    place_order(signal)
                    last_trade_minute = None  # İşlem açıldı, sıfırla

        except Exception as e:
            print("HATA:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()