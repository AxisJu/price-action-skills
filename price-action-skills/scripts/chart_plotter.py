import os
import sys
import json
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime

def plot_price_action(json_path: str, output_img_path: str):
    """Load PA analysis JSON and plot a highly customized, premium dark-mode candlestick chart."""
    if not os.path.exists(json_path):
        print(f"Error: JSON file not found at {json_path}")
        sys.exit(1)
        
    with open(json_path, 'r', encoding='utf-8') as f:
        analysis = json.load(f)
        
    # Read the data preview
    data_preview = analysis.get("data_preview", [])
    if not data_preview:
        print("Error: No data_preview found in JSON")
        sys.exit(1)
        
    df = pd.DataFrame(data_preview)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    # Enable premium styling
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(15, 8), dpi=150)
    
    fig.patch.set_facecolor('#121214')
    ax.set_facecolor('#18181B')
    
    # Plot candlestick bars
    # We will use integer indices on X-axis to avoid gaps on weekends
    x = np.arange(len(df))
    
    bull_color = '#10B981' # Emerald Green
    bear_color = '#EF4444' # Crimson Red
    doji_color = '#9CA3AF' # Grey
    ema_color  = '#F59E0B' # Gold/Amber
    
    # Plot EMA 20
    if 'ema20' in df.columns:
        ax.plot(x, df['ema20'], color=ema_color, linewidth=1.8, label='20 EMA', alpha=0.9)
        
    # Plot candles
    for i in range(len(df)):
        row = df.iloc[i]
        o, h, l, c = row['open'], row['high'], row['low'], row['close']
        
        # Determine color
        if c > o:
            color = bull_color
            fill = True
        elif c < o:
            color = bear_color
            fill = True
        else:
            color = doji_color
            fill = False
            
        # Draw shadow (wick)
        ax.vlines(i, l, h, color=color, linewidth=1.2)
        
        # Draw body
        body_width = 0.6
        if fill:
            rect = patches.Rectangle((i - body_width/2, min(o, c)), body_width, abs(c - o),
                                     facecolor=color, edgecolor=color, linewidth=0.8)
        else:
            rect = patches.Rectangle((i - body_width/2, min(o, c)), body_width, 0.01,
                                     facecolor=color, edgecolor=color, linewidth=0.8)
        ax.add_patch(rect)
        
        # Draw H1/H2 setups (Bull Pullback entries) below the low
        h_setup = row.get('h_setup', 0)
        if h_setup > 0:
            ax.text(i, l - (h - l)*0.3 - 0.01 * c, f"H{int(h_setup)}", color=bull_color,
                    fontsize=9, fontweight='bold', ha='center', va='top')
            ax.plot(i, l - (h - l)*0.1, marker='^', color=bull_color, markersize=4)
            
        # Draw L1/L2 setups (Bear Pullback entries) above the high
        l_setup = row.get('l_setup', 0)
        if l_setup > 0:
            ax.text(i, h + (h - l)*0.3 + 0.01 * c, f"L{int(l_setup)}", color=bear_color,
                    fontsize=9, fontweight='bold', ha='center', va='bottom')
            ax.plot(i, h + (h - l)*0.1, marker='v', color=bear_color, markersize=4)

    # Plot Swing Highs & Swing Lows by matching dates
    # Fetch dates in this preview window
    preview_dates = set(df['date'].dt.strftime('%Y-%m-%d'))
    
    swing_highs = analysis.get("swing_highs", [])
    for sh in swing_highs:
        sh_date = sh['date']
        if sh_date in preview_dates:
            idx = df[df['date'].dt.strftime('%Y-%m-%d') == sh_date].index[0]
            price = sh['price']
            ax.plot(idx, price * 1.008, marker='v', color='#F43F5E', markersize=6, linestyle='None')
            ax.text(idx, price * 1.012, "SH", color='#F43F5E', fontsize=8, ha='center', va='bottom')
            
    swing_lows = analysis.get("swing_lows", [])
    for sl in swing_lows:
        sl_date = sl['date']
        if sl_date in preview_dates:
            idx = df[df['date'].dt.strftime('%Y-%m-%d') == sl_date].index[0]
            price = sl['price']
            ax.plot(idx, price * 0.992, marker='^', color='#06B6D4', markersize=6, linestyle='None')
            ax.text(idx, price * 0.988, "SL", color='#06B6D4', fontsize=8, ha='center', va='top')

    # Format ticks and layout
    # Show dates on X-axis, e.g. every 10 bars
    step = max(1, len(df) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(df['date'].dt.strftime('%m-%d')[::step], rotation=45, color='#9CA3AF')
    ax.tick_params(axis='y', colors='#9CA3AF')
    
    # Grids & Labels
    ax.grid(True, linestyle='--', color='#27272A', alpha=0.7)
    
    ticker = analysis.get("ticker", "Stock")
    cycle = analysis.get("market_cycle", "Unknown Cycle")
    
    ax.set_title(f"{ticker} - Price Action Analysis (Al Brooks Methodology)\nMarket Cycle: {cycle}",
                 color='#F3F4F6', fontsize=14, fontweight='bold', pad=15)
    
    # Border styling
    for spine in ax.spines.values():
        spine.set_color('#27272A')
        
    ax.legend(facecolor='#18181B', edgecolor='#27272A', loc='upper left')
    
    # Tight layout and save
    plt.tight_layout()
    os.makedirs(os.path.dirname(output_img_path), exist_ok=True)
    plt.savefig(output_img_path, facecolor='#121214')
    plt.close()
    print(f"Chart saved successfully to {output_img_path}")

def main():
    parser = argparse.ArgumentParser(description="Al Brooks Price Action Chart Plotter")
    parser.add_argument("--data", type=str, required=True, help="Path to analysis JSON file")
    parser.add_argument("--output", type=str, required=True, help="Path to save output chart image")
    args = parser.parse_args()
    
    plot_price_action(args.data, args.output)

if __name__ == '__main__':
    main()
