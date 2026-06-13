#!/usr/bin/env python
"""Run the follow-up treatment-effect investigation (multivariate / dynamics
/ interactions) on the CellScope IC295 results reachable via data/.

    conda run -n cellscope_analysis python scripts/run_followup.py
    # (cellpose4 also works — it has scipy/sklearn/pandas)

Prints arm-structured results for each analysis. Recording = experimental
unit throughout. See docs/DATA.md for provenance and CLAUDE.md for the
hypotheses behind each test.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maskviewer.analysis import multivariate, dynamics, interactions


def main():
    multivariate.run()
    print()
    dynamics.run()
    print()
    interactions.run()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
