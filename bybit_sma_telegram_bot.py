import time
import requests
from datetime import datetime, timezone
from pybit.unified_trading import HTTP
import pandas as pd

# API ve Telegram bilgileri (Render ortamında env olarak eklenmeli)
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

symbol = "SUIUSDT"
binance_symbol = "suiusdt"
qty = 1000
leverage = 50

bybit = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        )
    except Exception as e:
        print("Telegram hatası:", e)

def calculate_sma(series, period):
    return series.rolling(window=period).mean()

def get_binance_data():
    url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol.upper()}&interval=1m&limit=30"
    response = requests.get(url)
    df = pd.DataFrame(response.json(), columns=[
        "timestamp", "open", "high", "low", "close", "volume", "close_time",
        "quote_asset_volume", "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    return df

def get_position():
    try:
        pos = bybit.get_positions(category="linear", symbol=symbol)["result"]["list"][0]
        size = float(pos["size"])
        side = pos["side"]
        return size, side
    except Exception:
        return 0, None

def close_position(side):
    opposite = "Sell" if side == "Buy" else "Buy"
    try:
        bybit.place_order(category="linear", symbol=symbol, side=opposite, order_type="Market", qty=qty, time_in_force="GoodTillCancel")
        print("Pozisyon kapatıldı.")
    except Exception as e:
        print("Pozisyon kapatma hatası:", e)

def place_order(signal):
    try:
        bybit.place_order(category="linear", symbol=symbol, side=signal, order_type="Market", qty=qty, time_in_force="GoodTillCancel")
        send_telegram(f"İşlem açıldı: {signal}")
    except Exception as e:
        print("İşlem gönderilemedi:", e)

def run_bot():
    print("📡 1 dakikalık SMA (Binance verili) bot çalışıyor")
    send_telegram("🚀 Bot başlatıldı (SMA9/SMA21, Binance verisi)")
    last_signal = None

    while True:
        now = datetime.now(timezone.utc)
        if now.second == 0:
            try:
                df = get_binance_data()
                df["sma9"] = calculate_sma(df["close"], 9)
                df["sma21"] = calculate_sma(df["close"], 21)

                sma9 = df["sma9"].iloc[-2]
                sma21 = df["sma21"].iloc[-2]

                send_telegram(f"[{now.strftime('%H:%M:%S')}] SMA9: {sma9:.4f}, SMA21: {sma21:.4f}")

                if pd.isna(sma9) or pd.isna(sma21):
                    continue

                signal = "Buy" if sma9 > sma21 else "Sell" if sma9 < sma21 else None

                if signal and signal != last_signal:
                    size, current_side = get_position()
                    if size > 0 and current_side != signal:
                        close_position(current_side)
                        time.sleep(1)
                        place_order(signal)
                    elif size == 0:
                        place_order(signal)
                    last_signal = signal

            except Exception as e:
                print("Bot hatası:", e)

            time.sleep(60)
        time.sleep(0.5)

if __name__ == "__main__":
    run_bot()