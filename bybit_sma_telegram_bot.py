from pybit.unified_trading import HTTP
import requests
import pandas as pd
import time
from datetime import datetime, timezone
import os

# API Ayarları
api_key = os.environ.get("BYBIT_API_KEY")
api_secret = os.environ.get("BYBIT_API_SECRET")
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
chat_id = os.environ.get("TELEGRAM_CHAT_ID")

# Ayarlar
symbol = "SUIUSDT"
qty = 1000
leverage = 50

session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

def get_binance_sma(symbol="SUIUSDT", interval="5m", limit=30):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    df = pd.DataFrame(response.json(), columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "qav", "not", "tbbv", "tbqv", "ignore"
    ])
    df['close'] = df['close'].astype(float)
    df['sma9'] = df['close'].rolling(window=9).mean()
    df['sma21'] = df['close'].rolling(window=21).mean()
    return df

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": msg})
    except Exception as e:
        print("Telegram gönderilemedi:", e)

def get_position():
    positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
    for p in positions:
        if float(p["size"]) > 0:
            return p["side"], float(p["size"])
    return None, 0

def close_position(current_side):
    opp_side = "Sell" if current_side == "Buy" else "Buy"
    session.place_order(
        category="linear",
        symbol=symbol,
        side=opp_side,
        order_type="Market",
        qty=qty,
        time_in_force="GoodTillCancel",
        reduce_only=True
    )

def place_order(side):
    session.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        order_type="Market",
        qty=qty,
        time_in_force="GoodTillCancel"
    )
    send_telegram(f"✅ Yeni İşlem: {side.upper()} açıldı ({qty} {symbol})")

def run_bot():
    print("⏳ SMA crossover bot başladı...")
    last_signal = None
    last_action_time = None

    while True:
        now = datetime.now(timezone.utc)
        try:
            df = get_binance_sma()
            sma9 = df['sma9'].iloc[-2]
            sma21 = df['sma21'].iloc[-2]

            signal = "Buy" if sma9 > sma21 else "Sell"
            send_telegram(f"[{now.strftime('%H:%M')}] SMA9: {sma9:.4f} | SMA21: {sma21:.4f}")

            if now.minute % 5 == 0 and now.second == 0:
                if signal != last_signal:
                    current_pos, pos_size = get_position()
                    if current_pos and current_pos != signal:
                        close_position(current_pos)
                        time.sleep(1)
                        place_order(signal)
                    elif not current_pos:
                        place_order(signal)
                    last_signal = signal
                    last_action_time = now

        except Exception as e:
            print("Hata:", e)

        time.sleep(1)

if __name__ == "__main__":
    run_bot()