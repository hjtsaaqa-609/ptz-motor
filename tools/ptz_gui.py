#!/usr/bin/env python3
import datetime as dt
import os
import platform
import queue
import sys
import threading
import time
import traceback

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, simpledialog

import serial
from serial.tools import list_ports


DRIVER_PROFILES = {
    "GC6609": {"steps_per_rev": 3200, "wakeup_us": 0},
    "DM556": {"steps_per_rev": 1600, "wakeup_us": 0},
    "A4988": {"steps_per_rev": 1600, "wakeup_us": 1000},
    "TMC2209": {"steps_per_rev": 1600, "wakeup_us": 0},
}
DEFAULT_DRIVER = "A4988"
A4988_MICROSTEP_STEPS = [200, 400, 800, 1600, 3200]
TMC2209_MICROSTEP_STEPS = [1600, 3200, 6400, 12800]
DRIVER_STEP_PRESETS = {
    "GC6609": [1600, 3200],
    "DM556": [400, 800, 1600, 3200, 6400],
    "A4988": A4988_MICROSTEP_STEPS,
    "TMC2209": TMC2209_MICROSTEP_STEPS,
}
SPEED_MIN_RPM = 1
SPEED_MAX_RPM = 1875
ACCEL_MIN_RPMPS = 4
ACCEL_MAX_RPMPS = 1875
DEFAULT_SPEED_RPM = 10
DEFAULT_ACCEL_RPMPS = 60
QUEUE_POLL_BATCH = 64
LOG_MAX_LINES = 2000
LOG_TRIM_TO_LINES = 1200
HEALTH_LOG_INTERVAL_MS = 5000
SERIAL_IDLE_WARN_MS = 3000

BG = "#eef3ef"
PANEL = "#fbfdf9"
PANEL_ALT = "#e3ece3"
TEXT = "#213128"
MUTED = "#607267"
ACCENT = "#2f7a67"
ACCENT_SOFT = "#d5ebe4"
BTN = "#d9e3dc"
BTN_ACTIVE = "#cad6cf"
BTN_GO = "#5f9361"
BTN_WARN = "#d59d45"
BTN_STOP = "#b85c52"
VALUE_BG = "#ffffff"
LINE = "#cdd9d1"
M1_PANEL = "#f8faf6"
M1_HEAD = "#dbe8d8"
M1_LINE = "#72926d"
M2_PANEL = "#f8f8fb"
M2_HEAD = "#dbe1ef"
M2_LINE = "#6e81aa"
OK_BG = "#6f9e66"
ERR_BG = "#c16057"
INFO_BG = "#6f7f87"
LOG_BG = "#f4f6f4"
SELECT_ON_BG = "#355f52"
SELECT_OFF_BG = "#b0b8b2"
SELECT_PARTIAL_BG = "#c1873f"
CHART_BG = "#f7faf7"
CHART_GRID = "#d6ddd7"
CHART_TEXT = "#54645a"
M1_TRACE = "#5f9361"
M2_TRACE = "#5878b1"
LOG_DIR = Path("/Users/michael/Documents/AI Codex/PTZ/logs")
LOG_FILE = LOG_DIR / "ptz_gui_runtime.log"

MOTOR_STYLE = {
    "m1": {
        "title": "M1 / PAN",
        "panel": M1_PANEL,
        "head": M1_HEAD,
        "line": M1_LINE,
        "tag": "TIM1 PA8 STEP | PA0 DIR | PA1 EN",
    },
    "m2": {
        "title": "M2 / TILT",
        "panel": M2_PANEL,
        "head": M2_HEAD,
        "line": M2_LINE,
        "tag": "TIM3 PB4 STEP | PB0 DIR | PB1 EN",
    },
}


@dataclass
class MotorTelemetry:
    driver: str = DEFAULT_DRIVER
    steps_rev: int = DRIVER_PROFILES[DEFAULT_DRIVER]["steps_per_rev"]
    wakeup_us: int = DRIVER_PROFILES[DEFAULT_DRIVER]["wakeup_us"]
    state: str = "IDLE"
    dir: str = "STOP"
    target_hz: int = 0
    actual_hz: int = 0
    rpm: int = 0
    zero: int = 0
    edges: int = 0
    accel_hzps: int = 0
    fault: str = "NONE"
    override: int = 0


class SerialClient:
    def __init__(self):
        self.ser = None
        self.queue = queue.Queue()
        self.stop_evt = threading.Event()
        self.thread = None

    def connect(self, port: str, baud: int):
        self.disconnect()
        self.ser = serial.Serial(port, baud, timeout=0.2)
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass
        self.stop_evt.clear()
        self.thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.thread.start()

    def disconnect(self):
        self.stop_evt.set()
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def send_line(self, text: str):
        if not self.is_open():
            raise RuntimeError("serial link not connected")
        self.ser.write((text.strip() + "\r\n").encode())

    def flush_input(self):
        if not self.is_open():
            return
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def _rx_loop(self):
        while not self.stop_evt.is_set():
            if self.ser is None:
                break
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if line:
                    self.queue.put(line)
            except Exception as exc:
                self.queue.put(f"ERR code=SERIAL detail={str(exc).replace(' ', '_')}")
                break


