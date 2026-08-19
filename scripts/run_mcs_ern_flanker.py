#!/usr/bin/env python3
"""MCS-ERN-Flanker v0.2
Standalone ERN/Flanker/anxiety analysis pipeline.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

try:
    from scipy import stats
except Exception:  # pragma: no cover
    stats = None

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None

try:
    import mne
except Exception:  # pragma: no cover
    mne = None

try:
    import statsmodels.api as sm
except Exception:  # pragma: no cover
    sm = None


def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def ensure_dirs(output_root: Path, run_label: str) -> Dict[str, Path]:
    run_dir = output_root / run_label
    dirs = {
        "run": run_dir,
        "tables": run_dir / "tables",
        "figures": run_dir / "figures",
        "reports": run_dir / "reports",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def zbool_correct(series: pd.Series, cfg: Dict[str, Any]) -> pd.Series:
    correct_values = set(str(v).lower() for v in cfg["event_parsing"].get("correct_values", []))
    error_values = set(str(v).lower() for v in cfg["event_parsing"].get("error_values", []))
    out = []
    for v in series:
        s = str(v).strip().lower()
        if s in correct_values:
            out.append(True)
        elif s in error_values:
            out.append(False)
        else:
            try:
                out.append(bool(int(float(s))))
            except Exception:
                out.append(np.nan)
    return pd.Series(out, index=series.index)


def file_inventory(paths: List[Path]) -> pd.DataFrame:
    rows = []
    for p in paths:
        rows.append({
            "path": str(p),
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else np.nan,
        })
    return pd.DataFrame(rows)


def classify_trials(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    ep = cfg["event_parsing"]
    subject_col = ep.get("subject_col", "subject_id")
    trial_id_col = ep.get("trial_id_col", "trial_id")
    condition_col = ep.get("condition_col", "condition")
    correct_col = ep.get("correct_col", "correct")
    rt_col = ep.get("rt_ms_col", "rt_ms")

    if subject_col not in df.columns:
        raise ValueError(f"Missing subject column: {subject_col}")
    if trial_id_col not in df.columns:
        df[trial_id_col] = np.arange(len(df)) + 1
    if correct_col in df.columns:
        df["is_correct"] = zbool_correct(df[correct_col], cfg)
    elif condition_col in df.columns:
        df["is_correct"] = ~df[condition_col].astype(str).str.lower().str.contains("err|incorr|wrong|0")
    else:
        raise ValueError("Need either a correct column or a condition column")
    if rt_col not in df.columns:
        df[rt_col] = np.nan
    df["rt_valid"] = True
    if rt_col in df.columns:
        df["rt_valid"] = df[rt_col].between(ep.get("min_rt_ms", 150), ep.get("max_rt_ms", 1500), inclusive="both")
    df["trial_valid"] = df["is_correct"].notna() & df["rt_valid"]
    df["trial_type"] = np.where(df["is_correct"], "correct", "error")
    return df


def amplitude_from_wave(times_ms: np.ndarray, data_uv: np.ndarray, window_ms: Tuple[float, float], method: str) -> float:
    mask = (times_ms >= window_ms[0]) & (times_ms <= window_ms[1])
    if not np.any(mask):
        return np.nan
    segment = data_uv[..., mask]
    if method == "peak":
        return float(np.nanmin(segment))
    return float(np.nanmean(segment))


def trial_table_pipeline(cfg: Dict[str, Any], dirs: Dict[str, Path], log_rows: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trial_path = Path(cfg["input"].get("trial_table_csv", ""))
    meta_path = Path(cfg["input"].get("metadata_csv", ""))
    if not trial_path.exists():
        raise FileNotFoundError(f"Trial table not found: {trial_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata table not found: {meta_path}")
    trials = pd.read_csv(trial_path)
    trials = classify_trials(trials, cfg)
    subj_col = cfg["event_parsing"].get("subject_col", "subject_id")

    # Accept one of these trial-level amplitude columns.
    amp_candidates = ["ern_uv", "amplitude_uv", "response_locked_mean_uv"]
    amp_col = next((c for c in amp_candidates if c in trials.columns), None)
    if amp_col is None:
        raise ValueError(f"Trial-table mode requires one amplitude column: {amp_candidates}")

    valid = trials[trials["trial_valid"]].copy()
    summary_rows = []
    for sid, g in valid.groupby(subj_col):
        errors = g[g["trial_type"] == "error"]
        corrects = g[g["trial_type"] == "correct"]
        ern = errors[amp_col].mean() if len(errors) else np.nan
        crn = corrects[amp_col].mean() if len(corrects) else np.nan
        delta = ern - crn if pd.notna(ern) and pd.notna(crn) else np.nan
        summary_rows.append({
            "subject_id": sid,
            "valid_error_count": int(len(errors)),
            "valid_correct_count": int(len(corrects)),
            "ERN_error_uv": ern,
            "CRN_correct_uv": crn,
            "DeltaERN_error_minus_correct_uv": delta,
            "DeltaERN_correct_minus_error_uv": -delta if pd.notna(delta) else np.nan,
            "qc_min_error_trials_pass": int(len(errors) >= cfg["ern"].get("min_error_trials", 6)),
            "qc_min_correct_trials_pass": int(len(corrects) >= cfg["ern"].get("min_correct_trials", 20)),
        })
    features = pd.DataFrame(summary_rows)
    qc = features[["subject_id", "valid_error_count", "valid_correct_count", "qc_min_error_trials_pass", "qc_min_correct_trials_pass"]].copy()
    metadata = pd.read_csv(meta_path)
    trials.to_csv(dirs["tables"] / "trial_classification_table.csv", index=False)
    features.to_csv(dirs["tables"] / "ern_subject_level_features.csv", index=False)
    qc.to_csv(dirs["tables"] / "participants_qc_summary.csv", index=False)
    metadata.to_csv(dirs["tables"] / "anxiety_subject_level_variables.csv", index=False)
    log_rows.append({"module": "trial_table_pipeline", "status": "completed", "detail": f"amplitude_col={amp_col}"})
    return features, metadata, trials


def load_raw(path: Path):
    if mne is None:
        raise RuntimeError("MNE is required for mne_raw mode. Install mne or use trial_table mode.")
    suffix = path.suffix.lower()
    name = path.name.lower()
    if name.endswith(".fif") or name.endswith(".fif.gz"):
        return mne.io.read_raw_fif(path, preload=True, verbose="ERROR")
    if suffix in [".edf", ".bdf"]:
        return mne.io.read_raw_edf(path, preload=True, verbose="ERROR")
    if suffix == ".gdf":
        return mne.io.read_raw_gdf(path, preload=True, verbose="ERROR")
    if suffix == ".vhdr":
        return mne.io.read_raw_brainvision(path, preload=True, verbose="ERROR")
    if suffix == ".set":
        return mne.io.read_raw_eeglab(path, preload=True, verbose="ERROR")
    raise ValueError(f"Unsupported raw format for automatic import: {path}")


def find_subject_id(path: Path, cfg: Dict[str, Any]) -> str:
    rgx = cfg["input"].get("subject_id_regex", "")
    if rgx:
        m = re.search(rgx, path.name)
        if m:
            return m.group(1) if m.groups() else m.group(0)
    return path.stem


def preprocess_raw(raw, cfg: Dict[str, Any]):
    pp = cfg["preprocessing"]
    bads = pp.get("bad_channels", []) or []
    raw.info["bads"] = [b for b in bads if b in raw.ch_names]
    if pp.get("notch_freqs"):
        raw.notch_filter(pp.get("notch_freqs"), verbose="ERROR")
    raw.filter(pp.get("l_freq", None), pp.get("h_freq", None), verbose="ERROR")
    if pp.get("rereference", "none") == "average":
        raw.set_eeg_reference("average", projection=False, verbose="ERROR")
    return raw


def process_subject_raw(raw_path: Path, event_path: Path, cfg: Dict[str, Any], dirs: Dict[str, Path], sensitivity_rows: List[Dict[str, Any]], erp_rows: List[Dict[str, Any]]):
    sid = find_subject_id(raw_path, cfg)
    raw = preprocess_raw(load_raw(raw_path), cfg)
    events_df = pd.read_csv(event_path)
    events_df = classify_trials(events_df, cfg)
    ep = cfg["event_parsing"]
    resp_col = ep.get("response_time_sec_col", "response_time_sec")
    if resp_col not in events_df.columns:
        raise ValueError(f"Event file for {sid} missing {resp_col}")
    valid_events = events_df[events_df["trial_valid"]].copy()

    sfreq = raw.info["sfreq"]
    samples = raw.time_as_index(valid_events[resp_col].astype(float).values)
    event_id_map = {"correct": 1, "error": 2}
    event_codes = np.where(valid_events["trial_type"].values == "error", 2, 1)
    events = np.column_stack([samples, np.zeros(len(samples), dtype=int), event_codes])

    pp = cfg["preprocessing"]
    baseline = tuple(pp.get("baseline_sec", [-0.2, 0.0]))
    reject_uv = pp.get("reject_peak_to_peak_uv", 150.0)
    reject = {"eeg": reject_uv * 1e-6}
    epochs = mne.Epochs(raw, events, event_id=event_id_map, tmin=pp.get("epoch_tmin_sec", -0.2),
                        tmax=pp.get("epoch_tmax_sec", 0.4), baseline=baseline, preload=True,
                        reject=reject, verbose="ERROR")
    primary_channels = [ch for ch in cfg["ern"].get("channels", ["FCz", "Cz"]) if ch in epochs.ch_names]
    if not primary_channels:
        primary_channels = epochs.ch_names[:min(2, len(epochs.ch_names))]

    def compute_for(chs, window, method, reject_label=None):
        picks = [ch for ch in chs if ch in epochs.ch_names]
        if not picks:
            return np.nan, np.nan, np.nan
        e_err = epochs["error"].copy().pick(picks)
        e_cor = epochs["correct"].copy().pick(picks)
        err_data = e_err.get_data() * 1e6
        cor_data = e_cor.get_data() * 1e6
        times_ms = e_err.times * 1000.0
        err_wave = np.nanmean(err_data, axis=(0,1)) if len(err_data) else np.full_like(times_ms, np.nan)
        cor_wave = np.nanmean(cor_data, axis=(0,1)) if len(cor_data) else np.full_like(times_ms, np.nan)
        ern = amplitude_from_wave(times_ms, err_wave, tuple(window), method)
        crn = amplitude_from_wave(times_ms, cor_wave, tuple(window), method)
        return ern, crn, (ern-crn if pd.notna(ern) and pd.notna(crn) else np.nan)

    ern, crn, delta = compute_for(primary_channels, cfg["ern"].get("window_ms", [0, 100]), cfg["ern"].get("amplitude_method", "mean"))

    # ERP long rows for primary cluster
    for condition in ["error", "correct"]:
        e = epochs[condition].copy().pick(primary_channels)
        data = e.get_data() * 1e6
        if len(data):
            wave = np.nanmean(data, axis=(0,1))
            for t_ms, val in zip(e.times*1000.0, wave):
                erp_rows.append({"subject_id": sid, "condition": condition, "time_ms": t_ms, "amplitude_uv": val})

    # sensitivity combinations
    if cfg.get("sensitivity", {}).get("enabled", True):
        for window in cfg["sensitivity"].get("windows_ms", [[0,100]]):
            for chs in cfg["sensitivity"].get("channel_clusters", [primary_channels]):
                for method in cfg["sensitivity"].get("amplitude_methods", ["mean"]):
                    se, sc, sd = compute_for(chs, window, method)
                    sensitivity_rows.append({
                        "subject_id": sid,
                        "window_ms": str(window),
                        "channels": "+".join(chs),
                        "method": method,
                        "ERN_error_uv": se,
                        "CRN_correct_uv": sc,
                        "DeltaERN_error_minus_correct_uv": sd,
                    })

    n_error = len(epochs["error"])
    n_correct = len(epochs["correct"])
    return {
        "subject_id": sid,
        "raw_file": str(raw_path),
        "event_file": str(event_path),
        "valid_error_count": int(n_error),
        "valid_correct_count": int(n_correct),
        "ERN_error_uv": ern,
        "CRN_correct_uv": crn,
        "DeltaERN_error_minus_correct_uv": delta,
        "DeltaERN_correct_minus_error_uv": -delta if pd.notna(delta) else np.nan,
        "qc_min_error_trials_pass": int(n_error >= cfg["ern"].get("min_error_trials", 6)),
        "qc_min_correct_trials_pass": int(n_correct >= cfg["ern"].get("min_correct_trials", 20)),
    }


def mne_raw_pipeline(cfg: Dict[str, Any], dirs: Dict[str, Path], log_rows: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_dir = Path(cfg["input"].get("raw_dir", "data/raw"))
    events_dir = Path(cfg["input"].get("events_dir", "data/events"))
    raw_files = sorted(raw_dir.glob(cfg["input"].get("raw_glob", "*.fif")))
    event_files = sorted(events_dir.glob(cfg["input"].get("events_glob", "*.csv")))
    if not raw_files:
        raise FileNotFoundError(f"No raw files found in {raw_dir}")
    if not event_files:
        raise FileNotFoundError(f"No event files found in {events_dir}")
    event_by_sid = {find_subject_id(p, cfg): p for p in event_files}
    sensitivity_rows, erp_rows, feature_rows = [], [], []
    for rf in raw_files:
        sid = find_subject_id(rf, cfg)
        ev = event_by_sid.get(sid)
        if ev is None:
            log_rows.append({"module": "mne_raw_pipeline", "status": "skipped", "detail": f"no events for {sid}"})
            continue
        feature_rows.append(process_subject_raw(rf, ev, cfg, dirs, sensitivity_rows, erp_rows))
        log_rows.append({"module": "mne_raw_pipeline", "status": "processed", "detail": sid})
    features = pd.DataFrame(feature_rows)
    qc = features[["subject_id", "valid_error_count", "valid_correct_count", "qc_min_error_trials_pass", "qc_min_correct_trials_pass"]].copy()
    meta_path = Path(cfg["input"].get("metadata_csv", ""))
    metadata = pd.read_csv(meta_path) if meta_path.exists() else pd.DataFrame({"subject_id": features["subject_id"]})
    pd.DataFrame(erp_rows).to_csv(dirs["tables"] / "grand_erp_long_table.csv", index=False)
    pd.DataFrame(sensitivity_rows).to_csv(dirs["tables"] / "sensitivity_subject_level_features_long.csv", index=False)
    features.to_csv(dirs["tables"] / "ern_subject_level_features.csv", index=False)
    qc.to_csv(dirs["tables"] / "participants_qc_summary.csv", index=False)
    metadata.to_csv(dirs["tables"] / "anxiety_subject_level_variables.csv", index=False)
    return features, metadata, pd.DataFrame()


def merge_and_stats(features: pd.DataFrame, metadata: pd.DataFrame, cfg: Dict[str, Any], dirs: Dict[str, Path], log_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    subj_col_meta = cfg["statistics"].get("subject_col", "subject_id")
    anxiety_col = cfg["statistics"].get("anxiety_column", "trait_anxiety")
    if subj_col_meta != "subject_id" and subj_col_meta in metadata.columns:
        metadata = metadata.rename(columns={subj_col_meta: "subject_id"})
    merged = features.merge(metadata, on="subject_id", how="left")
    merged.to_csv(dirs["tables"] / "ern_anxiety_merged_table.csv", index=False)
    rows = []
    x = merged["DeltaERN_error_minus_correct_uv"]
    y = merged[anxiety_col] if anxiety_col in merged.columns else pd.Series(dtype=float)
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) >= 3 and stats is not None:
        pr = stats.pearsonr(valid["x"], valid["y"])
        sr = stats.spearmanr(valid["x"], valid["y"])
        rows.append({"analysis": "pearson", "n": len(valid), "r": pr.statistic, "p": pr.pvalue})
        rows.append({"analysis": "spearman", "n": len(valid), "r": sr.statistic, "p": sr.pvalue})
        # robust approximate skipped correlation: remove bivariate MAD outliers.
        mx, my = valid["x"].median(), valid["y"].median()
        madx = np.median(np.abs(valid["x"] - mx)) + 1e-9
        mady = np.median(np.abs(valid["y"] - my)) + 1e-9
        keep = (np.abs(valid["x"]-mx)/(1.4826*madx) < 3.5) & (np.abs(valid["y"]-my)/(1.4826*mady) < 3.5)
        if keep.sum() >= 3:
            rr = stats.pearsonr(valid.loc[keep,"x"], valid.loc[keep,"y"])
            rows.append({"analysis": "robust_mad_filtered_pearson", "n": int(keep.sum()), "r": rr.statistic, "p": rr.pvalue})
    else:
        rows.append({"analysis": "insufficient_data", "n": int(len(valid)), "r": np.nan, "p": np.nan})
    stat_df = pd.DataFrame(rows)
    stat_df.to_csv(dirs["tables"] / "ern_anxiety_correlation_results.csv", index=False)

    # Optional regression.
    reg_rows = []
    covariates = cfg["statistics"].get("covariates", []) or []
    available_covs = [c for c in covariates if c in merged.columns]
    if sm is not None and anxiety_col in merged.columns and len(merged.dropna(subset=["DeltaERN_error_minus_correct_uv", anxiety_col] + available_covs)) >= max(4, 2+len(available_covs)):
        sub = merged.dropna(subset=["DeltaERN_error_minus_correct_uv", anxiety_col] + available_covs).copy()
        X = sub[[anxiety_col] + available_covs]
        X = sm.add_constant(X)
        model = sm.OLS(sub["DeltaERN_error_minus_correct_uv"], X).fit()
        for term, coef, pval in zip(model.params.index, model.params.values, model.pvalues.values):
            reg_rows.append({"term": term, "coef": coef, "p": pval, "n": len(sub), "r2": model.rsquared})
    else:
        reg_rows.append({"term": "not_run", "coef": np.nan, "p": np.nan, "n": np.nan, "r2": np.nan})
    pd.DataFrame(reg_rows).to_csv(dirs["tables"] / "optional_regression_results.csv", index=False)
    log_rows.append({"module": "primary_statistics", "status": "completed", "detail": f"anxiety_col={anxiety_col}"})
    return merged


def sensitivity_stats(cfg: Dict[str, Any], dirs: Dict[str, Path], merged: pd.DataFrame) -> None:
    sens_path = dirs["tables"] / "sensitivity_subject_level_features_long.csv"
    anxiety_col = cfg["statistics"].get("anxiety_column", "trait_anxiety")
    rows = []
    if sens_path.exists():
        sens = pd.read_csv(sens_path)
        meta_cols = ["subject_id", anxiety_col]
        if anxiety_col in merged.columns:
            meta = merged[meta_cols].drop_duplicates()
            sens = sens.merge(meta, on="subject_id", how="left")
            for keys, g in sens.groupby(["window_ms", "channels", "method"]):
                valid = g[["DeltaERN_error_minus_correct_uv", anxiety_col]].dropna()
                if len(valid) >= 3 and stats is not None:
                    r = stats.pearsonr(valid["DeltaERN_error_minus_correct_uv"], valid[anxiety_col])
                    rows.append({"window_ms": keys[0], "channels": keys[1], "method": keys[2], "n": len(valid), "r": r.statistic, "p": r.pvalue})
    if not rows:
        rows.append({"window_ms": "primary_only_or_not_available", "channels": "", "method": "", "n": np.nan, "r": np.nan, "p": np.nan})
    pd.DataFrame(rows).to_csv(dirs["tables"] / "sensitivity_analysis_results.csv", index=False)


def make_figures(cfg: Dict[str, Any], dirs: Dict[str, Path], merged: pd.DataFrame) -> None:
    if plt is None or not cfg.get("reporting", {}).get("make_figures", True):
        return
    # Scatter.
    anxiety_col = cfg["statistics"].get("anxiety_column", "trait_anxiety")
    if anxiety_col in merged.columns:
        sub = merged.dropna(subset=["DeltaERN_error_minus_correct_uv", anxiety_col])
        if len(sub) >= 2:
            fig, ax = plt.subplots(figsize=(7,5))
            ax.scatter(sub[anxiety_col], sub["DeltaERN_error_minus_correct_uv"])
            ax.set_xlabel(anxiety_col)
            ax.set_ylabel("DeltaERN error-correct (µV)")
            ax.set_title("ERN/anxiety association")
            fig.tight_layout()
            fig.savefig(dirs["figures"] / "ern_anxiety_scatter.png", dpi=150)
            plt.close(fig)
    # QC retention.
    qc_path = dirs["tables"] / "participants_qc_summary.csv"
    if qc_path.exists():
        qc = pd.read_csv(qc_path)
        if not qc.empty:
            fig, ax = plt.subplots(figsize=(8,4))
            ax.bar(np.arange(len(qc)), qc["valid_error_count"], label="error")
            ax.bar(np.arange(len(qc)), qc["valid_correct_count"], bottom=qc["valid_error_count"], label="correct")
            ax.set_xticks(np.arange(len(qc)))
            ax.set_xticklabels(qc["subject_id"].astype(str), rotation=90, fontsize=7)
            ax.set_ylabel("Valid epoch/trial count")
            ax.legend()
            ax.set_title("Valid trial/epoch counts")
            fig.tight_layout()
            fig.savefig(dirs["figures"] / "qc_retention_plot.png", dpi=150)
            plt.close(fig)
    # ERP grand average if available.
    erp_path = dirs["tables"] / "grand_erp_long_table.csv"
    if erp_path.exists():
        erp = pd.read_csv(erp_path)
        if not erp.empty:
            fig, ax = plt.subplots(figsize=(8,5))
            for cond, g in erp.groupby("condition"):
                mean = g.groupby("time_ms")["amplitude_uv"].mean().reset_index()
                ax.plot(mean["time_ms"], mean["amplitude_uv"], label=cond)
            ax.axvline(0, color="black", linewidth=0.8)
            ax.axhline(0, color="black", linewidth=0.5)
            ax.invert_yaxis()
            ax.set_xlabel("Time from response (ms)")
            ax.set_ylabel("Amplitude (µV; negative up)")
            ax.set_title("Grand-average response-locked ERP")
            ax.legend()
            fig.tight_layout()
            fig.savefig(dirs["figures"] / "ern_grand_average_error_correct.png", dpi=150)
            plt.close(fig)


def make_report(cfg: Dict[str, Any], dirs: Dict[str, Path], log_rows: List[Dict[str, Any]]) -> None:
    merged_path = dirs["tables"] / "ern_anxiety_merged_table.csv"
    stats_path = dirs["tables"] / "ern_anxiety_correlation_results.csv"
    qc_path = dirs["tables"] / "participants_qc_summary.csv"
    features_path = dirs["tables"] / "ern_subject_level_features.csv"
    merged = pd.read_csv(merged_path) if merged_path.exists() else pd.DataFrame()
    stat_df = pd.read_csv(stats_path) if stats_path.exists() else pd.DataFrame()
    qc = pd.read_csv(qc_path) if qc_path.exists() else pd.DataFrame()
    feat = pd.read_csv(features_path) if features_path.exists() else pd.DataFrame()

    lines = []
    lines.append(f"# MCS-ERN-Flanker offline report")
    lines.append("")
    lines.append(f"Run label: `{cfg['project'].get('run_label')}`")
    lines.append("")
    lines.append("## Claim boundary")
    lines.append("This report summarizes an ERN/Flanker/anxiety analysis pipeline. It is not a clinical interpretation and not proof of mechanism.")
    lines.append("")
    lines.append("## QC summary")
    if not qc.empty:
        lines.append(f"Subjects processed: **{len(qc)}**")
        lines.append(f"Median valid error trials/epochs: **{qc['valid_error_count'].median():.1f}**")
        lines.append(f"Median valid correct trials/epochs: **{qc['valid_correct_count'].median():.1f}**")
        lines.append(f"Subjects passing minimum error-count gate: **{int(qc['qc_min_error_trials_pass'].sum())}/{len(qc)}**")
    else:
        lines.append("No QC table found.")
    lines.append("")
    lines.append("## ERN feature summary")
    if not feat.empty:
        lines.append(f"Mean ERN error amplitude: **{feat['ERN_error_uv'].mean():.3f} µV**")
        lines.append(f"Mean CRN correct amplitude: **{feat['CRN_correct_uv'].mean():.3f} µV**")
        lines.append(f"Mean DeltaERN error-correct: **{feat['DeltaERN_error_minus_correct_uv'].mean():.3f} µV**")
    else:
        lines.append("No ERN feature table found.")
    lines.append("")
    lines.append("## ERN/anxiety association")
    if not stat_df.empty:
        for _, row in stat_df.iterrows():
            lines.append(f"- {row['analysis']}: n={row.get('n','')}, r={row.get('r', np.nan):.4f}, p={row.get('p', np.nan):.4g}")
    else:
        lines.append("No statistics table found.")
    lines.append("")
    lines.append("## Decision log")
    for row in log_rows:
        lines.append(f"- {row.get('module')}: {row.get('status')} — {row.get('detail','')}")
    lines.append("")
    lines.append("## Next checks")
    lines.append("- Confirm event parsing and response-locking against the dataset codebook.")
    lines.append("- Verify electrode names and whether FCz/Cz exist or need replacement by dataset montage.")
    lines.append("- Inspect grand-average error/correct ERPs before interpreting correlations.")
    lines.append("- Treat sensitivity results as robustness checks, not independent confirmations.")

    text = "\n".join(lines)
    (dirs["reports"] / "offline_ern_interpretive_report.md").write_text(text, encoding="utf-8")
    (dirs["reports"] / "offline_ern_interpretive_report.txt").write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="MCS-ERN-Flanker v0.2")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    ap.add_argument("--print-config", action="store_true", help="Print parsed config and exit")
    args = ap.parse_args()
    cfg_path = Path(args.config)
    cfg = load_yaml(cfg_path)
    if args.print_config:
        print(json.dumps(cfg, indent=2))
        return 0
    run_label = cfg.get("project", {}).get("run_label", "MCS_ERN_Flanker_Run")
    output_root = Path(cfg.get("project", {}).get("output_root", "outputs"))
    dirs = ensure_dirs(output_root, run_label)
    log_rows: List[Dict[str, Any]] = []
    log_rows.append({"module": "config", "status": "loaded", "detail": str(cfg_path)})

    input_mode = cfg.get("input", {}).get("mode", "trial_table")
    inv_paths = [cfg_path]
    for k in ["trial_table_csv", "metadata_csv", "raw_dir", "events_dir"]:
        val = cfg.get("input", {}).get(k)
        if val:
            inv_paths.append(Path(val))
    file_inventory(inv_paths).to_csv(dirs["tables"] / "file_inventory.csv", index=False)

    if input_mode == "trial_table":
        features, metadata, trials = trial_table_pipeline(cfg, dirs, log_rows)
    elif input_mode == "mne_raw":
        features, metadata, trials = mne_raw_pipeline(cfg, dirs, log_rows)
    else:
        raise ValueError(f"Unknown input.mode: {input_mode}")

    merged = merge_and_stats(features, metadata, cfg, dirs, log_rows)
    sensitivity_stats(cfg, dirs, merged)
    make_figures(cfg, dirs, merged)
    pd.DataFrame(log_rows).to_csv(dirs["tables"] / "preprocessing_decision_log.csv", index=False)
    manifest = {
        "schema": "MCS_ERN_Flanker_analysis_manifest_v0_2",
        "run_label": run_label,
        "config_path": str(cfg_path),
        "output_dir": str(dirs["run"]),
        "input_mode": input_mode,
        "boundary": "ERN/Flanker analysis only; not PRAYCG/narrative/meaning analysis.",
    }
    write_json(dirs["reports"] / "analysis_manifest.json", manifest)
    make_report(cfg, dirs, log_rows)
    print(f"MCS-ERN-Flanker completed. Output: {dirs['run']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
