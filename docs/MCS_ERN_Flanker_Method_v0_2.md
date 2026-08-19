# MCS-ERN-Flanker Method v0.2

## Objective

Estimate response-locked ERN and CRN amplitudes from Flanker-task EEG, compute Delta ERN, merge with anxiety/personality metadata, and test the ERN-anxiety association.

## Primary features

```text
ERN_error_uv = mean or negative peak amplitude in configured ERN window for error trials.
CRN_correct_uv = mean or negative peak amplitude in same window for correct trials.
DeltaERN_error_minus_correct_uv = ERN_error_uv - CRN_correct_uv.
```

## Primary statistics

```text
Pearson correlation: DeltaERN ~ anxiety
Spearman correlation: DeltaERN ~ anxiety
Robust MAD-filtered Pearson: approximate sensitivity check
Optional regression: DeltaERN ~ anxiety + covariates
```

## QC gates

```text
minimum valid error trials
minimum valid correct trials
reaction-time validity
artifact rejection / peak-to-peak threshold in raw mode
```

## Non-claims

This is not PRAYCG, not narrative psychophysiology, not meaning analysis, not clinical diagnosis, and not proof of a causal personality mechanism.
