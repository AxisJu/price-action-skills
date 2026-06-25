import os
import sys
import json
import argparse
import sqlite3
import re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from loguru import logger
import requests

# ----------------------------------------------------------------------
# EastMoney Direct HTTP Fetcher (Zero dependency fallback for A-Shares)
# ----------------------------------------------------------------------
class EastMoneyFetcher:
    KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    UT = "fa5fd1943c7b386f172d6893dbfba10b"

    @staticmethod
    def _secid(ticker: str) -> str:
        # A-share secid mapping
        if ticker.startswith(('6', '9')):
            return f"1.{ticker}"
        return f"0.{ticker}"

    @classmethod
    def fetch_daily_kline(cls, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch daily stock price from EastMoney API.
        
        Args:
            ticker: 6-digit stock code (e.g. 600519)
            start_date: YYYYMMDD
            end_date: YYYYMMDD
        """
        params = {
            'secid': cls._secid(ticker),
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': '101',   # Daily K-line
            'fqt': '1',     # Adjust forward (前复权)
            'beg': start_date,
            'end': end_date,
            'lmt': '1000',
            'ut': cls.UT,
        }
        import time
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Referer': 'https://quote.eastmoney.com/'
        }
        # Avoid frequency blocking by sleeping for 1.0 second first
        time.sleep(1.0)
        
        for attempt in range(3):
            try:
                logger.info(f"Fetching from EastMoney API for ticker {ticker} ({start_date} to {end_date})... (Attempt {attempt+1})")
                resp = requests.get(cls.KLINE_URL, params=params, headers=headers, proxies={"http": None, "https": None}, timeout=15)
                resp.raise_for_status()
                data = resp.json().get('data')
                if not data or not data.get('klines'):
                    logger.warning(f"No kline data returned from EastMoney API for {ticker}")
                    return pd.DataFrame()
                
                rows = [k.split(',') for k in data['klines']]
                df = pd.DataFrame(rows, columns=[
                    'date', 'open', 'close', 'high', 'low', 'volume',
                    'amount', 'amplitude', 'change_pct', 'change_amt', 'turnover'
                ])
                
                # Format and convert types
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                for col in ['open', 'close', 'high', 'low', 'volume', 'change_pct']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                return df
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed to fetch from EastMoney: {e}")
                time.sleep(1.5)
                
        logger.error(f"All 3 attempts failed to fetch from EastMoney for {ticker}")
        return pd.DataFrame()

# ----------------------------------------------------------------------
# Local SQLite SQLite Database Loader
# ----------------------------------------------------------------------
def fetch_from_local_db(db_path: str, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch price data from the local signal_flux.db database if available."""
    if not os.path.exists(db_path):
        logger.debug(f"Database {db_path} does not exist. Skipping local database fetch.")
        return pd.DataFrame()
        
    try:
        conn = sqlite3.connect(db_path)
        # Parse dates to match the table format
        start_fmt = datetime.strptime(start_date, "%Y%m%d").strftime("%Y-%m-%d")
        end_fmt = datetime.strptime(end_date, "%Y%m%d").strftime("%Y-%m-%d")
        
        query = """
            SELECT date, open, close, high, low, volume, change_pct 
            FROM stock_prices 
            WHERE ticker = ? AND date >= ? AND date <= ?
            ORDER BY date ASC
        """
        df = pd.read_sql_query(query, conn, params=(ticker, start_fmt, end_fmt))
        conn.close()
        
        if not df.empty:
            logger.info(f"Loaded {len(df)} rows from local database {db_path} for ticker {ticker}")
            return df
    except Exception as e:
        logger.error(f"Error reading local SQLite db: {e}")
    return pd.DataFrame()

# ----------------------------------------------------------------------
# Al Brooks Price Action Analyzer
# ----------------------------------------------------------------------
class AlBrooksPAAnalyzer:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        if not self.df.empty:
            self.df = self.df.sort_values('date').reset_index(drop=True)
            self._preprocess()

    def _preprocess(self):
        # Calculate EMA 20
        self.df['ema20'] = self.df['close'].ewm(span=20, adjust=False).mean()
        
        # Calculate sizes
        self.df['range'] = self.df['high'] - self.df['low']
        # Avoid division by zero
        self.df['range'] = self.df['range'].replace(0, 0.0001)
        self.df['body'] = (self.df['close'] - self.df['open']).abs()
        self.df['body_pct'] = self.df['body'] / self.df['range']
        
        # Upper and lower shadow lengths
        self.df['upper_tail'] = self.df['high'] - self.df[['open', 'close']].max(axis=1)
        self.df['lower_tail'] = self.df[['open', 'close']].min(axis=1) - self.df['low']

    def classify_bars(self):
        """Classify each candlestick as Trend Bar or Doji based on Al Brooks criteria."""
        bar_types = []
        descriptions = []
        
        for idx, row in self.df.iterrows():
            body_pct = row['body_pct']
            close = row['close']
            open_ = row['open']
            
            # Al Brooks: Trend bar has body >= 50% of range. Doji has body < 30%.
            if body_pct >= 0.45:
                if close > open_:
                    bar_type = "Bull Trend"
                    desc = "Strong Buyers"
                else:
                    bar_type = "Bear Trend"
                    desc = "Strong Sellers"
            elif body_pct < 0.25:
                bar_type = "Doji"
                desc = "Indecision/Doji"
            else:
                bar_type = "Trading Range"
                desc = "Neutral/Range Bar"
                
            bar_types.append(bar_type)
            descriptions.append(desc)
            
        self.df['bar_type'] = bar_types
        self.df['bar_desc'] = descriptions

    def find_swing_points(self, window: int = 3):
        """Identify Swing Highs and Swing Lows (local extrema)."""
        highs = self.df['high'].values
        lows = self.df['low'].values
        dates = self.df['date'].values
        
        swing_highs = []
        swing_lows = []
        
        for i in range(window, len(self.df) - window):
            # Swing High: Highest high in the window around index i
            if all(highs[i] >= highs[i - w] for w in range(1, window + 1)) and \
               all(highs[i] >= highs[i + w] for w in range(1, window + 1)):
                swing_highs.append({
                    "index": i,
                    "date": dates[i],
                    "price": float(highs[i])
                })
                
            # Swing Low: Lowest low in the window around index i
            if all(lows[i] <= lows[i - w] for w in range(1, window + 1)) and \
               all(lows[i] <= lows[i + w] for w in range(1, window + 1)):
                swing_lows.append({
                    "index": i,
                    "date": dates[i],
                    "price": float(lows[i])
                })
                
        return swing_highs, swing_lows

    def count_pullback_setups(self):
        """Count High 1/2 (H1/H2) and Low 1/2 (L1/L2) pullbacks."""
        close = self.df['close'].values
        high = self.df['high'].values
        low = self.df['low'].values
        ema = self.df['ema20'].values
        
        h_signals = [0] * len(self.df)
        l_signals = [0] * len(self.df)
        
        # Track counts
        h_count = 0
        l_count = 0
        
        # State: are we in a pullback?
        in_bull_pullback = False
        in_bear_pullback = False
        
        # Track the highest high/lowest low during the trend to reset counts
        highest_trend_high = -1.0
        lowest_trend_low = 1e9
        
        for i in range(1, len(self.df)):
            # Check context: Price relative to EMA 20
            # Bullish context: Close is above EMA 20
            is_bullish_context = close[i] > ema[i]
            is_bearish_context = close[i] < ema[i]
            
            # --- Bullish Pullback Count (H1 / H2) ---
            if is_bullish_context:
                l_count = 0
                in_bear_pullback = False
                lowest_trend_low = 1e9
                
                # Check for trend breakout to reset counts
                if high[i] > highest_trend_high:
                    highest_trend_high = high[i]
                    h_count = 0
                    in_bull_pullback = False
                
                # A pullback starts when a bar makes a Lower High
                if high[i] < high[i-1]:
                    in_bull_pullback = True
                
                if in_bull_pullback:
                    # If high breaks prior high, it triggers a High count (H1/H2...)
                    if high[i] > high[i-1]:
                        h_count += 1
                        h_signals[i] = h_count
                        # Temporary reset pullback state until another lower high occurs
                        in_bull_pullback = False
                        
            # --- Bearish Pullback Count (L1 / L2) ---
            elif is_bearish_context:
                h_count = 0
                in_bull_pullback = False
                highest_trend_high = -1.0
                
                # Check for trend breakdown to reset counts
                if low[i] < lowest_trend_low:
                    lowest_trend_low = low[i]
                    l_count = 0
                    in_bear_pullback = False
                
                # A pullback starts when a bar makes a Higher Low
                if low[i] > low[i-1]:
                    in_bear_pullback = True
                
                if in_bear_pullback:
                    # If low breaks prior low, it triggers a Low count (L1/L2...)
                    if low[i] < low[i-1]:
                        l_count += 1
                        l_signals[i] = l_count
                        in_bear_pullback = False
                        
            else:
                # Neutral / Trading Range
                h_count = 0
                l_count = 0
                in_bull_pullback = False
                in_bear_pullback = False
                
        self.df['h_setup'] = h_signals
        self.df['l_setup'] = l_signals

    def detect_wedges(self, swing_highs, swing_lows):
        """Identify Wedge Bottoms (3 lower lows in pullback) and Wedge Tops (3 higher highs)."""
        wedges = []
        
        # Wedge Bottom (Uptrend Pullback Wedge)
        # Search for 3 consecutive swing lows that are descending
        if len(swing_lows) >= 3:
            for i in range(len(swing_lows) - 2):
                sl1 = swing_lows[i]
                sl2 = swing_lows[i+1]
                sl3 = swing_lows[i+2]
                
                # Must be descending prices
                if sl1['price'] > sl2['price'] > sl3['price']:
                    # Check if they are reasonably close in time (e.g. within 40 bars)
                    if sl3['index'] - sl1['index'] < 40:
                        wedges.append({
                            "type": "Wedge Bottom (Bullish Reversal)",
                            "points": [sl1, sl2, sl3],
                            "trigger_index": sl3['index'],
                            "trigger_date": sl3['date']
                        })
                        
        # Wedge Top (Downtrend Pullback Wedge)
        # Search for 3 consecutive swing highs that are ascending
        if len(swing_highs) >= 3:
            for i in range(len(swing_highs) - 2):
                sh1 = swing_highs[i]
                sh2 = swing_highs[i+1]
                sh3 = swing_highs[i+2]
                
                # Must be ascending prices
                if sh1['price'] < sh2['price'] < sh3['price']:
                    if sh3['index'] - sh1['index'] < 40:
                        wedges.append({
                            "type": "Wedge Top (Bearish Reversal)",
                            "points": [sh1, sh2, sh3],
                            "trigger_index": sh3['index'],
                            "trigger_date": sh3['date']
                        })
                        
        return wedges

    def run_analysis(self) -> dict:
        if self.df.empty:
            return {"error": "Empty dataframe"}
            
        self.classify_bars()
        self.count_pullback_setups()
        swing_highs, swing_lows = self.find_swing_points()
        wedges = self.detect_wedges(swing_highs, swing_lows)
        
        # Determine current trend state based on the last bar
        last_idx = len(self.df) - 1
        last_row = self.df.iloc[last_idx]
        
        recent_bars = self.df.tail(15)
        above_ema = (recent_bars['close'] > recent_bars['ema20']).sum()
        
        if above_ema >= 11:
            market_cycle = "Bull Channel / Bull Trend"
        elif above_ema <= 4:
            market_cycle = "Bear Channel / Bear Trend"
        else:
            market_cycle = "Trading Range"
            
        # Detect active signals on the most recent 3 bars
        active_setups = []
        for offset in range(3):
            idx = last_idx - offset
            if idx < 0: continue
            row = self.df.iloc[idx]
            if row['h_setup'] > 0:
                active_setups.append({
                    "date": row['date'],
                    "bar_index": int(idx),
                    "setup": f"H{row['h_setup']}",
                    "description": "Bull trend pullback entry trigger"
                })
            if row['l_setup'] > 0:
                active_setups.append({
                    "date": row['date'],
                    "bar_index": int(idx),
                    "setup": f"L{row['l_setup']}",
                    "description": "Bear trend pullback entry trigger"
                })
                
        # Format the result dictionary
        result = {
            "ticker": "",
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
            "market_cycle": market_cycle,
            "latest_price": {
                "date": last_row['date'],
                "open": float(last_row['open']),
                "high": float(last_row['high']),
                "low": float(last_row['low']),
                "close": float(last_row['close']),
                "volume": float(last_row['volume']),
                "ema20": float(last_row['ema20'])
            },
            "active_setups": active_setups,
            "swing_highs": swing_highs[-10:] if swing_highs else [], # last 10
            "swing_lows": swing_lows[-10:] if swing_lows else [],   # last 10
            "wedges": wedges[-3:] if wedges else [],
            "data_preview": self.df[['date', 'open', 'high', 'low', 'close', 'ema20', 'bar_type', 'h_setup', 'l_setup']].tail(120).to_dict('records')
        }
        
        return result

# ----------------------------------------------------------------------
# Command Line Interface
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Al Brooks Price Action Stock Analyzer")
    parser.add_argument("--ticker", type=str, required=True, help="Stock code (e.g. 600519)")
    parser.add_argument("--start-date", type=str, default="", help="Start date (YYYYMMDD). Defaults to 180 days ago.")
    parser.add_argument("--end-date", type=str, default="", help="End date (YYYYMMDD). Defaults to today.")
    parser.add_argument("--db-path", type=str, default="data/signal_flux.db", help="Path to local database")
    parser.add_argument("--output", type=str, default="scratch/pa_result.json", help="Path to save output JSON")
    
    args = parser.parse_args()
    
    # Compute default dates
    end_dt = datetime.now()
    if not args.end_date:
        end_str = end_dt.strftime("%Y%m%d")
    else:
        end_str = args.end_date
        
    if not args.start_date:
        start_str = (end_dt - timedelta(days=240)).strftime("%Y%m%d")
    else:
        start_str = args.start_date
        
    ticker = args.ticker.strip()
    
    # Resolve ticker format (clean up suffix if present for database queries, e.g., 600519.SH -> 600519)
    clean_ticker = re.sub(r'\.(SH|SZ|HK|US)$', '', ticker, flags=re.IGNORECASE)
    
    # Step 1: Try fetching from EastMoney API first to get up-to-date daily klines
    df = EastMoneyFetcher.fetch_daily_kline(clean_ticker, start_str, end_str)
    
    # Step 2: Fall back to local database if API fails
    if df.empty:
        df = fetch_from_local_db(args.db_path, clean_ticker, start_str, end_str)
        
    if df.empty:
        logger.error(f"Failed to fetch any price history for ticker: {ticker}")
        sys.exit(1)
        
    # Run analyzer
    analyzer = AlBrooksPAAnalyzer(df)
    analysis_res = analyzer.run_analysis()
    analysis_res['ticker'] = ticker
    
    # Save output
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(analysis_res, f, ensure_ascii=False, indent=2)
        
    logger.info(f"Successfully analyzed {ticker} and saved results to {args.output}")

if __name__ == '__main__':
    main()
