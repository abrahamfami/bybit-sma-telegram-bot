import time
import json
import requests
import pandas as pd
from pybit.unified_trading import HTTP
import os
from datetime import datetime, timezone

# === API ve Telegram ===
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# === Parite Listesi ===
PAIRS = [
    {"symbol": "VINEUSDT", "bybit_symbol": "VINEUSDT", "qty": 2000},
    {"symbol": "SWARMSUSDT", "bybit_symbol": "SWARMSUSDT", "qty": 10000},
    {"symbol": "CHILLGUYUSDT", "bybit_symbol": "CHILLGUYUSDT", "qty": 4000},
    {"symbol": "GRIFFAINUSDT", "bybit_symbol": "GRIFFAINUSDT", "qty": 8000},
    {"symbol": "ZEREBROUSDT", "bybit_symbol": "ZEREBROUSDT", "qty": 7500}
]

TP_PERCENT = 0.03
SL_PERCENT = 0.05
CACHE_FILE = "ema_cache.json"

def send_telegram(text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": f"🕒 {now}\n{text}"})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

def fetch_binance_ohlcv(symbol, interval="5m", limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list): return None
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "_", "_", "_", "_", "_", "_"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except:
        return None

def calculate_ema(df, period):
    return df["close"].ewm(span=period).mean().iloc[-1]

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def get_position(symbol):
    try:
        positions = session.get_positions(category="linear", symbol=symbol)["result"]["list"]
        for pos in positions:
            if pos["size"] != "0":
                return pos
    except:
        return None
    return None

def close_position(symbol, side, qty):
    try:
        session.place_order(
            category="linear",
            symbol=symbol,
            side="Sell" if side == "Buy" else "Buy",
            order_type="Market",
            qty=qty,
            reduce_only=True
        )
        time.sleep(1)
        session.cancel_all_orders(category="linear", symbol=symbol)
        send_telegram(f"🔴 {symbol} pozisyon kapatıldı ({side})")
    except Exception as e:
        send_telegram(f"⚠️ {symbol} pozisyon kapama hatası: {e}")

def open_position(symbol, side, qty, entry_price):
    try:
        if side == "Buy":
            tp = round(entry_price * (1 + TP_PERCENT), 5)
            sl = round(entry_price * (1 - SL_PERCENT), 5)
        else:
            tp = round(entry_price * (1 - TP_PERCENT), 5)
            sl = round(entry_price * (1 + SL_PERCENT), 5)

        session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            take_profit=str(tp),
            stop_loss=str(sl),
            time_in_force="GTC",
            position_idx=0
        )

        send_telegram(f"🟢 {symbol} pozisyon açıldı: {side} @ {entry_price:.5f}\n🎯 TP: {tp} | 🛑 SL: {sl}")
    except Exception as e:
        send_telegram(f"⛔️ {symbol} işlem açma hatası: {e}")

def process_pair(pair, cache):
    symbol = pair["symbol"]
    bybit_symbol = pair["bybit_symbol"]
    qty = pair["qty"]

    df = fetch_binance_ohlcv(symbol)
    if df is None or df.shape[0] < 2:
        send_telegram(f"⚠️ {symbol} için veri alınamadı.")
        return

    ema9_now = calculate_ema(df, 9)
    ema21_now = calculate_ema(df, 21)
    price = df.iloc[-1]["close"]

    prev_ema9 = cache.get(symbol, {}).get("EMA9")
    prev_ema21 = cache.get(symbol, {}).get("EMA21")

    signal = None
    if prev_ema9 is not None and prev_ema21 is not None:
        if prev_ema9 <= prev_ema21 and ema9_now > ema21_now:
            signal = "long"
        elif prev_ema9 >= prev_ema21 and ema9_now < ema21_now:
            signal = "short"

    # Log için güvenli string'ler
    prev_ema9_str = f"{prev_ema9:.5f}" if prev_ema9 is not None else "---"
    prev_ema21_str = f"{prev_ema21:.5f}" if prev_ema21 is not None else "---"

    send_telegram(f"""📊 {symbol} Sinyal Kontrolü:
🔁 Önceki EMA9: {prev_ema9_str} | EMA21: {prev_ema21_str}
✅ Şimdi EMA9: {ema9_now:.5f} | EMA21: {ema21_now:.5f}
💰 Fiyat: {price:.5f}
📌 Sinyal: {signal.upper() if signal else 'YOK'}""")

    # Her durumda güncel EMA'ları kaydet
    cache[symbol] = {
        "EMA9": ema9_now,
        "EMA21": ema21_now
    }

    if not signal:
        return

    current_pos = get_position(bybit_symbol)
    current_side = None
    if current_pos:
        current_side = "long" if current_pos["side"] == "Buy" else "short"

    if not current_pos or current_side != signal:
        if current_pos:
            close_position(bybit_symbol, current_pos["side"], qty)
            time.sleep(2)
        open_position(bybit_symbol, "Buy" if signal == "long" else "Sell", qty, price)
    else:
        send_telegram(f"⏸ {symbol} pozisyon zaten açık ({signal.upper()})")

# === Ana Döngü ===
while True:
    try:
        now = datetime.now(timezone.utc)
        if now.minute % 5 == 0 and now.second < 10:
            cache = load_cache()
            for pair in PAIRS:
                process_pair(pair, cache)
            save_cache(cache)
            time.sleep(60)
        else:
            time.sleep(5)
    except Exception as e:
        send_telegram(f"🚨 Genel Hata: {e}")
        time.sleep(60)