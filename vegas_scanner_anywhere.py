import os
import sys
import requests
import yfinance as yf
import pandas as pd

# Securely grab the URL from the system environment variables
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

# Configuration
WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "AMD"]        
EMA_G1 = (36, 43)
EMA_G2 = (144, 169)
EMA_G3 = (576, 676)

def send_discord_alert(message):
    if not DISCORD_WEBHOOK_URL:
        print("❌ Error: DISCORD_WEBHOOK environment variable is missing!")
        return
    payload = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code == 204:
            print("📱 Alert sent successfully!")
        else:
            print(f"❌ Discord error code: {response.status_code}")
    except Exception as e:
        print(f"Network error: {e}")

def check_stock_tunnel(ticker, timeframe):
    """
    Calculates Vegas Tunnels for a single stock based on timeframe.
    timeframe: '1h' (Hourly Short-Term) or '1d' (Daily Long-Term)
    """
    stock = yf.Ticker(ticker)
    
    # Request data based on timeframe
    if timeframe == '1h':
        # 2 years of hourly data is plenty to calculate up to 676 EMA
        df = stock.history(interval="1h", period="2y")
        tf_label = "1-Hour (Short-Term)"
    else:
        # 5 years for daily candles
        df = stock.history(interval="1d", period="5y")
        tf_label = "Daily (Long-Term)"
        
    if len(df) < max(EMA_G3):
        print(f"❌ Not enough historical data for {ticker} on {timeframe}")
        return

    # Calculate EMAs
    df['EMA36'] = df['Close'].ewm(span=EMA_G1[0], adjust=False).mean()
    df['EMA43'] = df['Close'].ewm(span=EMA_G1[1], adjust=False).mean()
    df['EMA144'] = df['Close'].ewm(span=EMA_G2[0], adjust=False).mean()
    df['EMA169'] = df['Close'].ewm(span=EMA_G2[1], adjust=False).mean()
    df['EMA576'] = df['Close'].ewm(span=EMA_G3[0], adjust=False).mean()
    df['EMA676'] = df['Close'].ewm(span=EMA_G3[1], adjust=False).mean()

    df['G1_Top'] = df[['EMA36', 'EMA43']].max(axis=1)
    df['G1_Bot'] = df[['EMA36', 'EMA43']].min(axis=1)
    df['G2_Top'] = df[['EMA144', 'EMA169']].max(axis=1)
    df['G2_Bot'] = df[['EMA144', 'EMA169']].min(axis=1)
    df['G3_Top'] = df[['EMA576', 'EMA676']].max(axis=1)
    
    # Check the structural relationship of the latest fully closed candle vs the previous one
    today_candle = df.iloc[-2]
    prev_candle = df.iloc[-3]
    
    def get_regime(candle):
        close = candle['Close']
        if close < candle['G3_Top']: return "BEAR_G3"
        if close > candle['G1_Top'] and close > candle['G2_Top']: return "BULL"
        if close < candle['G1_Bot'] and close > candle['G2_Top']: return "PULLBACK"
        if candle['G2_Bot'] <= close <= candle['G2_Top']: return "CHOPPY"
        if close < candle['G2_Bot']: return "BEAR_G2"
        return None

    current_regime = get_regime(today_candle)
    past_regime = get_regime(prev_candle)
    close_price = today_candle['Close']

    # ONLY fire if the structural trend state shifted on this timeframe
    if current_regime != past_regime:
        base_msg = f"⏱️ **[{tf_label}]** **{ticker}** crossed lines at **${close_price:.2f}**:\n"
        
        if current_regime == "BEAR_G3":
            send_discord_alert(base_msg + f"⚠️ Suppressed under macro 576/676 tunnel floor. Macro danger.")
        elif current_regime == "BULL":
            send_discord_alert(base_msg + f"🟩 Bullish breakout! Riding above 36/43 and 144/169 tunnels.")
        elif current_regime == "PULLBACK":
            send_discord_alert(base_msg + f"🔵 Healthy Pullback. Holding support above the 144/169 boundary.")
        elif current_regime == "CHOPPY":
            send_discord_alert(base_msg + f"🟡 Caution. Price entered the 144/169 no-man's-land.")
        elif current_regime == "BEAR_G2":
            send_discord_alert(base_msg + f"🟥 Trend Reversal! Closed completely below the 169 EMA floor.")

if __name__ == "__main__":
    # Read the timeframe parameter passed by the system (Default to daily if empty)
    target_timeframe = sys.argv[1] if len(sys.argv) > 1 else '1d'
    
    print(f"🚀 Starting scanning cycle for timeframe: {target_timeframe}")
    for ticker in WATCHLIST:
        try:
            check_stock_tunnel(ticker, target_timeframe)
        except Exception as e:
            print(f"Error executing scanner for {ticker}: {e}")
