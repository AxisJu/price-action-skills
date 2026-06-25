import sys
import os
import unittest
import json
import subprocess
from pathlib import Path

# Add skill root to path
SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(SKILL_ROOT))

class TestPriceAction(unittest.TestCase):
    def setUp(self):
        # Create scratch directory in the artifact space if not exists
        self.artifact_scratch = Path("/Users/axis/.gemini/antigravity/brain/c88e405d-1047-4f9c-8642-3bb9f3e8f6f1/scratch")
        self.artifact_scratch.mkdir(parents=True, exist_ok=True)
        
        self.json_out = self.artifact_scratch / "moutai_result.json"
        self.chart_out = self.artifact_scratch / "moutai_priceaction.png"
        self.report_out = self.artifact_scratch / "moutai_analysis.md"
        
    def test_end_to_end_analysis(self):
        print("\n--- Running End-to-End Price Action Analysis (Moutai: 600519) ---")
        
        # 1. Run pa_analyzer.py
        analyzer_script = SKILL_ROOT / "scripts" / "pa_analyzer.py"
        cmd_analyze = [
            sys.executable, str(analyzer_script),
            "--ticker", "600519",
            "--output", str(self.json_out)
        ]
        
        print(f"Running command: {' '.join(cmd_analyze)}")
        res_analyze = subprocess.run(cmd_analyze, capture_output=True, text=True)
        print("Analyzer STDOUT:\n", res_analyze.stdout)
        print("Analyzer STDERR:\n", res_analyze.stderr)
        
        self.assertEqual(res_analyze.returncode, 0, "Analyzer script failed!")
        self.assertTrue(self.json_out.exists(), "JSON output file does not exist!")
        
        # Verify JSON content
        with open(self.json_out, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.assertIn("ticker", data)
            self.assertIn("market_cycle", data)
            self.assertIn("data_preview", data)
            print(f"Analysis complete. Ticker: {data['ticker']}, Cycle: {data['market_cycle']}")
            print(f"Latest Price Details: {data['latest_price']}")
            
        # 2. Run chart_plotter.py
        plotter_script = SKILL_ROOT / "scripts" / "chart_plotter.py"
        cmd_plot = [
            sys.executable, str(plotter_script),
            "--data", str(self.json_out),
            "--output", str(self.chart_out)
        ]
        
        print(f"Running command: {' '.join(cmd_plot)}")
        res_plot = subprocess.run(cmd_plot, capture_output=True, text=True)
        print("Plotter STDOUT:\n", res_plot.stdout)
        print("Plotter STDERR:\n", res_plot.stderr)
        
        self.assertEqual(res_plot.returncode, 0, "Plotter script failed!")
        self.assertTrue(self.chart_out.exists(), "Annotated chart image does not exist!")
        
        # 3. Generate Markdown Analysis Report
        self.generate_report(data)
        self.assertTrue(self.report_out.exists(), "Report Markdown file does not exist!")
        print(f"E2E Price Action Analysis successful! Outputs saved to {self.artifact_scratch}")

    def generate_report(self, data):
        """Build a beautiful, structured Al Brooks markdown report."""
        latest = data['latest_price']
        setups = data['active_setups']
        wedges = data['wedges']
        
        setup_str = ""
        if setups:
            for s in setups:
                setup_str += f"- **{s['date']}**: Triggered **{s['setup']}** ({s['description']})\n"
        else:
            setup_str = "- No active H1/H2/L1/L2 setups detected on the last few bars.\n"
            
        wedge_str = ""
        if wedges:
            for w in wedges:
                wedge_str += f"- **{w['type']}** detected at bar date **{w['trigger_date']}**\n"
        else:
            wedge_str = "- No active 3-push wedge structures detected.\n"
            
        report_content = f"""# Price Action Strategic Analysis Report

**Target Ticker**: `{data['ticker']}`
**Analysis Date**: {data['analysis_date']}
**Market Cycle Phase**: **{data['market_cycle']}**

---

## 1. Latest Price State (Daily Bar)
- **Bar Date**: `{latest['date']}`
- **Open**: `{latest['open']:.2f}`
- **High**: `{latest['high']:.2f}`
- **Low**: `{latest['low']:.2f}`
- **Close**: `{latest['close']:.2f}`
- **EMA 20**: `{latest['ema20']:.2f}`
- **Price Position**: {"Above EMA 20 (Bull Context)" if latest['close'] > latest['ema20'] else "Below EMA 20 (Bear Context)"}

## 2. Al Brooks Pullback Setups
{setup_str}

## 3. Wedge Reversal Structures
{wedge_str}

---

## 4. Chart Visualization
An annotated K-line chart demonstrating swing structures and setups has been successfully saved to:
`{self.chart_out.name}`
"""
        with open(self.report_out, 'w', encoding='utf-8') as f:
            f.write(report_content)

if __name__ == '__main__':
    unittest.main()
