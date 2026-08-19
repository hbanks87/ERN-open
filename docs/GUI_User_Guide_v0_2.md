# MCS-ERN-Flanker GUI User Guide v0.2

## Launch

```bat
py -3.11 scripts\mcs_ern_flanker_gui.py
```

or double-click:

```text
MCS_ERN_Flanker_GUI_Launcher.bat
```

## Recommended first run

1. Open the GUI.
2. Click **Create synthetic demo and select demo config**.
3. Click **Run analysis**.
4. Click **Open output folder**.
5. Read `reports/offline_ern_interpretive_report.md`.

## Real-data modes

### trial_table

Use this when you already have a trial-level CSV with an ERN-like amplitude column.
Required columns:

```text
subject_id
trial_id
correct or condition
rt_ms
ern_uv or amplitude_uv or response_locked_mean_uv
```

### mne_raw

Use this when you have raw EEG files and event CSVs. Raw files are read through MNE. Event files need response times in seconds from raw start.

Required event columns:

```text
subject_id optional if recoverable from filename
trial_id
correct or condition
rt_ms
response_time_sec
```

## Outputs

Main report:

```text
outputs/<run_label>/reports/offline_ern_interpretive_report.md
```

Main tables:

```text
ern_subject_level_features.csv
ern_anxiety_merged_table.csv
ern_anxiety_correlation_results.csv
participants_qc_summary.csv
sensitivity_analysis_results.csv
```

## Restricted data warning

For embargoed or restricted EEG datasets, run this locally and follow the data-use agreement. Do not upload data, outputs, or results elsewhere unless explicitly permitted.
