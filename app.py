import time, threading, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.getenv("CHAT_ID", "PUT_YOUR_CHAT_ID_HERE")

sent_signals = {}
THRESHOLD = 0.002
CACHE_COOLDOWN = 0.005

def send_telegram(symbol, price, change, signal_type, breakout_level):
    try:
        emoji = "🚀" if signal_type == "bullish" else "🔻"
        # Simple text without Markdown to avoid errors
        text = f"{emoji} {signal_type.upper()} {emoji}\n\nCoin: {symbol}\nPrice: ${price}\n24h: {change}%\nLevel: ${breakout_level}\nTime: 4H breakout\nAuto Permanent ON"
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        # Try without Markdown first
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        print(f"Telegram response: {r.status_code} - {r.text[:200]}")
        if r.status_code == 200:
            print(f"✅ Sent alert for {symbol} - {signal_type}")
            return True
        else:
            print(f"❌ Telegram failed: {r.text}")
            return False
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def check_breakout(coin):
    symbol = coin['symbol']
    try:
        # Try multiple endpoints
        for base_url in ["https://fapi.binance.com", "https://api.binance.com"]:
            try:
                r = requests.get(f"{base_url}/fapi/v1/klines?symbol={symbol}&interval=4h&limit=20", timeout=10)
                if r.status_code == 200:
                    break
            except:
                continue
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
            if symbol not in sent_signals or abs(current_price - last_price) / current_price > CACHE_COOLDOWN:
                sent_signals[symbol] = current_price
                return {'symbol': symbol, 'price': coin['lastPrice'], 'change': coin['priceChangePercent'], 'type': signal_type, 'level': breakout_level}
    except Exception as e:
        print(f"check error {symbol}: {e}")
        return None
    return None

def scanner_loop():
    print("🚀 Scanner started 24/7 - AUTO PERMANENT ON...")
    # Send startup message to Telegram to prove it works
    try:
        send_telegram("TEST", "0.00", "0", "bullish", "0")
        print("Startup telegram sent")
    except Exception as e:
        print(f"Startup telegram failed: {e}")
    
    while True:
        try:
            print("Scanning Top 200...")
            res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=15).json()
            top = sorted([t for t in res if t['symbol'].endswith('USDT')], key=lambda x: float(x['quoteVolume']), reverse=True)[:200]
            found = 0
            for i in range(0, 200, 10):
                batch = top[i:i+10]
                for coin in batch:
                    sig = check_breakout(coin)
                    if sig:
                        print(f"🔥 BREAKOUT FOUND: {sig['symbol']} {sig['type']}")
                        send_telegram(sig['symbol'], sig['price'], sig['change'], sig['type'], sig['level'])
                        found += 1
                    time.sleep(0.2)
            print(f"Scan done. Found {found} signals. Sleeping 90s. Cache: {len(sent_signals)} coins")
            time.sleep(90)
        except Exception as e:
            print(f"Loop error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(30)

threading.Thread(target=scanner_loop, daemon=True).start()

@app.route('/')
def home():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Scanner Running - Error loading index: {e} - Cache: {len(sent_signals)}"

@app.route('/api/alert', methods=['POST', 'GET'])
def api_alert():
    """Frontend calls this to send Telegram - This connects website signals to Telegram!"""
    try:
        data = request.get_json() if request.is_json else request.args
        if not data:
            data = {}
        symbol = data.get('symbol', 'UNKNOWN')
        price = data.get('price', '0')
        change = data.get('change', '0')
        sig_type = data.get('type', 'bullish')
        level = data.get('level', price)
        
        # Prevent spam - same logic as backend
        try:
            curr_price = float(str(price).replace('$',''))
            last_price = sent_signals.get(symbol, 0)
            if symbol in sent_signals and abs(curr_price - last_price) / max(curr_price,1) < CACHE_COOLDOWN:
                print(f"Skipping duplicate {symbol}")
                return jsonify({"status": "skipped", "reason": "duplicate"})
            sent_signals[symbol] = curr_price
        except:
            sent_signals[symbol] = price

        success = send_telegram(symbol, price, change, sig_type, level)
        if success:
            return jsonify({"status": "sent", "symbol": symbol})
        else:
            return jsonify({"status": "failed"}), 500
    except Exception as e:
        print(f"/api/alert error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "OK", "auto": "permanent ON", "cache": len(sent_signals), "threshold": THRESHOLD})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
