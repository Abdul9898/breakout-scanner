import time, threading, requests
from flask import Flask
import os

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.getenv("CHAT_ID", "PUT_YOUR_CHAT_ID_HERE")

sent_signals = {}
THRESHOLD = 0.002  # 0.2% - catches more breakouts - AUTO PERMANENT
CACHE_COOLDOWN = 0.005  # 0.5% change needed to resend same coin

def send_telegram(symbol, price, change, signal_type, breakout_level):
    emoji = "🚀" if signal_type == "bullish" else "🔻"
    text = f"{emoji} *{signal_type.upper()}* {emoji}\n\nCoin: *{symbol}*\nPrice: `${price}`\n24h: {change}%\nBreakout Level: `${breakout_level}`\n\nTime: 4H breakout"
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
        print(f"✅ Sent alert for {symbol} - {signal_type}")
    except Exception as e:
        print(f"Telegram error: {e}")

def check_breakout(coin):
    symbol = coin['symbol']
    try:
        r = requests.get(f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=4h&limit=20", timeout=10)
        if r.status_code != 200: 
            return None
        klines = r.json()
        if len(klines) < 5: 
            return None
        prices = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        current_price = prices[-1]
        max_prev_high = max(highs[-4:-1])
        min_prev_low = min(lows[-4:-1])
        signal_type = None
        breakout_level = 0
        if current_price > max_prev_high * (1 + THRESHOLD):
            signal_type = 'bullish'
            breakout_level = max_prev_high
        elif current_price < min_prev_low * (1 - THRESHOLD):
            signal_type = 'bearish'
            breakout_level = min_prev_low
        if signal_type:
            last_price = sent_signals.get(symbol, 0)
            # Only send if new coin or moved 0.5%
            if symbol not in sent_signals or abs(current_price - last_price) / current_price > CACHE_COOLDOWN:
                sent_signals[symbol] = current_price  # SAVE TO CACHE - prevents spam
                return {'symbol': symbol, 'price': coin['lastPrice'], 'change': coin['priceChangePercent'], 'type': signal_type, 'level': breakout_level}
    except Exception as e:
        print(f"check error {symbol}: {e}")
        return None
    return None

def scanner_loop():
    print("🚀 Scanner started 24/7 - AUTO PERMANENT ON...")
    while True:
        try:
            print("Scanning Top 200...")
            res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=15).json()
            top = sorted([t for t in res if t['symbol'].endswith('USDT')], key=lambda x: float(x['quoteVolume']), reverse=True)[:200]
            for i in range(0, 200, 10):
                batch = top[i:i+10]
                for coin in batch:
                    sig = check_breakout(coin)
                    if sig:
                        send_telegram(sig['symbol'], sig['price'], sig['change'], sig['type'], sig['level'])
                    time.sleep(0.3)
            print(f"Scan done. Sleeping 90s. Cache: {len(sent_signals)} coins tracked")
            time.sleep(90)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(30)

# AUTO START PERMANENTLY - no button needed
threading.Thread(target=scanner_loop, daemon=True).start()

@app.route('/')
def home():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return f"""
        <h2>🚀 Scanner Running 24/7 - AUTO ON</h2>
        <p>Threshold: {THRESHOLD*100}%</p>
        <p>Cache: {len(sent_signals)} coins</p>
        <p>Bot: {BOT_TOKEN[:10]}...</p>
        <p>Status: Scanning Top 200 every 90s</p>
        """

@app.route('/health')
def health():
    return "OK - Scanner running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