class MotorCard:
    def __init__(self, app, parent, motor_key: str):
        self.app = app
        self.motor_key = motor_key
        style = MOTOR_STYLE[motor_key]
        self.style = style
        self.selected_var = tk.IntVar(value=1)
        self.speed_var = tk.StringVar(value=str(DEFAULT_SPEED_RPM))
        self.accel_var = tk.StringVar(value=str(DEFAULT_ACCEL_RPMPS))
        self.driver_var = tk.StringVar(value=DEFAULT_DRIVER)
        self.steps_var = tk.StringVar(value=str(DRIVER_PROFILES[DEFAULT_DRIVER]["steps_per_rev"]))
        self.wakeup_var = tk.StringVar(value=str(DRIVER_PROFILES[DEFAULT_DRIVER]["wakeup_us"]))
        self.badge_var = tk.StringVar(value=f"{style['title']} IDLE")
        self.selection_var = tk.StringVar(value="Included in grouped actions")
        self.target_var = tk.StringVar(value="0 rpm")
        self.actual_var = tk.StringVar(value="0 rpm")
        self.state_var = tk.StringVar(value="IDLE")
        self.dir_var = tk.StringVar(value="STOP")
        self.zero_var = tk.StringVar(value="0")
        self.fault_var = tk.StringVar(value="NONE")
        self.override_var = tk.StringVar(value="0")
        self.accel_status_var = tk.StringVar(value=f"{DEFAULT_ACCEL_RPMPS} rpm/s")
        self.steps_buttons = []

        self.panel, _head, body = app.create_panel(parent, style["title"], style["tag"], style["panel"], style["head"], style["line"])
        self.panel.pack(fill=tk.X, pady=(0, 16))
        self.selection_badge = None

        self.badge = tk.Button(
            body,
            textvariable=self.badge_var,
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=style["line"],
            font=("Helvetica", 11, "bold"),
            cursor="arrow",
            anchor=tk.W,
        )
        self.badge.pack(fill=tk.X)

        selection_row = tk.Frame(body, bg=style["panel"])
        selection_row.pack(fill=tk.X, pady=(10, 10))
        tk.Checkbutton(
            selection_row,
            text="Group Select",
            variable=self.selected_var,
            command=self._selection_changed,
            bg=style["panel"],
            fg=TEXT,
            activebackground=style["panel"],
            selectcolor=VALUE_BG,
            font=("Helvetica", 10, "bold"),
        ).pack(side=tk.LEFT)
        self.selection_badge = tk.Button(
            selection_row,
            textvariable=self.selection_var,
            bg=SELECT_ON_BG,
            fg="#ffffff",
            activebackground=SELECT_ON_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=7,
            highlightthickness=1,
            highlightbackground=style["line"],
            font=("Helvetica", 10, "bold"),
            cursor="arrow",
            width=24,
        )
        self.selection_badge.pack(side=tk.RIGHT)

        cfg = tk.Frame(body, bg=style["panel"])
        cfg.pack(fill=tk.X, pady=(0, 10))
        self._build_driver_row(cfg, style["panel"])
        self._build_steps_row(cfg, style["panel"])
        self._build_wakeup_row(cfg, style["panel"])
        self._build_speed_row(cfg, style["panel"])
        self._build_accel_row(cfg, style["panel"])

        metrics = tk.Frame(body, bg=style["panel"])
        metrics.pack(fill=tk.X, pady=(0, 10))
        for col in range(3):
            metrics.grid_columnconfigure(col, weight=1)
        app.metric_tile(metrics, 0, "State", self.state_var)
        app.metric_tile(metrics, 1, "Direction", self.dir_var)
        app.metric_tile(metrics, 2, "Target", self.target_var)

        metrics2 = tk.Frame(body, bg=style["panel"])
        metrics2.pack(fill=tk.X, pady=(0, 10))
        for col in range(3):
            metrics2.grid_columnconfigure(col, weight=1)
        app.metric_tile(metrics2, 0, "Actual", self.actual_var)
        app.metric_tile(metrics2, 1, "Accel", self.accel_status_var)
        app.metric_tile(metrics2, 2, "0-bit", self.zero_var)

        metrics3 = tk.Frame(body, bg=style["panel"])
        metrics3.pack(fill=tk.X, pady=(0, 10))
        for col in range(2):
            metrics3.grid_columnconfigure(col, weight=1)
        app.metric_tile(metrics3, 0, "Fault", self.fault_var)
        app.metric_tile(metrics3, 1, "Pin Override", self.override_var)

        ctrl = tk.Frame(body, bg=style["panel"])
        ctrl.pack(fill=tk.X, pady=(0, 10))
        app.button(ctrl, f"{motor_key.upper()} FWD", lambda: app.drive_motor(motor_key, "f"), width=11, bg=BTN_GO, fg="#ffffff").pack(side=tk.LEFT)
        app.button(ctrl, f"{motor_key.upper()} REV", lambda: app.drive_motor(motor_key, "r"), width=11, bg=ACCENT, fg="#ffffff").pack(side=tk.LEFT, padx=8)
        app.button(ctrl, f"{motor_key.upper()} STOP", lambda: app.stop_motor(motor_key), width=11, bg=BTN_STOP, fg="#ffffff").pack(side=tk.LEFT)
        app.button(ctrl, "Apply Accel", lambda: app.apply_motor_cfg(motor_key), width=11, bg=BTN_WARN).pack(side=tk.RIGHT)

        diag = tk.Frame(body, bg=style["panel"])
        diag.pack(fill=tk.X, pady=(0, 10))
        app.button(diag, "Diag", lambda: app.send_line(f"{motor_key} diag"), width=8).pack(side=tk.LEFT)
        app.button(diag, "Clear Fault", lambda: app.send_line(f"{motor_key} clear"), width=11).pack(side=tk.LEFT, padx=8)

        pins = tk.Frame(body, bg=style["panel"])
        pins.pack(fill=tk.X)
        app.button(pins, "DIR Low", lambda: app.pin_test(motor_key, "dir", "lo"), width=8).pack(side=tk.LEFT)
        app.button(pins, "DIR High", lambda: app.pin_test(motor_key, "dir", "hi"), width=8).pack(side=tk.LEFT, padx=6)
        app.button(pins, "EN Low", lambda: app.pin_test(motor_key, "en", "lo"), width=8).pack(side=tk.LEFT)
        app.button(pins, "EN High", lambda: app.pin_test(motor_key, "en", "hi"), width=8).pack(side=tk.LEFT, padx=6)
        app.button(pins, "STEP Low", lambda: app.pin_test(motor_key, "step", "lo"), width=9).pack(side=tk.LEFT)
        app.button(pins, "STEP High", lambda: app.pin_test(motor_key, "step", "hi"), width=9).pack(side=tk.LEFT, padx=6)
        app.button(pins, "Restore", lambda: app.pin_restore(motor_key), width=9, bg=ACCENT_SOFT).pack(side=tk.RIGHT)
        self.refresh_group_visuals()

    def _selection_changed(self):
        if self.selected_var.get():
            self.selection_var.set("Included in grouped actions")
        else:
            self.selection_var.set("Excluded from grouped actions")
        self.refresh_group_visuals()
        self.app.refresh_group_summary()

    def refresh_group_visuals(self):
        selected = bool(self.selected_var.get())
        if selected:
            self.selection_var.set("Included in grouped actions")
            self.selection_badge.configure(bg=SELECT_ON_BG, activebackground=SELECT_ON_BG)
            self.panel.configure(highlightbackground=self.style["line"], highlightthickness=2)
        else:
            self.selection_var.set("Excluded from grouped actions")
            self.selection_badge.configure(bg=SELECT_OFF_BG, activebackground=SELECT_OFF_BG)
            self.panel.configure(highlightbackground=LINE, highlightthickness=1)

    def _build_speed_row(self, parent, panel_bg):
        row = tk.Frame(parent, bg=panel_bg)
        row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row, text="Speed", bg=panel_bg, fg=TEXT, font=("Helvetica", 11, "bold")).pack(side=tk.LEFT)
        self.app.button(row, "-10", lambda: self.adjust_speed(-10), width=5).pack(side=tk.LEFT, padx=(10, 6))
        self.app.button(row, "-1", lambda: self.adjust_speed(-1), width=4).pack(side=tk.LEFT, padx=(0, 6))
        self.app.value_button(row, self.speed_var, lambda: self.prompt_speed("Speed rpm", self.speed_var, SPEED_MIN_RPM, SPEED_MAX_RPM), width=10).pack(side=tk.LEFT)
        tk.Label(row, text="rpm", bg=panel_bg, fg=MUTED, font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(6, 12))
        self.app.button(row, "+1", lambda: self.adjust_speed(1), width=4).pack(side=tk.LEFT, padx=(0, 6))
        self.app.button(row, "+10", lambda: self.adjust_speed(10), width=5).pack(side=tk.LEFT)

    def _build_driver_row(self, parent, panel_bg):
        row = tk.Frame(parent, bg=panel_bg)
        row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row, text="Driver", bg=panel_bg, fg=TEXT, font=("Helvetica", 11, "bold")).pack(side=tk.LEFT)
        self.app.value_button(row, self.driver_var, width=10).pack(side=tk.LEFT, padx=(10, 10))
        self.app.button(row, "GC6609", lambda: self.app.set_driver(self.motor_key, "GC6609"), width=8).pack(side=tk.LEFT)
        self.app.button(row, "DM556", lambda: self.app.set_driver(self.motor_key, "DM556"), width=8, bg=ACCENT_SOFT).pack(side=tk.LEFT, padx=6)
        self.app.button(row, "A4988", lambda: self.app.set_driver(self.motor_key, "A4988"), width=8).pack(side=tk.LEFT)
        self.app.button(row, "TMC2209", lambda: self.app.set_driver(self.motor_key, "TMC2209"), width=9).pack(side=tk.LEFT, padx=6)

    def _build_steps_row(self, parent, panel_bg):
        row = tk.Frame(parent, bg=panel_bg)
        row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row, text="Steps/rev", bg=panel_bg, fg=TEXT, font=("Helvetica", 11, "bold")).pack(side=tk.LEFT)
        self.app.value_button(
            row,
            self.steps_var,
            lambda: self.app.prompt_steps_rev(self.motor_key),
            width=10,
        ).pack(side=tk.LEFT, padx=(10, 10))
        for idx in range(5):
            btn = self.app.button(row, "", lambda: None, width=6)
            btn.pack(side=tk.LEFT, padx=(0, 6) if idx < 4 else 0)
            self.steps_buttons.append(btn)
        self.refresh_steps_presets()

    def refresh_steps_presets(self):
        driver = self.driver_var.get().strip().upper() or DEFAULT_DRIVER
        presets = DRIVER_STEP_PRESETS.get(driver, A4988_MICROSTEP_STEPS)
        current_steps = self.steps_var.get().strip()
        for idx, btn in enumerate(self.steps_buttons):
            if idx < len(presets):
                steps = presets[idx]
                btn.configure(
                    text=str(steps),
                    command=lambda s=steps: self.app.set_steps_rev(self.motor_key, s),
                    state=tk.NORMAL,
                    bg=ACCENT_SOFT if str(steps) == current_steps else BTN,
                    activebackground=BTN_ACTIVE,
                )
            else:
                btn.configure(text="--", command=lambda: None, state=tk.DISABLED, bg=BTN)

    def _build_wakeup_row(self, parent, panel_bg):
        row = tk.Frame(parent, bg=panel_bg)
        row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row, text="Wakeup", bg=panel_bg, fg=TEXT, font=("Helvetica", 11, "bold")).pack(side=tk.LEFT)
        self.app.button(row, "-500", lambda: self.app.adjust_wakeup_us(self.motor_key, -500), width=6).pack(side=tk.LEFT, padx=(10, 6))
        self.app.button(row, "-100", lambda: self.app.adjust_wakeup_us(self.motor_key, -100), width=6).pack(side=tk.LEFT, padx=(0, 6))
        self.app.value_button(
            row,
            self.wakeup_var,
            lambda: self.app.prompt_wakeup_us(self.motor_key),
            width=10,
        ).pack(side=tk.LEFT)
        tk.Label(row, text="us", bg=panel_bg, fg=MUTED, font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(6, 12))
        self.app.button(row, "+100", lambda: self.app.adjust_wakeup_us(self.motor_key, 100), width=6).pack(side=tk.LEFT, padx=(0, 6))
        self.app.button(row, "+500", lambda: self.app.adjust_wakeup_us(self.motor_key, 500), width=6).pack(side=tk.LEFT)

    def _build_accel_row(self, parent, panel_bg):
        row = tk.Frame(parent, bg=panel_bg)
        row.pack(fill=tk.X)
        tk.Label(row, text="Accel", bg=panel_bg, fg=TEXT, font=("Helvetica", 11, "bold")).pack(side=tk.LEFT)
        self.app.button(row, "-20", lambda: self.adjust_accel(-20), width=5).pack(side=tk.LEFT, padx=(10, 6))
        self.app.button(row, "-5", lambda: self.adjust_accel(-5), width=4).pack(side=tk.LEFT, padx=(0, 6))
        self.app.value_button(row, self.accel_var, lambda: self.prompt_speed("Accel rpm/s", self.accel_var, ACCEL_MIN_RPMPS, ACCEL_MAX_RPMPS), width=10).pack(side=tk.LEFT)
        tk.Label(row, text="rpm/s", bg=panel_bg, fg=MUTED, font=("Helvetica", 10)).pack(side=tk.LEFT, padx=(6, 12))
        self.app.button(row, "+5", lambda: self.adjust_accel(5), width=4).pack(side=tk.LEFT, padx=(0, 6))
        self.app.button(row, "+20", lambda: self.adjust_accel(20), width=5).pack(side=tk.LEFT)

    def adjust_speed(self, delta: int):
        try:
            value = int(self.speed_var.get())
        except ValueError:
            value = DEFAULT_SPEED_RPM
        value = max(SPEED_MIN_RPM, min(SPEED_MAX_RPM, value + delta))
        self.speed_var.set(str(value))

    def adjust_accel(self, delta: int):
        try:
            value = int(self.accel_var.get())
        except ValueError:
            value = DEFAULT_ACCEL_RPMPS
        value = max(ACCEL_MIN_RPMPS, min(ACCEL_MAX_RPMPS, value + delta))
        self.accel_var.set(str(value))

    def prompt_speed(self, title: str, var: tk.StringVar, min_v: int, max_v: int):
        try:
            current = int(var.get())
        except ValueError:
            current = min_v
        value = simpledialog.askinteger(title, f"Input {title} ({min_v}-{max_v})", parent=self.app.root, initialvalue=current, minvalue=min_v, maxvalue=max_v)
        if value is not None:
            var.set(str(value))

    def update_from_telemetry(self, data: MotorTelemetry):
        self.driver_var.set(data.driver)
        self.steps_var.set(str(data.steps_rev))
        self.wakeup_var.set(str(data.wakeup_us))
        self.refresh_steps_presets()
        self.state_var.set(data.state)
        self.dir_var.set(data.dir)
        steps_rev = max(1, data.steps_rev)
        self.target_var.set(f"{data.target_hz * 60 // steps_rev} rpm")
        self.actual_var.set(f"{data.rpm} rpm")
        self.zero_var.set(str(data.zero))
        self.fault_var.set(data.fault)
        self.override_var.set(str(data.override))
        accel_rpmps = data.accel_hzps * 60 // steps_rev if data.accel_hzps else 0
        self.accel_status_var.set(f"{accel_rpmps} rpm/s")

        title = MOTOR_STYLE[self.motor_key]["title"]
        if data.override:
            text = f"{title} PIN TEST"
            bg = BTN_WARN
        elif data.fault != "NONE":
            text = f"{title} FAULT {data.fault}"
            bg = ERR_BG
        elif data.state == "RUN":
            text = f"{title} {data.dir} {data.rpm} rpm"
            bg = BTN_GO if data.dir == "FWD" else ACCENT
        elif data.state.startswith("RAMP"):
            text = f"{title} {data.state} {data.rpm} rpm"
            bg = BTN_WARN
        else:
            zero_suffix = " | 0-bit ON" if data.zero else ""
            text = f"{title} IDLE{zero_suffix}"
            bg = INFO_BG
        self.badge_var.set(text)
        self.badge.configure(bg=bg, activebackground=bg)


class PTZGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PTZ Pegasus Console")
        self.root.geometry("1560x960")
        self.root.minsize(1320, 860)
        self.root.configure(bg=BG)
        self.client = SerialClient()
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="115200")
        self.mode_var = tk.StringVar(value="continuous")
        self.jog_ms_var = tk.StringVar(value="250")
        self.pulse_hz_var = tk.StringVar(value="1.0")
        self.jog_display_var = tk.StringVar()
        self.pulse_display_var = tk.StringVar()
        self.build_var = tk.StringVar(value="FW unknown")
        self.link_var = tk.StringVar(value="Disconnected")
        self.event_var = tk.StringVar(value="No events")
        self.telemetry_var = tk.StringVar(value="telemetry=on")
        self.manual_var = tk.StringVar()
        self.group_var = tk.StringVar(value="Grouped axes: M1 + M2")
        self.mode_hint_var = tk.StringVar(value="Continuous mode: selected axes keep rotating until Stop")
        self.cards = {}
        self.telemetry = {"m1": MotorTelemetry(), "m2": MotorTelemetry()}
        self.pulse_job = {"m1": None, "m2": None}
        self.pulse_active = {"m1": False, "m2": False}
        self.pulse_direction = {"m1": "f", "m2": "f"}
        self.connect_seq = 0
        self.active_connect_seq = 0
        self.version_query_job = None
        self.port_menu = None
        self.build_badge = None
        self.link_badge = None
        self.event_badge = None
        self.group_badge = None
        self.trend_canvas = None
        self.trend_note_var = tk.StringVar(value="Trend window: waiting for STAT frames")
        self.trend_history = deque(maxlen=120)
        self.log = None
        self.log_line_count = 0
        self.last_rx_monotonic = None
        self.last_stat_monotonic = None
        self.last_health_log_monotonic = None
        self.stats_frames = 0
        self.redraw_count = 0
        self.health_job = None

        self.jog_ms_var.trace_add("write", lambda *_args: self._refresh_mode_value_labels())
        self.pulse_hz_var.trace_add("write", lambda *_args: self._refresh_mode_value_labels())
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.root.report_callback_exception = self._report_callback_exception
        self._write_runtime_log("=== GUI START ===")
        self._write_runtime_log(self._runtime_banner())
        self._build_ui()
        self._warn_if_legacy_tk()
        self.mode_var.trace_add("write", self._on_mode_changed)
        self.refresh_ports()
        self.root.after(80, self._poll_queue)
        self.health_job = self.root.after(HEALTH_LOG_INTERVAL_MS, self._health_tick)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._refresh_mode_value_labels()
        self.refresh_group_summary()
        self._update_mode_hint()

    def button(self, parent, text, cmd, width=10, bg=BTN, fg=TEXT):
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            width=width,
            bg=bg,
            fg=fg,
            activebackground=BTN_ACTIVE if bg == BTN else bg,
            activeforeground=fg,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=7,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="hand2",
        )

    def value_button(self, parent, var, cmd=None, width=10):
        return tk.Button(
            parent,
            textvariable=var,
            command=cmd,
            width=width,
            bg=VALUE_BG,
            fg=TEXT,
            activebackground=VALUE_BG,
            activeforeground=TEXT,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=7,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="hand2" if cmd else "arrow",
        )

    def entry(self, parent, var, width=12, justify=tk.CENTER):
        return tk.Entry(
            parent,
            textvariable=var,
            width=width,
            justify=justify,
            bg=VALUE_BG,
            fg=TEXT,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=LINE,
            insertbackground=TEXT,
            font=("Helvetica", 10),
        )

    def create_panel(self, parent, title: str, subtitle: str, panel_bg=PANEL, head_bg=PANEL_ALT, line=LINE):
        panel = tk.Frame(parent, bg=panel_bg, highlightthickness=1, highlightbackground=line)
        head = tk.Frame(panel, bg=head_bg, padx=14, pady=10)
        head.pack(fill=tk.X)
        tk.Label(head, text=title, bg=head_bg, fg=TEXT, font=("Helvetica", 13, "bold")).pack(anchor=tk.W)
        if subtitle:
            tk.Label(head, text=subtitle, bg=head_bg, fg=MUTED, font=("Helvetica", 10)).pack(anchor=tk.W, pady=(2, 0))
        body = tk.Frame(panel, bg=panel_bg, padx=14, pady=12)
        body.pack(fill=tk.BOTH, expand=True)
        return panel, head, body

    def metric_tile(self, parent, col: int, label: str, var: tk.StringVar):
        tile = tk.Frame(parent, bg=VALUE_BG, highlightthickness=1, highlightbackground=LINE, padx=10, pady=10)
        tile.grid(row=0, column=col, sticky=tk.NSEW, padx=(0 if col == 0 else 8, 0))
        tk.Label(tile, text=label, bg=VALUE_BG, fg=MUTED, font=("Helvetica", 9)).pack(anchor=tk.W)
        tk.Label(tile, textvariable=var, bg=VALUE_BG, fg=TEXT, font=("Helvetica", 13, "bold")).pack(anchor=tk.W, pady=(6, 0))

    def _refresh_mode_value_labels(self):
        self.jog_display_var.set(f"{self.jog_ms_var.get()} ms")
        self.pulse_display_var.set(f"{self.pulse_hz_var.get()} Hz")

    def _build_ui(self):
        header = tk.Frame(self.root, bg=BG, padx=18, pady=14)
        header.pack(fill=tk.X)
        title_wrap = tk.Frame(header, bg=BG)
        title_wrap.pack(side=tk.LEFT)
        tk.Label(title_wrap, text="PTZ Pegasus Console", bg=BG, fg=TEXT, font=("Helvetica", 23, "bold")).pack(anchor=tk.W)
        tk.Label(title_wrap, text="Connection, grouped jog operations, dual-axis tuning, and protocol telemetry", bg=BG, fg=MUTED, font=("Helvetica", 11)).pack(anchor=tk.W, pady=(2, 0))

        self.link_badge = tk.Button(
            header,
            textvariable=self.link_var,
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=8,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 11, "bold"),
            cursor="arrow",
        )
        self.link_badge.pack(side=tk.RIGHT)

        board = tk.Frame(self.root, bg=BG, padx=18, pady=6)
        board.pack(fill=tk.BOTH, expand=True)
        board.grid_columnconfigure(1, weight=1)
        board.grid_rowconfigure(0, weight=1)

        left = tk.Frame(board, bg=BG)
        left.grid(row=0, column=0, sticky=tk.NS, padx=(0, 16))
        center = tk.Frame(board, bg=BG)
        center.grid(row=0, column=1, sticky=tk.NSEW, padx=(0, 16))
        center.grid_columnconfigure(0, weight=1)
        right = tk.Frame(board, bg=BG)
        right.grid(row=0, column=2, sticky=tk.NSEW)
        right.grid_rowconfigure(2, weight=1)

        self._build_link_panel(left)
        self._build_motion_panel(left)
        self._build_system_panel(right)
        self._build_trend_panel(right)
        self._build_log_panel(right)

        self.cards["m1"] = MotorCard(self, center, "m1")
        self.cards["m2"] = MotorCard(self, center, "m2")

    def _build_link_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Connection Deck", "USB VCP discovery, baud selection, and firmware handshake")
        panel.pack(fill=tk.X, pady=(0, 16))
        body.grid_columnconfigure(1, weight=1)

        tk.Label(body, text="Port", bg=PANEL, fg=TEXT, font=("Helvetica", 11)).grid(row=0, column=0, sticky=tk.W, pady=4)
        self.port_menu = tk.OptionMenu(body, self.port_var, "")
        self._style_menu(self.port_menu, 22)
        self.port_menu.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(body, text="Baud", bg=PANEL, fg=TEXT, font=("Helvetica", 11)).grid(row=1, column=0, sticky=tk.W, pady=4)
        baud_menu = tk.OptionMenu(body, self.baud_var, "115200", "57600", "38400", "9600")
        self._style_menu(baud_menu, 22)
        baud_menu.grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=4)

        btns = tk.Frame(body, bg=PANEL)
        btns.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(10, 8))
        self.button(btns, "Refresh", self.refresh_ports, width=8).pack(side=tk.LEFT)
        self.button(btns, "Connect", self.connect, width=8, bg=BTN_GO, fg="#ffffff").pack(side=tk.LEFT, padx=8)
        self.button(btns, "Disconnect", self.disconnect, width=10, bg=BTN_STOP, fg="#ffffff").pack(side=tk.LEFT)

        self.build_badge = tk.Button(
            body,
            textvariable=self.build_var,
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
            wraplength=290,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="arrow",
        )
        self.build_badge.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(2, 0))

    def _build_motion_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Motion Deck", "Pegasus-style grouped motion workflow: select axes, set mode, then jog or run")
        panel.pack(fill=tk.BOTH, expand=True)

        modes = tk.Frame(body, bg=PANEL)
        modes.pack(fill=tk.X)
        tk.Radiobutton(modes, text="Continuous", variable=self.mode_var, value="continuous", bg=PANEL, fg=TEXT, selectcolor=VALUE_BG, activebackground=PANEL, font=("Helvetica", 11)).grid(row=0, column=0, sticky=tk.W, pady=4)
        tk.Radiobutton(modes, text="Jog", variable=self.mode_var, value="jog", bg=PANEL, fg=TEXT, selectcolor=VALUE_BG, activebackground=PANEL, font=("Helvetica", 11)).grid(row=1, column=0, sticky=tk.W, pady=4)
        tk.Radiobutton(modes, text="Pulse Repeat", variable=self.mode_var, value="pulse_repeat", bg=PANEL, fg=TEXT, selectcolor=VALUE_BG, activebackground=PANEL, font=("Helvetica", 11)).grid(row=2, column=0, sticky=tk.W, pady=4)

        hint = tk.Button(
            body,
            textvariable=self.mode_hint_var,
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
            wraplength=320,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 9, "bold"),
            cursor="arrow",
        )
        hint.pack(fill=tk.X, pady=(10, 8))

        jog_row = tk.Frame(body, bg=PANEL)
        jog_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(jog_row, text="Jog Time", bg=PANEL, fg=TEXT, font=("Helvetica", 11, "bold")).pack(side=tk.LEFT)
        self.button(jog_row, "-100", lambda: self.adjust_jog_ms(-100), width=6).pack(side=tk.LEFT, padx=(10, 6))
        self.button(jog_row, "-10", lambda: self.adjust_jog_ms(-10), width=5).pack(side=tk.LEFT, padx=(0, 6))
        self.value_button(jog_row, self.jog_display_var, lambda: self.prompt_mode_value("Jog time (ms)", self.jog_ms_var, 20, 60000, is_float=False), width=12).pack(side=tk.LEFT)
        self.button(jog_row, "+10", lambda: self.adjust_jog_ms(10), width=5).pack(side=tk.LEFT, padx=6)
        self.button(jog_row, "+100", lambda: self.adjust_jog_ms(100), width=6).pack(side=tk.LEFT)

        pulse_row = tk.Frame(body, bg=PANEL)
        pulse_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(pulse_row, text="Pulse Rate", bg=PANEL, fg=TEXT, font=("Helvetica", 11, "bold")).pack(side=tk.LEFT)
        self.button(pulse_row, "-0.5", lambda: self.adjust_pulse_hz(-0.5), width=6).pack(side=tk.LEFT, padx=(10, 6))
        self.button(pulse_row, "-0.1", lambda: self.adjust_pulse_hz(-0.1), width=6).pack(side=tk.LEFT, padx=(0, 6))
        self.value_button(pulse_row, self.pulse_display_var, lambda: self.prompt_mode_value("Pulse rate (Hz)", self.pulse_hz_var, 0.2, 10.0, is_float=True), width=12).pack(side=tk.LEFT)
        self.button(pulse_row, "+0.1", lambda: self.adjust_pulse_hz(0.1), width=6).pack(side=tk.LEFT, padx=6)
        self.button(pulse_row, "+0.5", lambda: self.adjust_pulse_hz(0.5), width=6).pack(side=tk.LEFT)

        self.group_badge = tk.Button(
            body,
            textvariable=self.group_var,
            bg=ACCENT,
            fg="#ffffff",
            activebackground=ACCENT,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=9,
            wraplength=320,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="arrow",
        )
        self.group_badge.pack(fill=tk.X, pady=(0, 10))

        group1 = tk.Frame(body, bg=PANEL)
        group1.pack(fill=tk.X, pady=(0, 8))
        self.button(group1, "Selected FWD", lambda: self.drive_selected("f"), width=15, bg=BTN_GO, fg="#ffffff").pack(side=tk.LEFT)
        self.button(group1, "Selected REV", lambda: self.drive_selected("r"), width=15, bg=ACCENT, fg="#ffffff").pack(side=tk.LEFT, padx=8)

        group2 = tk.Frame(body, bg=PANEL)
        group2.pack(fill=tk.X, pady=(0, 8))
        self.button(group2, "Stop Selected", self.stop_selected, width=15, bg=BTN_WARN).pack(side=tk.LEFT)
        self.button(group2, "ALL STOP", self.stop_all, width=15, bg=BTN_STOP, fg="#ffffff").pack(side=tk.LEFT, padx=8)

        note = tk.Button(
            body,
            text="Grouped actions apply the active mode. In Continuous they run until Stop. In Jog they send one firmware jog. In Pulse Repeat they schedule repeated jog pulses.",
            bg=ACCENT_SOFT,
            fg=TEXT,
            activebackground=ACCENT_SOFT,
            activeforeground=TEXT,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
            wraplength=320,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 9, "bold"),
            cursor="arrow",
        )
        note.pack(fill=tk.X)

    def _build_system_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Session Monitor", "Status, telemetry policy, and manual protocol control")
        panel.grid(row=0, column=0, sticky=tk.EW, pady=(0, 16))

        status_row = tk.Frame(body, bg=PANEL)
        status_row.pack(fill=tk.X, pady=(0, 8))
        self.button(status_row, "Read Status", lambda: self.send_line("status"), width=10).pack(side=tk.LEFT)
        self.button(status_row, "Read Version", lambda: self.send_line("version"), width=11).pack(side=tk.LEFT, padx=8)
        self.button(status_row, "Help", lambda: self.send_line("help"), width=8).pack(side=tk.LEFT)

        telem_row = tk.Frame(body, bg=PANEL)
        telem_row.pack(fill=tk.X, pady=(0, 8))
        self.button(telem_row, "Telemetry On", lambda: self.send_line("telemetry on"), width=12, bg=BTN_GO, fg="#ffffff").pack(side=tk.LEFT)
        self.button(telem_row, "Telemetry Off", lambda: self.send_line("telemetry off"), width=12).pack(side=tk.LEFT, padx=8)
        tk.Button(
            telem_row,
            textvariable=self.telemetry_var,
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="arrow",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.event_badge = tk.Button(
            body,
            textvariable=self.event_var,
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
            wraplength=330,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="arrow",
        )
        self.event_badge.pack(fill=tk.X, pady=(0, 8))

        tk.Label(body, text="Manual Command", bg=PANEL, fg=TEXT, font=("Helvetica", 11, "bold")).pack(anchor=tk.W)
        entry = self.entry(body, self.manual_var, width=30, justify=tk.LEFT)
        entry.pack(fill=tk.X, pady=(6, 8))
        entry.bind("<Return>", lambda _evt: self.send_manual())

        cmds = tk.Frame(body, bg=PANEL)
        cmds.pack(fill=tk.X)
        self.button(cmds, "Send", self.send_manual, width=8, bg=ACCENT_SOFT).pack(side=tk.LEFT)
        self.button(cmds, "M1 Diag", lambda: self.send_line("m1 diag"), width=9).pack(side=tk.LEFT, padx=8)
        self.button(cmds, "M2 Diag", lambda: self.send_line("m2 diag"), width=9).pack(side=tk.LEFT)

    def _build_trend_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Live Trend", "Recent rpm curves plus compact state/fault lanes for M1 and M2")
        panel.grid(row=1, column=0, sticky=tk.EW, pady=(0, 16))
        legend = tk.Frame(body, bg=PANEL)
        legend.pack(fill=tk.X, pady=(0, 8))
        tk.Label(legend, text="M1 rpm", bg=PANEL, fg=M1_TRACE, font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)
        tk.Label(legend, text="M2 rpm", bg=PANEL, fg=M2_TRACE, font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=14)
        tk.Label(legend, text="State/Fault lanes", bg=PANEL, fg=CHART_TEXT, font=("Helvetica", 10, "bold")).pack(side=tk.RIGHT)

        self.trend_canvas = tk.Canvas(
            body,
            width=420,
            height=220,
            bg=CHART_BG,
            highlightthickness=1,
            highlightbackground=LINE,
            bd=0,
        )
        self.trend_canvas.pack(fill=tk.X)
        self.trend_canvas.bind("<Configure>", lambda _evt: self._redraw_trend())

        trend_note = tk.Button(
            body,
            textvariable=self.trend_note_var,
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=7,
            wraplength=340,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 9, "bold"),
            cursor="arrow",
        )
        trend_note.pack(fill=tk.X, pady=(8, 0))

    def _build_log_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Protocol Log", "Structured replies, telemetry frames, and diagnostics")
        panel.grid(row=2, column=0, sticky=tk.NSEW)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self.button(body, "Clear Log", self.clear_log, width=10).grid(row=0, column=0, sticky=tk.E)
        wrap = tk.Frame(body, bg=LOG_BG, highlightthickness=1, highlightbackground=LINE)
        wrap.grid(row=1, column=0, sticky=tk.NSEW, pady=(8, 0))

        self.log = tk.Text(wrap, wrap=tk.WORD, bg=LOG_BG, fg=TEXT, insertbackground=TEXT, relief=tk.FLAT, bd=0, padx=12, pady=10, font=("Menlo", 10))
        scroll = tk.Scrollbar(wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _style_menu(self, menu: tk.OptionMenu, width: int):
        menu.config(width=width, bg=VALUE_BG, fg=TEXT, activebackground=VALUE_BG, activeforeground=TEXT, relief=tk.FLAT, bd=0, highlightthickness=1, highlightbackground=LINE, font=("Helvetica", 10))
        menu["menu"].config(bg=VALUE_BG, fg=TEXT, activebackground=ACCENT_SOFT, activeforeground=TEXT)

    def _on_mode_changed(self, *_args):
        if self.mode_var.get() != "pulse_repeat":
            self._cancel_all_pulse_jobs()
        self._update_mode_hint()

    def _update_mode_hint(self):
        mode = self.mode_var.get()
        if mode == "jog":
            self.mode_hint_var.set("Jog mode: each execute action sends one firmware-side jog with the configured jog time")
        elif mode == "pulse_repeat":
            self.mode_hint_var.set("Pulse Repeat mode: execute actions send recurring jog commands at the configured pulse rate")
        else:
            self.mode_hint_var.set("Continuous mode: selected axes keep rotating until Stop")

    def refresh_ports(self):
        ports = []
        for item in list_ports.comports():
            dev = item.device
            low = dev.lower()
            if "debug-console" in low or "bluetooth" in low:
                continue
            ports.append(dev)

        menu = self.port_menu["menu"]
        menu.delete(0, "end")
        if not ports:
            ports = [""]
        for dev in ports:
            menu.add_command(label=dev, command=tk._setit(self.port_var, dev))

        preferred = next((dev for dev in ports if "usbmodem" in dev.lower() or "usbserial" in dev.lower()), ports[0])
        self.port_var.set(preferred)

    def connect(self):
        if self.client.is_open():
            self.append_log("[INFO] already connected\n")
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("Port", "Please select serial port")
            return
        try:
            self.client.connect(port, int(self.baud_var.get()))
        except Exception as exc:
            messagebox.showerror("Connect failed", str(exc))
            return

        self.connect_seq += 1
        self.active_connect_seq = self.connect_seq
        self.link_var.set(f"Connected {port}")
        self.link_badge.configure(bg=OK_BG, activebackground=OK_BG)
        self.build_var.set("FW reading...")
        self.build_badge.configure(bg=INFO_BG, activebackground=INFO_BG)
        self.last_rx_monotonic = None
        self.last_stat_monotonic = None
        self.stats_frames = 0
        self.redraw_count = 0
        self.set_event("Connected. Querying firmware...", INFO_BG)
        self.append_log(f"[INFO] connected {port} @ {self.baud_var.get()}\n")
        self._write_runtime_log(f"CONNECT port={port} baud={self.baud_var.get()}")
        self.client.flush_input()
        if self.version_query_job is not None:
            try:
                self.root.after_cancel(self.version_query_job)
            except Exception:
                pass
            self.version_query_job = None
        self.version_query_job = self.root.after(250, lambda seq=self.active_connect_seq: self._query_firmware_version(seq))
        self.root.after(420, lambda seq=self.active_connect_seq: self._request_status(seq))

    def disconnect(self):
        self._cancel_all_pulse_jobs()
        if self.version_query_job is not None:
            try:
                self.root.after_cancel(self.version_query_job)
            except Exception:
                pass
            self.version_query_job = None
        self.client.disconnect()
        self.active_connect_seq = 0
        self.link_var.set("Disconnected")
        self.link_badge.configure(bg=INFO_BG, activebackground=INFO_BG)
        self.build_var.set("FW unknown")
        self.build_badge.configure(bg=INFO_BG, activebackground=INFO_BG)
        self._write_runtime_log("DISCONNECT")
        self.set_event("Disconnected", INFO_BG)
        self.append_log("[INFO] disconnected\n")

    def _write_runtime_log(self, message: str):
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as fp:
            fp.write(f"{stamp} {message}\n")

    def _runtime_banner(self) -> str:
        try:
            tcl = self.root.tk.call("info", "patchlevel")
            tk_patch = self.root.tk.call("set", "tk_patchLevel")
            ws = self.root.tk.call("tk", "windowingsystem")
        except Exception:
            tcl = "unknown"
            tk_patch = "unknown"
            ws = "unknown"
        return (
            f"ENV python={sys.version.split()[0]} exe={sys.executable} "
            f"platform={platform.platform()} tcl={tcl} tk={tk_patch} ws={ws}"
        )

    def _warn_if_legacy_tk(self):
        try:
            tk_patch = str(self.root.tk.call("set", "tk_patchLevel"))
            parts = tk_patch.split(".")
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            if (major, minor) < (8, 6):
                msg = f"Legacy Tk runtime detected ({tk_patch}); long-run stability is not guaranteed"
                self.set_event(msg, BTN_WARN)
                self.append_log(f"[WARN] {msg}\n")
                self._write_runtime_log("LEGACY_TK " + tk_patch)
        except Exception as exc:
            self._write_runtime_log("LEGACY_TK_CHECK_EXCEPTION " + repr(exc))

    def _report_callback_exception(self, exc, val, tb):
        message = f"Tk callback exception: {exc.__name__}: {val}"
        self.set_event(message, ERR_BG)
        self.append_log(f"[GUI-ERR] {message}\n")
        self._write_runtime_log("TK_CALLBACK_EXCEPTION " + message)
        self._write_runtime_log("".join(traceback.format_exception(exc, val, tb)).rstrip())

    @staticmethod
    def _safe_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _query_firmware_version(self, seq: int):
        if seq != self.active_connect_seq or not self.client.is_open():
            return
        self.client.flush_input()
        self.send_line("version")
        self.version_query_job = None

    def _request_status(self, seq: int):
        if seq != self.active_connect_seq or not self.client.is_open():
            return
        self.send_line("status")

    def selected_motors(self):
        return [key for key, card in self.cards.items() if card.selected_var.get()]

    def refresh_group_summary(self):
        selected = self.selected_motors()
        total = len(self.cards)
        for card in self.cards.values():
            card.refresh_group_visuals()
        if not selected:
            self.group_var.set("Grouped axes: none selected | grouped actions disabled")
            self.group_badge.configure(bg=ERR_BG, activebackground=ERR_BG)
            return
        labels = " + ".join(key.upper() for key in selected)
        if len(selected) == total:
            self.group_var.set(f"Grouped axes: {labels} | all axes armed")
            self.group_badge.configure(bg=SELECT_ON_BG, activebackground=SELECT_ON_BG)
        else:
            self.group_var.set(f"Grouped axes: {labels} | partial selection")
            self.group_badge.configure(bg=SELECT_PARTIAL_BG, activebackground=SELECT_PARTIAL_BG)

    def send_line(self, line: str):
        try:
            self.client.send_line(line)
            self.append_log(f"> {line}\n")
        except Exception as exc:
            self.append_log(f"[WARN] {exc}\n")

    def send_manual(self):
        cmd = self.manual_var.get().strip()
        if not cmd:
            return
        self.send_line(cmd)
        self.manual_var.set("")

    def drive_selected(self, direction: str):
        selected = self.selected_motors()
        if not selected:
            messagebox.showwarning("Grouped axes", "Select at least one motor card before executing grouped motion")
            return
        self.append_log(f"[GROUP] execute {direction.upper()} on {', '.join(m.upper() for m in selected)} using mode={self.mode_var.get()}\n")
        for motor_key in selected:
            self.drive_motor(motor_key, direction)

    def stop_selected(self):
        selected = self.selected_motors()
        if not selected:
            messagebox.showwarning("Grouped axes", "Select at least one motor card before stopping grouped motion")
            return
        self.append_log(f"[GROUP] stop {', '.join(m.upper() for m in selected)}\n")
        for motor_key in selected:
            self.stop_motor(motor_key)

    def stop_motor(self, motor_key: str):
        self._cancel_pulse_job(motor_key)
        self.append_log(f"[CTRL] {motor_key.upper()} STOP\n")
        self.send_line(f"{motor_key} stop")

    def stop_all(self):
        self._cancel_all_pulse_jobs()
        self.append_log("[CTRL] ALL STOP\n")
        self.send_line("all stop")

    def _driver_steps_rev(self, motor_key: str) -> int:
        tel = self.telemetry.get(motor_key)
        if tel and tel.steps_rev > 0:
            return tel.steps_rev
        driver = self.cards[motor_key].driver_var.get().strip().upper() or DEFAULT_DRIVER
        profile = DRIVER_PROFILES.get(driver, DRIVER_PROFILES[DEFAULT_DRIVER])
        return profile["steps_per_rev"]

    def rpm_to_hz(self, motor_key: str, rpm: int) -> int:
        hz = round(rpm * self._driver_steps_rev(motor_key) / 60)
        return max(10, min(50000, hz))

    def accel_rpmps_to_hzps(self, motor_key: str, rpmps: int) -> int:
        hzps = round(rpmps * self._driver_steps_rev(motor_key) / 60)
        return max(100, min(50000, hzps))

    def _parse_pulse_hz(self):
        try:
            pulse_hz = float(self.pulse_hz_var.get())
        except ValueError:
            pulse_hz = 1.0
        pulse_hz = max(0.2, min(10.0, pulse_hz))
        self.pulse_hz_var.set(f"{pulse_hz:.1f}")
        return pulse_hz

    def adjust_jog_ms(self, delta: int):
        try:
            value = int(self.jog_ms_var.get())
        except ValueError:
            value = 250
        value = max(20, min(60000, value + delta))
        self.jog_ms_var.set(str(value))

    def adjust_pulse_hz(self, delta: float):
        try:
            value = float(self.pulse_hz_var.get())
        except ValueError:
            value = 1.0
        value = max(0.2, min(10.0, value + delta))
        self.pulse_hz_var.set(f"{value:.1f}")

    def prompt_mode_value(self, title: str, var: tk.StringVar, min_v, max_v, is_float: bool):
        if is_float:
            try:
                current = float(var.get())
            except ValueError:
                current = float(min_v)
            value = simpledialog.askfloat(title, f"Input {title} ({min_v}-{max_v})", parent=self.root, initialvalue=current)
            if value is None:
                return
            value = max(float(min_v), min(float(max_v), float(value)))
            var.set(f"{value:.1f}")
            return

        try:
            current = int(var.get())
        except ValueError:
            current = int(min_v)
        value = simpledialog.askinteger(title, f"Input {title} ({min_v}-{max_v})", parent=self.root, initialvalue=current, minvalue=int(min_v), maxvalue=int(max_v))
        if value is None:
            return
        var.set(str(value))

    def _cancel_pulse_job(self, motor_key: str):
        job = self.pulse_job.get(motor_key)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.pulse_job[motor_key] = None
        self.pulse_active[motor_key] = False

    def _cancel_all_pulse_jobs(self):
        self._cancel_pulse_job("m1")
        self._cancel_pulse_job("m2")

    def _schedule_next_pulse(self, motor_key: str, speed_hz: int, jog_ms: int, period_ms: int):
        if not self.pulse_active[motor_key]:
            return
        direction = self.pulse_direction[motor_key]
        self.send_line(f"{motor_key} jog {direction} {speed_hz} {jog_ms}")
        self.pulse_job[motor_key] = self.root.after(period_ms, lambda m=motor_key, hz=speed_hz, ms=jog_ms, p=period_ms: self._schedule_next_pulse(m, hz, ms, p))

    def _start_pulse_job(self, motor_key: str, direction: str, speed_rpm: int, speed_hz: int):
        pulse_hz = self._parse_pulse_hz()
        period_ms = max(100, round(1000.0 / pulse_hz))
        try:
            jog_ms = int(self.jog_ms_var.get())
        except ValueError:
            jog_ms = 250
        jog_ms = max(20, min(period_ms - 20, jog_ms))
        self.jog_ms_var.set(str(jog_ms))

        self._cancel_pulse_job(motor_key)
        self.pulse_active[motor_key] = True
        self.pulse_direction[motor_key] = direction
        self.append_log(f"[CTRL] {motor_key.upper()} PULSE_REPEAT {direction.upper()} {speed_rpm}rpm {jog_ms}ms @ {pulse_hz:.1f}Hz ({period_ms}ms)\n")
        self._schedule_next_pulse(motor_key, speed_hz, jog_ms, period_ms)

    def apply_motor_cfg(self, motor_key: str):
        card = self.cards[motor_key]
        try:
            accel_rpmps = int(card.accel_var.get())
        except ValueError:
            accel_rpmps = DEFAULT_ACCEL_RPMPS
        accel_rpmps = max(ACCEL_MIN_RPMPS, min(ACCEL_MAX_RPMPS, accel_rpmps))
        card.accel_var.set(str(accel_rpmps))
        accel_hzps = self.accel_rpmps_to_hzps(motor_key, accel_rpmps)
        self.append_log(f"[CFG] {motor_key.upper()} accel {accel_rpmps}rpm/s -> {accel_hzps}Hz/s\n")
        self.send_line(f"{motor_key} cfg accel {accel_hzps}")

    def prompt_steps_rev(self, motor_key: str):
        card = self.cards[motor_key]
        self.prompt_mode_value("Steps/rev", card.steps_var, 200, 51200, is_float=False)
        try:
            steps_rev = int(card.steps_var.get())
        except ValueError:
            steps_rev = DRIVER_PROFILES[card.driver_var.get().strip().upper() or DEFAULT_DRIVER]["steps_per_rev"]
        self.set_steps_rev(motor_key, steps_rev)

    def set_steps_rev(self, motor_key: str, steps_rev: int):
        card = self.cards[motor_key]
        driver = card.driver_var.get().strip().upper() or DEFAULT_DRIVER
        steps_rev = max(200, min(51200, int(steps_rev)))
        card.steps_var.set(str(steps_rev))
        self.telemetry[motor_key].steps_rev = steps_rev
        self.cards[motor_key].update_from_telemetry(self.telemetry[motor_key])
        if driver == "A4988" and steps_rev in A4988_MICROSTEP_STEPS:
            microstep = steps_rev // 200
            self.append_log(f"[CFG] {motor_key.upper()} A4988 microstep {microstep}x -> {steps_rev} steps/rev\n")
            self.send_line(f"{motor_key} cfg microstep {microstep}")
        elif driver == "TMC2209" and steps_rev in TMC2209_MICROSTEP_STEPS:
            microstep = steps_rev // 200
            self.append_log(f"[CFG] {motor_key.upper()} TMC2209 microstep {microstep}x -> {steps_rev} steps/rev\n")
            self.send_line(f"{motor_key} cfg microstep {microstep}")
        else:
            self.append_log(f"[CFG] {motor_key.upper()} steps/rev {steps_rev}\n")
            self.send_line(f"{motor_key} cfg steps {steps_rev}")

    def prompt_wakeup_us(self, motor_key: str):
        card = self.cards[motor_key]
        self.prompt_mode_value("Wakeup delay (us)", card.wakeup_var, 0, 100000, is_float=False)
        try:
            wakeup_us = int(card.wakeup_var.get())
        except ValueError:
            wakeup_us = 0
        self.set_wakeup_us(motor_key, wakeup_us)

    def adjust_wakeup_us(self, motor_key: str, delta: int):
        card = self.cards[motor_key]
        try:
            value = int(card.wakeup_var.get())
        except ValueError:
            value = 0
        self.set_wakeup_us(motor_key, value + delta)

    def set_wakeup_us(self, motor_key: str, wakeup_us: int):
        wakeup_us = max(0, min(100000, int(wakeup_us)))
        self.cards[motor_key].wakeup_var.set(str(wakeup_us))
        self.telemetry[motor_key].wakeup_us = wakeup_us
        self.cards[motor_key].update_from_telemetry(self.telemetry[motor_key])
        self.append_log(f"[CFG] {motor_key.upper()} wakeup {wakeup_us}us\n")
        self.send_line(f"{motor_key} cfg wakeup {wakeup_us}")

    def set_driver(self, motor_key: str, driver_name: str):
        driver_name = driver_name.strip().upper()
        if driver_name not in DRIVER_PROFILES:
            return
        self._cancel_pulse_job(motor_key)
        self.cards[motor_key].driver_var.set(driver_name)
        self.telemetry[motor_key].driver = driver_name
        self.telemetry[motor_key].steps_rev = DRIVER_PROFILES[driver_name]["steps_per_rev"]
        self.telemetry[motor_key].wakeup_us = DRIVER_PROFILES[driver_name]["wakeup_us"]
        self.cards[motor_key].update_from_telemetry(self.telemetry[motor_key])
        self.append_log(f"[CFG] {motor_key.upper()} driver {driver_name}\n")
        self.send_line(f"{motor_key} cfg driver {driver_name.lower()}")

    def drive_motor(self, motor_key: str, direction: str):
        card = self.cards[motor_key]
        try:
            speed_rpm = int(card.speed_var.get())
        except ValueError:
            speed_rpm = DEFAULT_SPEED_RPM
        speed_rpm = max(SPEED_MIN_RPM, min(SPEED_MAX_RPM, speed_rpm))
        card.speed_var.set(str(speed_rpm))
        speed_hz = self.rpm_to_hz(motor_key, speed_rpm)
        self.apply_motor_cfg(motor_key)

        if self.mode_var.get() == "jog":
            self._cancel_pulse_job(motor_key)
            try:
                jog_ms = int(self.jog_ms_var.get())
            except ValueError:
                jog_ms = 250
            jog_ms = max(20, min(60000, jog_ms))
            self.jog_ms_var.set(str(jog_ms))
            self.append_log(f"[CTRL] {motor_key.upper()} JOG {direction.upper()} {speed_rpm}rpm {jog_ms}ms\n")
            self.send_line(f"{motor_key} jog {direction} {speed_hz} {jog_ms}")
        elif self.mode_var.get() == "pulse_repeat":
            self._start_pulse_job(motor_key, direction, speed_rpm, speed_hz)
        else:
            self._cancel_pulse_job(motor_key)
            self.append_log(f"[CTRL] {motor_key.upper()} RUN {direction.upper()} {speed_rpm}rpm\n")
            self.send_line(f"{motor_key} {direction} {speed_hz}")

    def pin_test(self, motor_key: str, pin: str, level: str):
        self._cancel_pulse_job(motor_key)
        self.append_log(f"[TEST] {motor_key.upper()} {pin.upper()} {level.upper()}\n")
        self.send_line(f"{motor_key} pin {pin} {level}")

    def pin_restore(self, motor_key: str):
        self._cancel_pulse_job(motor_key)
        self.append_log(f"[TEST] {motor_key.upper()} pin restore\n")
        self.send_line(f"{motor_key} pin restore")

    def clear_log(self):
        self.log.delete("1.0", tk.END)
        self.log_line_count = 0

    def append_log(self, text: str):
        self.log.insert(tk.END, text)
        self.log_line_count += max(1, text.count("\n"))
        if self.log_line_count > LOG_MAX_LINES:
            trim_to = max(1, LOG_TRIM_TO_LINES)
            self.log.delete("1.0", f"{self.log_line_count - trim_to + 1}.0")
            self.log_line_count = trim_to
        self.log.see(tk.END)

    def set_event(self, text: str, bg: str):
        self.event_var.set(text)
        self.event_badge.configure(bg=bg, activebackground=bg)

    def _poll_queue(self):
        processed = 0
        more_pending = False
        try:
            while processed < QUEUE_POLL_BATCH:
                line = self.client.queue.get_nowait()
                self.last_rx_monotonic = time.monotonic()
                if not line.startswith("STAT "):
                    self.append_log(line + "\n")
                try:
                    self._handle_line(line)
                except Exception as exc:
                    self.append_log(f"[GUI-ERR] line handling failed: {exc}\n")
                    self.set_event(f"GUI parse error: {exc}", ERR_BG)
                    self._write_runtime_log("HANDLE_LINE_EXCEPTION " + repr(exc))
                    self._write_runtime_log(traceback.format_exc().rstrip())
                processed += 1
            more_pending = True
        except queue.Empty:
            pass
        finally:
            self.root.after(10 if more_pending else 80, self._poll_queue)

    def _handle_line(self, line: str):
        if line.startswith("BUILD "):
            data = self._parse_kv_tokens(line)
            fw = data.get("fw", "fw")
            tm = data.get("time", "?")
            self.build_var.set(f"FW {fw} | {tm}")
            self.build_badge.configure(bg=ACCENT, activebackground=ACCENT)
            return
        if line.startswith("STAT "):
            self.last_stat_monotonic = time.monotonic()
            self.stats_frames += 1
            data = self._parse_kv_tokens(line)
            self._update_from_status(data)
            return
        if line.startswith("OK "):
            self.set_event(line, OK_BG)
            return
        if line.startswith("ERR "):
            self.set_event(line, ERR_BG)
            return
        if line.startswith("DIAG "):
            self.set_event(line, BTN_WARN)
            return
        if line.startswith("READY "):
            self.set_event(line, INFO_BG)
            return
        if line.startswith("BUILD:"):
            self.build_var.set(line)
            self.build_badge.configure(bg=ACCENT, activebackground=ACCENT)

    def _update_from_status(self, data):
        self.telemetry_var.set(f"telemetry={'on' if data.get('telemetry', '1') == '1' else 'off'}")
        for motor_key in ("m1", "m2"):
            tel = self.telemetry[motor_key]
            tel.driver = data.get(f"{motor_key}_drv", tel.driver)
            tel.steps_rev = self._safe_int(data.get(f"{motor_key}_steps_rev"), tel.steps_rev)
            tel.wakeup_us = self._safe_int(data.get(f"{motor_key}_wakeup_us"), tel.wakeup_us)
            tel.state = data.get(f"{motor_key}_state", tel.state)
            tel.dir = data.get(f"{motor_key}_dir", tel.dir)
            tel.target_hz = self._safe_int(data.get(f"{motor_key}_target_hz"), tel.target_hz)
            tel.actual_hz = self._safe_int(data.get(f"{motor_key}_actual_hz"), tel.actual_hz)
            tel.rpm = self._safe_int(data.get(f"{motor_key}_rpm"), tel.rpm)
            tel.zero = self._safe_int(data.get(f"{motor_key}_zero"), tel.zero)
            tel.edges = self._safe_int(data.get(f"{motor_key}_edges"), tel.edges)
            tel.accel_hzps = self._safe_int(data.get(f"{motor_key}_accel_hzps"), tel.accel_hzps)
            tel.fault = data.get(f"{motor_key}_fault", tel.fault)
            tel.override = self._safe_int(data.get(f"{motor_key}_override"), tel.override)
            self.cards[motor_key].update_from_telemetry(tel)
        self._append_trend_snapshot()
        self._redraw_trend()

    def _append_trend_snapshot(self):
        self.trend_history.append(
            {
                "m1_rpm": self.telemetry["m1"].rpm,
                "m2_rpm": self.telemetry["m2"].rpm,
                "m1_state": self.telemetry["m1"].state,
                "m2_state": self.telemetry["m2"].state,
                "m1_fault": self.telemetry["m1"].fault,
                "m2_fault": self.telemetry["m2"].fault,
            }
        )

    def _state_color(self, state: str, axis: str):
        if state == "RUN":
            return M1_TRACE if axis == "m1" else M2_TRACE
        if state.startswith("RAMP"):
            return BTN_WARN
        if state == "PIN_TEST":
            return ACCENT
        if state == "FAULT":
            return ERR_BG
        return "#c7cfca"

    def _draw_lane(self, x0, x1, y0, y1, state: str, fault: str, axis: str):
        state_color = self._state_color(state, axis)
        self.trend_canvas.create_rectangle(x0, y0, x1, y1, fill=state_color, outline="")
        if fault != "NONE":
            self.trend_canvas.create_rectangle(x0, y1 - 5, x1, y1, fill=ERR_BG, outline="")

    def _redraw_trend(self):
        if self.trend_canvas is None:
            return
        self.redraw_count += 1
        width = max(420, self.trend_canvas.winfo_width())
        height = max(220, self.trend_canvas.winfo_height())
        self.trend_canvas.delete("all")
        self.trend_canvas.create_rectangle(0, 0, width, height, fill=CHART_BG, outline="")

        left = 42
        right = width - 10
        top = 12
        rpm_bottom = 126
        lane1_top = 146
        lane1_bottom = 170
        lane2_top = 180
        lane2_bottom = 204

        max_rpm = max(
            60,
            max((item["m1_rpm"] for item in self.trend_history), default=0),
            max((item["m2_rpm"] for item in self.trend_history), default=0),
        )
        max_rpm = int(((max_rpm + 29) // 30) * 30)

        for step in range(4):
            y = top + (rpm_bottom - top) * step / 3
            self.trend_canvas.create_line(left, y, right, y, fill=CHART_GRID)
            label_value = max_rpm - (max_rpm * step // 3)
            self.trend_canvas.create_text(left - 8, y, text=str(label_value), fill=CHART_TEXT, anchor="e", font=("Helvetica", 8))

        self.trend_canvas.create_text(left, top - 6, text="rpm", fill=CHART_TEXT, anchor="w", font=("Helvetica", 8, "bold"))
        self.trend_canvas.create_text(left, lane1_top - 8, text="M1 state/fault", fill=CHART_TEXT, anchor="w", font=("Helvetica", 8, "bold"))
        self.trend_canvas.create_text(left, lane2_top - 8, text="M2 state/fault", fill=CHART_TEXT, anchor="w", font=("Helvetica", 8, "bold"))

        history = list(self.trend_history)
        if not history:
            self.trend_canvas.create_text(width / 2, height / 2, text="Waiting for STAT telemetry...", fill=CHART_TEXT, font=("Helvetica", 11, "bold"))
            return

        plot_width = max(1, right - left)
        count = len(history)
        step_x = plot_width / max(1, count - 1) if count > 1 else plot_width
        lane_w = max(2, plot_width / max(1, count))
        m1_points = []
        m2_points = []

        def rpm_to_y(rpm: int):
            return rpm_bottom - (min(max_rpm, rpm) / max_rpm) * (rpm_bottom - top)

        for idx, item in enumerate(history):
            x = left + idx * step_x
            x0 = left + idx * lane_w
            x1 = min(right, x0 + lane_w + 1)
            self._draw_lane(x0, x1, lane1_top, lane1_bottom, item["m1_state"], item["m1_fault"], "m1")
            self._draw_lane(x0, x1, lane2_top, lane2_bottom, item["m2_state"], item["m2_fault"], "m2")
            m1_points.extend((x, rpm_to_y(item["m1_rpm"])))
            m2_points.extend((x, rpm_to_y(item["m2_rpm"])))

        if len(m1_points) >= 4:
            self.trend_canvas.create_line(*m1_points, fill=M1_TRACE, width=2, smooth=True)
        if len(m2_points) >= 4:
            self.trend_canvas.create_line(*m2_points, fill=M2_TRACE, width=2, smooth=True)

        m1 = self.telemetry["m1"]
        m2 = self.telemetry["m2"]
        self.trend_note_var.set(
            f"M1 {m1.state} {m1.rpm}rpm fault={m1.fault} | "
            f"M2 {m2.state} {m2.rpm}rpm fault={m2.fault}"
        )

    def _health_tick(self):
        try:
            now = time.monotonic()
            qsize = self.client.queue.qsize()
            rx_idle_ms = -1 if self.last_rx_monotonic is None else int((now - self.last_rx_monotonic) * 1000)
            stat_idle_ms = -1 if self.last_stat_monotonic is None else int((now - self.last_stat_monotonic) * 1000)
            self._write_runtime_log(
                f"HEALTH connected={int(self.client.is_open())} queue={qsize} "
                f"log_lines={self.log_line_count} stat_frames={self.stats_frames} redraws={self.redraw_count} "
                f"rx_idle_ms={rx_idle_ms} stat_idle_ms={stat_idle_ms}"
            )
            if self.client.is_open() and self.last_stat_monotonic is not None and stat_idle_ms > SERIAL_IDLE_WARN_MS:
                msg = f"Telemetry stalled: last STAT {stat_idle_ms}ms ago"
                self.set_event(msg, BTN_WARN)
                self.append_log(f"[WARN] {msg}\n")
        except Exception as exc:
            self._write_runtime_log("HEALTH_EXCEPTION " + repr(exc))
            self._write_runtime_log(traceback.format_exc().rstrip())
        finally:
            self.health_job = self.root.after(HEALTH_LOG_INTERVAL_MS, self._health_tick)

    def _parse_kv_tokens(self, line: str):
        result = {}
        for token in line.split()[1:]:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            result[key] = value
        return result

    def on_close(self):
        self._cancel_all_pulse_jobs()
        if self.health_job is not None:
            try:
                self.root.after_cancel(self.health_job)
            except Exception:
                pass
        self.client.disconnect()
        self._write_runtime_log("=== GUI STOP ===")
        self.root.destroy()


def main():
    root = tk.Tk()
    PTZGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
