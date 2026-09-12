import time, threading, requests
from flask import Flask, request, jsonify
import os
app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
sent_signals = {}
THRESHOLD = 0.001 # 0.1% - catches more like UAI, COPPER
CACHE_COOLDOWN = 0.002

def send_telegram(symbol, price, change, signal_type, breakout_level):
    try:
        emoji = "🚀" if signal_type == "bullish" else "🔻"
        text = f"{emoji} {signal_type.upper()} {emoji}\nCoin: {symbol}\nPrice: ${price}\n24h: {change}%\nLevel: ${breakout_level}\n4H Breakout"
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        print(f"Sent {symbol} {sig_type} - {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def check_breakout(coin):
    symbol = coin['symbol']
    try:
        r = requests.get(f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=4h&limit=20", timeout=10)
        if r.status_code!= 200: return None
        klines = r.json()
        if len(klines) < 5: return None
        prices = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        current = prices[-1]
        max_high = max(highs[-4:-1])
        min_low = min(lows[-4:-1])
        sig_type = None
        level = 0
        if current > max_high * (1 + THRESHOLD):
            sig_type = 'bullish'; level = max_high
        elif current < min_low * (1 - THRESHOLD):
            sig_type = 'bearish'; level = min_low
        if sig_type:
            last = sent_signals.get(symbol, 0)
            if symbol not in sent_signals or abs(current - last) / current > CACHE_COOLDOWN:
                sent_signals[symbol] = current
                return {'symbol': symbol, 'price': coin['lastPrice'], 'change': coin['priceChangePercent'], 'type': sig_type, 'level': level}
    except: return None
    return None

def scanner_loop():
    print("🚀 Scanner 24/7 Permanent ON - Bulk FAPI")
    while True:
        try:
            print("Scanning Top 200 - ONE call...")
            res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=15).json()
            top = sorted([t for t in res if t['symbol'].endswith('USDT')], key=lambda x: float(x['quoteVolume']), reverse=True)[:200]
            found = 0
            for i in range(0, 200, 10):
                for coin in top[i:i+10]:
                    sig = check_breakout(coin)
                    if sig:
                        print(f"BREAKOUT {sig['symbol']} {sig['type']}")
                        send_telegram(sig['symbol'], sig['price'], sig['change'], sig['type'], sig['level'])
                        found += 1
                time.sleep(0.2)
            print(f"Done: {found} signals")
            time.sleep(90)
        except Exception as e:
            print(f"Error {e}"); time.sleep(30)
threading.Thread(target=scanner_loop, daemon=True).start()

@app.route('/')
def home():
    try:
        with open("index.html","r",encoding="utf-8") as f: return f.read()
    except: return f"Running - {len(sent_signals)} tracked"

@app.route('/api/alert', methods=['POST'])
def api_alert():
    try:
        data = request.get_json()
        symbol = data.get('symbol'); price = data.get('price'); change = data.get('change'); sig_type = data.get('type'); level = data.get('level')
        try:
            curr = float(str(price).replace('$',''))
            last = sent_signals.get(symbol,0)
            if symbol in sent_signals and last!=0 and abs(curr-last)/max(curr,1) < CACHE_COOLDOWN:
                return jsonify({"status":"skip"})
            sent_signals[symbol]=curr
        except: pass
        ok = send_telegram(symbol, price, change, sig_type, level)
        return jsonify({"status":"sent" if ok else "fail"})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route('/health')
def health(): return jsonify({"ok":True,"auto":"ON","cache":len(sent_signals)})

if __name__ == "__main__": app.run(host="0.0.0.0", port=10000)
