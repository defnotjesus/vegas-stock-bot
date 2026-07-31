import requests
import yfinance as yf
import pandas as pd

# =====================================================================
# CONFIGURATION
# =====================================================================
WATCHLIST = ["AAPL", "TSLA", "NVDA", "MSFT", "AMD"]        
INTERVAL = "1d"

EMA_G1 = (36, 43)
EMA_G2 = (144, 169)
EMA_G3 = (576, 676)

DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE"

def send_discord_alert(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Error: {e}")

def check_stock_tunnel(ticker):
    stock = yf.Ticker(ticker)
    df = stock.history(interval=INTERVAL, period="5y")
    
    if len(df) < max(EMA_G3):
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
    
    # Check yesterday's closed candle vs the day before to see if it JUST crossed over
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

    # ONLY send a notification if the market state actually changed yesterday
    if current_regime != past_regime:
        if current_regime == "BEAR_G3":
            send_discord_alert(f"⚠️ **[{ticker}]** Closed at **${close_price:.2f}**, suppressed under macro 576/676 tunnel.")
        elif current_regime == "BULL":
            send_discord_alert(f"🟩 **[{ticker}]** Bullish breakout! Riding safely above 36/43 and 144/169 tunnels at **${close_price:.2f}**.")
        elif current_regime == "PULLBACK":
            send_discord_alert(f"🔵 **[{ticker}]** Healthy Pullback. Holding support above 144/169 tunnel at **${close_price:.2f}**.")
        elif current_regime == "CHOPPY":
            send_discord_alert(f"🟡 **[{ticker}]** Caution. Price entered the 144/169 no-man's-land at **${close_price:.2f}**.")
        elif current_regime == "BEAR_G2":
            send_discord_alert(f"🟥 **[{ticker}]** Trend Reversal! Price closed below the 169 EMA floor at **${close_price:.2f}**.")

# Run once per execution
if __name__ == "__main__":
    for ticker in WATCHLIST:
        try:
            check_stock_tunnel(ticker)
        except Exception as e:
            print(f"Error on {ticker}: {e}")