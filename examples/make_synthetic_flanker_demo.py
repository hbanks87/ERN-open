#!/usr/bin/env python3
"""Create a synthetic MCS-ERN-Flanker demo dataset.
This toy dataset is for pipeline testing only.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "synthetic_demo"
OUT.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(20260819)
subjects = [f"sub-{i:03d}" for i in range(1, 41)]
rows = []
meta = []
for sid_i, sid in enumerate(subjects):
    anxiety = rng.normal(50, 10)
    # Stronger anxiety associated with more negative DeltaERN in synthetic truth.
    subject_error_shift = -2.0 - 0.045*(anxiety-50) + rng.normal(0, 0.5)
    subject_correct_shift = -0.5 + rng.normal(0, 0.25)
    n_trials = 160
    for trial in range(1, n_trials+1):
        is_error = rng.random() < 0.18
        rt = rng.normal(430 if is_error else 470, 80)
        rt = np.clip(rt, 150, 1200)
        amp = (subject_error_shift if is_error else subject_correct_shift) + rng.normal(0, 2.0)
        rows.append({
            "subject_id": sid,
            "trial_id": trial,
            "condition": "error" if is_error else "correct",
            "correct": 0 if is_error else 1,
            "rt_ms": rt,
            "ern_uv": amp,
        })
    meta.append({"subject_id": sid, "trait_anxiety": anxiety, "age": int(rng.integers(18,45)), "sex": rng.choice(["F","M"]),})

pd.DataFrame(rows).to_csv(OUT / "synthetic_trial_table.csv", index=False)
pd.DataFrame(meta).to_csv(OUT / "synthetic_metadata.csv", index=False)
print(f"Wrote synthetic demo files to: {OUT}")
