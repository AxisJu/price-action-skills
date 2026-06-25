---
name: price-action-skills
description: Analyze stock price movements using Al Brooks Price Action methodology. Use when user wants price action analysis, support/resistance levels, trend channels, swing points, or entry setups (H1/H2/L1/L2) for A-Share or global stocks.
---

# Price Action Skills

## Overview
This skill performs technical analysis on stocks using Al Brooks' classic Price Action (PA) methodology. It programmatically identifies market phases (spikes and channels), swing points, key support and resistance levels, candlestick types, and pullback counting setups (H1/H2/L1/L2).

## Capabilities

### 1. Run Price Action Analysis
Use the python engine `scripts/pa_analyzer.py` to analyze a specific stock code and generate a price action summary.

**Key Tools**:
- `scripts/pa_analyzer.py`:
  - `--ticker`: Stock ticker code (e.g., `600519` for Kweichow Moutai).
  - `--start-date` / `--end-date`: Analysis window.
  - `--output`: Path to write the JSON result (default: `scratch/pa_result.json`).

### 2. Plot Annotated Chart
Use the python script `scripts/chart_plotter.py` to generate K-line charts with highlighted support/resistance lines, swing points, EMA 20, and entry setup labels.

**Key Tools**:
- `scripts/chart_plotter.py`:
  - `--data`: Path to the K-line data or analysis JSON output.
  - `--output`: Path to save the annotated K-line image (PNG).

---

## Workflow

1. **Load Data**: The analyzer retrieves stock OHLCV data from the local database `data/signal_flux.db` or via `akshare`/`yfinance` APIs.
2. **Technical Computations**:
   - Calculates 20 EMA.
   - Identifies trend bars vs doji bars.
   - Detects swing highs/lows and maps them to determine trend direction.
   - Traces pullback H1/H2/L1/L2 counts and wedges.
3. **Generate Image & Report**:
   - Visualizes the findings using `chart_plotter.py`.
   - Produces a detailed Markdown analysis report summarizing current market structure, key setups, and trade options.

## References
For detailed definitions of the rules and patterns used, refer to [al_brooks_cheat_sheet.md](file://references/al_brooks_cheat_sheet.md).
