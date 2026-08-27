import os
import json
import requests
import yfinance as yf
import pandas as pd

# =====================================================================
# CONFIGURATION
# =====================================================================
EMA_G1 = (36, 43)
EMA_G2 = (144, 169)
EMA_G3 = (576, 676)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

def load_watchlist():
    """從 json 檔案讀取清單，若檔案不存在則回退預設值"""
    try:
        with open("watchlist.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("watchlist", ["AAPL", "NVDA"])
    except Exception as e:
        print(f"Error loading watchlist.json: {e}, using default.")
        return ["AAPL", "NVDA"]

def send_discord_alert(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Error: {e}")

def check_stock_tunnel(ticker):
    stock = yf.Ticker(ticker)
    
    # 1. 抓取日線歷史資料計算穩定的大週期 EMA 通道（基準）
    df_daily = stock.history(interval="1d", period="5y")
    if len(df_daily) < max(EMA_G3):
        print(f"[{ticker}] Not enough history data.")
        return

    # 計算日線 EMA
    df_daily['EMA36'] = df_daily['Close'].ewm(span=EMA_G1[0], adjust=False).mean()
    df_daily['EMA43'] = df_daily['Close'].ewm(span=EMA_G1[1], adjust=False).mean()
    df_daily['EMA144'] = df_daily['Close'].ewm(span=EMA_G2[0], adjust=False).mean()
    df_daily['EMA169'] = df_daily['Close'].ewm(span=EMA_G2[1], adjust=False).mean()
    df_daily['EMA576'] = df_daily['Close'].ewm(span=EMA_G3[0], adjust=False).mean()
    df_daily['EMA676'] = df_daily['Close'].ewm(span=EMA_G3[1], adjust=False).mean()

    df_daily['G1_Top'] = df_daily[['EMA36', 'EMA43']].max(axis=1)
    df_daily['G1_Bot'] = df_daily[['EMA36', 'EMA43']].min(axis=1)
    df_daily['G2_Top'] = df_daily[['EMA144', 'EMA169']].max(axis=1)
    df_daily['G2_Bot'] = df_daily[['EMA144', 'EMA169']].min(axis=1)
    df_daily['G3_Top'] = df_daily[['EMA576', 'EMA676']].max(axis=1)

    # 取得昨天收盤定案的通道基準
    last_completed_day = df_daily.iloc[-2]
    
    g1_top = last_completed_day['G1_Top']
    g1_bot = last_completed_day['G1_Bot']
    g2_top = last_completed_day['G2_Top']
    g2_bot = last_completed_day['G2_Bot']
    g3_top = last_completed_day['G3_Top']

    # 2. 取得當前即時價
    todays_data = stock.history(interval="1m", period="1d")
    if todays_data.empty:
        current_price = df_daily.iloc[-1]['Close']
    else:
        current_price = todays_data.iloc[-1]['Close']

    # 3. 判斷即時狀態
    def get_intraday_regime(price):
        if price < g3_top: return "BEAR_G3"
        if price > g1_top and price > g2_top: return "BULL"
        if price < g1_bot and price > g2_top: return "PULLBACK"
        if g2_bot <= price <= g2_top: return "CHOPPY"
        if price < g2_bot: return "BEAR_G2"
        return None

    current_regime = get_intraday_regime(current_price)
    prev_regime = get_intraday_regime(last_completed_day['Close'])

    print(f"[{ticker}] Current Price: {current_price:.2f} | Regime: {current_regime}")

    # 4. 狀態改變時，發送白話文通知
    if current_regime != prev_regime:
        if current_regime == "BULL":
            msg = (
                f"🟢 **【{ticker} 買進 / 偏多提醒】**\n"
                f"• 當前價格：**${current_price:.2f}**\n"
                f"• 狀況：價格已強勢站穩短期與中期通道之上。\n"
                f"• 💡 **建議**：多頭趨勢延續，可考慮順勢偏多操作或續抱。"
            )
            send_discord_alert(msg)
            
        elif current_regime == "PULLBACK":
            msg = (
                f"🔵 **【{ticker} 逢低回測提醒】**\n"
                f"• 當前價格：**${current_price:.2f}**\n"
                f"• 狀況：價格回測至中長期通道支撐帶（144/169上方）。\n"
                f"• 💡 **建議**：屬於健康回檔，可觀察是否在支撐區止穩，是潛在的低吸機會。"
            )
            send_discord_alert(msg)
            
        elif current_regime == "CHOPPY":
            msg = (
                f"🟡 **【{ticker} 盤整觀望提醒】**\n"
                f"• 當前價格：**${current_price:.2f}**\n"
                f"• 狀況：價格陷入 144/169 通道內部（多空交界處）。\n"
                f"• 💡 **建議**：方向不明顯，建議暫時觀望，避免多空雙巴。"
            )
            send_discord_alert(msg)
            
        elif current_regime == "BEAR_G2":
            msg = (
                f"🔴 **【{ticker} 賣出 / 停損警報】**\n"
                f"• 當前價格：**${current_price:.2f}**\n"
                f"• 狀況：價格已跌破 169 EMA 關鍵防線！\n"
                f"• 💡 **建議**：中短線趨勢轉弱，建議考慮**減碼或出場**保護資金。"
            )
            send_discord_alert(msg)
            
        elif current_regime == "BEAR_G3":
            msg = (
                f"⚠️ **【{ticker} 宏觀空頭警報】**\n"
                f"• 當前價格：**${current_price:.2f}**\n"
                f"• 狀況：價格被壓制在長天期 576/676 巨型均線下方。\n"
                f"• 💡 **建議**：屬於長期空頭格局，絕對避開做多，逢反彈偏空或空手為宜。"
            )
            send_discord_alert(msg)

if __name__ == "__main__":
    watchlist = load_watchlist()
    print(f"Loaded Watchlist: {watchlist}")
    for ticker in watchlist:
        try:
            check_stock_tunnel(ticker)
        except Exception as e:
            print(f"Error on {ticker}: {e}")
