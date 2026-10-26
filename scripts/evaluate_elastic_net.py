"""Run a single model family using the shared comparison protocol."""
import argparse
from pathlib import Path
from scripts.evaluate_regression_suite import run

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir',type=Path,required=True)
    ap.add_argument('--ridge-dir',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    run(a.input_dir,a.ridge_dir,a.output,models=['elastic_net'])
