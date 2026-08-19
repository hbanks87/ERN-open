# MCS-ERN-Flanker v0.2 GUI

A reproducible Master Comprehensive Suite fork for **ERN / Flanker / anxiety analysis**.

This is a completely separate program from PRAYCG. It does not run MRED, A-MRED, DGA, NUPI, TTI, NIP, CET/EET, Topo-OSM, narrative-analysis, or any PRAYCG meaning module. It borrows only the software discipline: explicit configuration, provenance tables, QC summaries, sensitivity analyses, and a local offline report.

## What is new in v0.2

- Added a Tkinter GUI: `scripts/mcs_ern_flanker_gui.py`.
- Added a Windows launcher: `MCS_ERN_Flanker_GUI_Launcher.bat`.
- Added a config editor panel for common fields.
- Added background execution with live logs.
- Added synthetic-demo creation from the GUI.
- Added local-only confidentiality warning for restricted datasets.

## Quick start: GUI

```bat
cd C:\path\to\MCS_ERN_Flanker_v0_2_GUI
py -3.11 -m pip install -r requirements.txt
py -3.11 scripts\mcs_ern_flanker_gui.py
```

Or double-click:

```text
MCS_ERN_Flanker_GUI_Launcher.bat
```

## Quick start: synthetic demo

```bat
py -3.11 examples\make_synthetic_flanker_demo.py
py -3.11 scripts\run_mcs_ern_flanker.py --config examples\synthetic_demo_config.yaml
```

The demo creates toy data with an artificial ERN-like group effect. It is for pipeline testing only.

## Command-line use

```bat
py -3.11 scripts\run_mcs_ern_flanker.py --config config\default_config.yaml
```

## Outputs

The program writes:

```text
outputs/<run_label>/
  tables/
  figures/
  reports/
```

See `docs/OUTPUT_MAP.md` for details.

## Confidentiality boundary

If you use this for a restricted many-analysts dataset, run it locally and follow that project’s rules. Do not upload private, embargoed, or restricted EEG data to third-party services unless the data-use agreement explicitly allows it.
