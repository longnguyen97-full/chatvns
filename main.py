import sys
import subprocess

def run_pipeline():
    extra_args = sys.argv[1:]

    if not extra_args:
        cmd = [
            sys.executable, "-m", "app.pipeline", "all",
            "--tickers", "HPG", "FPT", "VNM", "VCB", "MBB", "VPB", "HDB", "DXG",
            "GEE", "GEX", "GEL", "VIX", "VIC", "VHM", "VPL", "VRE", "VJC", "GAS", "PLX", "BSR",
            "--include-news",
            "--include-charts",
        ]
    else:
        cmd = [sys.executable, "-m", "app.pipeline"] + extra_args

    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    run_pipeline()