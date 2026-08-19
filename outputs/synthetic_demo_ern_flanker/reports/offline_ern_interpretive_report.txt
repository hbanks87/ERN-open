# MCS-ERN-Flanker offline report

Run label: `synthetic_demo_ern_flanker`

## Claim boundary
This report summarizes an ERN/Flanker/anxiety analysis pipeline. It is not a clinical interpretation and not proof of mechanism.

## QC summary
Subjects processed: **40**
Median valid error trials/epochs: **28.0**
Median valid correct trials/epochs: **132.0**
Subjects passing minimum error-count gate: **40/40**

## ERN feature summary
Mean ERN error amplitude: **-2.107 µV**
Mean CRN correct amplitude: **-0.548 µV**
Mean DeltaERN error-correct: **-1.559 µV**

## ERN/anxiety association
- pearson: n=40, r=-0.6311, p=1.264e-05
- spearman: n=40, r=-0.6088, p=3.067e-05
- robust_mad_filtered_pearson: n=40, r=-0.6311, p=1.264e-05

## Decision log
- config: loaded — C:\Users\hoytb\Desktop\MCS_ERN\gui_runs\effective_config_20260819_151655.yaml
- trial_table_pipeline: completed — amplitude_col=ern_uv
- primary_statistics: completed — anxiety_col=trait_anxiety

## Next checks
- Confirm event parsing and response-locking against the dataset codebook.
- Verify electrode names and whether FCz/Cz exist or need replacement by dataset montage.
- Inspect grand-average error/correct ERPs before interpreting correlations.
- Treat sensitivity results as robustness checks, not independent confirmations.