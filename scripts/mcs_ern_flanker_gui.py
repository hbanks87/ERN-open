#!/usr/bin/env python3
"""Tkinter GUI for MCS-ERN-Flanker v0.2."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import yaml
except Exception:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "scripts" / "run_mcs_ern_flanker.py"
DEMO_SCRIPT = ROOT / "examples" / "make_synthetic_flanker_demo.py"
DEFAULT_CONFIG = ROOT / "config" / "default_config.yaml"
DEMO_CONFIG = ROOT / "examples" / "synthetic_demo_config.yaml"


def load_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: py -3.11 -m pip install -r requirements.txt")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, obj: Dict[str, Any]) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: py -3.11 -m pip install -r requirements.txt")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False)


def set_if_not_blank(cfg: Dict[str, Any], path, value: str):
    if value is None or str(value).strip() == "":
        return
    cur = cfg
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


class MCSERNGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MCS-ERN-Flanker v0.2 GUI")
        self.geometry("1050x760")
        self.log_queue = queue.Queue()
        self.worker = None
        self.process = None
        self.config_path = tk.StringVar(value=str(DEFAULT_CONFIG))
        self.mode = tk.StringVar(value="trial_table")
        self.trial_table_csv = tk.StringVar(value="")
        self.raw_dir = tk.StringVar(value="")
        self.events_dir = tk.StringVar(value="")
        self.metadata_csv = tk.StringVar(value="")
        self.output_root = tk.StringVar(value="outputs")
        self.run_label = tk.StringVar(value="MCS_ERN_Flanker_Run")
        self.anxiety_col = tk.StringVar(value="trait_anxiety")
        self.subject_col = tk.StringVar(value="subject_id")
        self.status = tk.StringVar(value="Ready.")
        self.last_output_dir = None
        self._build_ui()
        self.after(100, self._poll_log_queue)
        self._load_config_into_fields(silent=True)

    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="MCS-ERN-Flanker v0.2 — ERN / Flanker / Anxiety Analysis GUI", font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w")
        boundary = ttk.Label(main, text="Local ERN pipeline only. Do not upload restricted/embargoed data. Not PRAYCG, not meaning analysis, not clinical software.", foreground="#8a3b00")
        boundary.pack(anchor="w", pady=(2,8))

        nb = ttk.Notebook(main)
        nb.pack(fill="both", expand=True)
        setup = ttk.Frame(nb, padding=8)
        run_tab = ttk.Frame(nb, padding=8)
        help_tab = ttk.Frame(nb, padding=8)
        nb.add(setup, text="1. Configure")
        nb.add(run_tab, text="2. Run + Logs")
        nb.add(help_tab, text="Help")

        self._build_config_tab(setup)
        self._build_run_tab(run_tab)
        self._build_help_tab(help_tab)

        bottom = ttk.Frame(main)
        bottom.pack(fill="x", pady=(8,0))
        ttk.Label(bottom, textvariable=self.status).pack(side="left", anchor="w")

    def row_file(self, parent, label, var, kind="file", patterns=None):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=24).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=4)
        def browse():
            if kind == "dir":
                p = filedialog.askdirectory()
            else:
                p = filedialog.askopenfilename(filetypes=patterns or [("All files","*.*")])
            if p:
                var.set(p)
        ttk.Button(row, text="Browse", command=browse).pack(side="right")

    def _build_config_tab(self, tab):
        top = ttk.LabelFrame(tab, text="Config file")
        top.pack(fill="x", pady=4)
        self.row_file(top, "Config YAML", self.config_path, patterns=[("YAML","*.yaml *.yml"),("All files","*.*")])
        row = ttk.Frame(top); row.pack(fill="x", pady=3)
        ttk.Button(row, text="Load config into fields", command=self._load_config_into_fields).pack(side="left")
        ttk.Button(row, text="Save effective config", command=self.save_effective_config_dialog).pack(side="left", padx=5)
        ttk.Button(row, text="Config self-check", command=self.config_self_check).pack(side="left", padx=5)

        inp = ttk.LabelFrame(tab, text="Common input settings")
        inp.pack(fill="x", pady=4)
        row = ttk.Frame(inp); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Input mode", width=24).pack(side="left")
        ttk.Combobox(row, textvariable=self.mode, values=["trial_table", "mne_raw"], width=20, state="readonly").pack(side="left")
        self.row_file(inp, "Trial table CSV", self.trial_table_csv, patterns=[("CSV","*.csv"),("All files","*.*")])
        self.row_file(inp, "Raw EEG folder", self.raw_dir, kind="dir")
        self.row_file(inp, "Events folder", self.events_dir, kind="dir")
        self.row_file(inp, "Metadata/personality CSV", self.metadata_csv, patterns=[("CSV","*.csv"),("All files","*.*")])

        out = ttk.LabelFrame(tab, text="Output and statistics")
        out.pack(fill="x", pady=4)
        self.row_file(out, "Output root", self.output_root, kind="dir")
        row = ttk.Frame(out); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Run label", width=24).pack(side="left")
        ttk.Entry(row, textvariable=self.run_label).pack(side="left", fill="x", expand=True)
        row = ttk.Frame(out); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Anxiety column", width=24).pack(side="left")
        ttk.Entry(row, textvariable=self.anxiety_col).pack(side="left", fill="x", expand=True, padx=(0,6))
        ttk.Label(row, text="Subject column", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.subject_col).pack(side="left", fill="x", expand=True)

        demo = ttk.LabelFrame(tab, text="Synthetic demo")
        demo.pack(fill="x", pady=4)
        ttk.Label(demo, text="Creates local toy data under examples/synthetic_demo and selects the synthetic config.").pack(anchor="w")
        ttk.Button(demo, text="Create synthetic demo and select demo config", command=self.make_demo).pack(anchor="w", pady=4)

    def _build_run_tab(self, tab):
        buttons = ttk.Frame(tab)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Run analysis", command=self.run_analysis).pack(side="left")
        ttk.Button(buttons, text="Stop", command=self.stop_process).pack(side="left", padx=5)
        ttk.Button(buttons, text="Open output folder", command=self.open_output_folder).pack(side="left", padx=5)
        ttk.Button(buttons, text="Clear log", command=lambda: self.log.delete("1.0", "end")).pack(side="left", padx=5)
        self.log = tk.Text(tab, wrap="word", height=32, font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(8,0))

    def _build_help_tab(self, tab):
        txt = tk.Text(tab, wrap="word", font=("Segoe UI", 10))
        txt.pack(fill="both", expand=True)
        txt.insert("end", """MCS-ERN-Flanker GUI help\n\n1. Use the synthetic demo first. Click 'Create synthetic demo', then run analysis.\n\n2. For restricted real data, do not upload data or results to outside services unless the project explicitly allows it.\n\n3. trial_table mode expects a CSV with subject_id, trial_id, correct/condition, rt_ms, and ern_uv/amplitude_uv.\n\n4. mne_raw mode expects raw EEG files readable by MNE plus event CSVs with response_time_sec and correct/error labels.\n\n5. Main outputs are in outputs/<run_label>/tables, figures, and reports.\n\n6. If the pipeline fails, check the live log and the config paths.\n""")
        txt.config(state="disabled")

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def _load_config_into_fields(self, silent=False):
        try:
            cfg = load_yaml(Path(self.config_path.get()))
            self.mode.set(cfg.get("input", {}).get("mode", self.mode.get()))
            self.trial_table_csv.set(str(cfg.get("input", {}).get("trial_table_csv", "")))
            self.raw_dir.set(str(cfg.get("input", {}).get("raw_dir", "")))
            self.events_dir.set(str(cfg.get("input", {}).get("events_dir", "")))
            self.metadata_csv.set(str(cfg.get("input", {}).get("metadata_csv", "")))
            self.output_root.set(str(cfg.get("project", {}).get("output_root", "outputs")))
            self.run_label.set(str(cfg.get("project", {}).get("run_label", "MCS_ERN_Flanker_Run")))
            self.anxiety_col.set(str(cfg.get("statistics", {}).get("anxiety_column", "trait_anxiety")))
            self.subject_col.set(str(cfg.get("statistics", {}).get("subject_col", "subject_id")))
            if not silent:
                self._log(f"Loaded config: {self.config_path.get()}")
        except Exception as e:
            if not silent:
                messagebox.showerror("Config load failed", str(e))

    def build_effective_config(self) -> Dict[str, Any]:
        cfg = load_yaml(Path(self.config_path.get()))
        set_if_not_blank(cfg, ["input", "mode"], self.mode.get())
        set_if_not_blank(cfg, ["input", "trial_table_csv"], self.trial_table_csv.get())
        set_if_not_blank(cfg, ["input", "raw_dir"], self.raw_dir.get())
        set_if_not_blank(cfg, ["input", "events_dir"], self.events_dir.get())
        set_if_not_blank(cfg, ["input", "metadata_csv"], self.metadata_csv.get())
        set_if_not_blank(cfg, ["project", "output_root"], self.output_root.get())
        set_if_not_blank(cfg, ["project", "run_label"], self.run_label.get())
        set_if_not_blank(cfg, ["statistics", "anxiety_column"], self.anxiety_col.get())
        set_if_not_blank(cfg, ["statistics", "subject_col"], self.subject_col.get())
        # Keep event parser subject column aligned unless user config says otherwise.
        set_if_not_blank(cfg, ["event_parsing", "subject_col"], self.subject_col.get())
        return cfg

    def save_effective_config(self) -> Path:
        cfg = self.build_effective_config()
        tmp_dir = ROOT / "gui_runs"
        tmp_dir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = tmp_dir / f"effective_config_{stamp}.yaml"
        save_yaml(path, cfg)
        self._log(f"Saved effective config: {path}")
        return path

    def save_effective_config_dialog(self):
        try:
            cfg = self.build_effective_config()
            p = filedialog.asksaveasfilename(defaultextension=".yaml", filetypes=[("YAML","*.yaml"),("All files","*.*")])
            if p:
                save_yaml(Path(p), cfg)
                self._log(f"Saved effective config: {p}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def config_self_check(self):
        try:
            cfg = self.build_effective_config()
            problems = []
            mode = cfg.get("input", {}).get("mode")
            if mode == "trial_table":
                for key in ["trial_table_csv", "metadata_csv"]:
                    p = Path(cfg.get("input", {}).get(key, ""))
                    if not p.exists(): problems.append(f"Missing {key}: {p}")
            elif mode == "mne_raw":
                for key in ["raw_dir", "events_dir"]:
                    p = Path(cfg.get("input", {}).get(key, ""))
                    if not p.exists(): problems.append(f"Missing {key}: {p}")
            else:
                problems.append(f"Unknown mode: {mode}")
            if problems:
                self._log("Config self-check warnings:\n" + "\n".join("- "+p for p in problems))
                messagebox.showwarning("Config warnings", "\n".join(problems))
            else:
                self._log("Config self-check passed.")
                messagebox.showinfo("Config self-check", "No obvious path/config problems found.")
        except Exception as e:
            messagebox.showerror("Config check failed", str(e))

    def make_demo(self):
        self._run_subprocess([sys.executable, str(DEMO_SCRIPT)], after=lambda: self._select_demo_config())

    def _select_demo_config(self):
        if DEMO_CONFIG.exists():
            self.config_path.set(str(DEMO_CONFIG))
            self._load_config_into_fields(silent=True)
            self._log(f"Selected demo config: {DEMO_CONFIG}")

    def run_analysis(self):
        try:
            cfg_path = self.save_effective_config()
            out_root = Path(self.output_root.get() or "outputs")
            self.last_output_dir = out_root / (self.run_label.get() or "MCS_ERN_Flanker_Run")
            self._run_subprocess([sys.executable, str(RUN_SCRIPT), "--config", str(cfg_path)])
        except Exception as e:
            messagebox.showerror("Run failed to start", str(e))

    def _run_subprocess(self, cmd, after=None):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Already running", "A process is already running.")
            return
        self.status.set("Running...")
        self._log("COMMAND: " + " ".join(map(str, cmd)))
        def worker():
            try:
                self.process = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in self.process.stdout:
                    self.log_queue.put(line.rstrip())
                rc = self.process.wait()
                self.log_queue.put(f"PROCESS_EXIT_CODE={rc}")
                if rc == 0 and after:
                    self.after(0, after)
                self.after(0, lambda: self.status.set("Ready." if rc == 0 else f"Failed with exit code {rc}."))
            except Exception as e:
                self.log_queue.put("ERROR: " + str(e))
                self.after(0, lambda: self.status.set("Error."))
            finally:
                self.process = None
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _poll_log_queue(self):
        try:
            while True:
                self._log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def stop_process(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self._log("Termination requested.")

    def open_output_folder(self):
        p = self.last_output_dir or (Path(self.output_root.get() or "outputs") / (self.run_label.get() or "MCS_ERN_Flanker_Run"))
        p = p.resolve()
        if not p.exists():
            messagebox.showwarning("Missing output", f"Output folder does not exist yet:\n{p}")
            return
        if sys.platform.startswith("win"):
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])


if __name__ == "__main__":
    app = MCSERNGUI()
    app.mainloop()
