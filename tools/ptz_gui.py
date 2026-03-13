#!/usr/bin/env python3
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, simpledialog

import serial
from serial.tools import list_ports


DRIVER_PROFILES = {
    "GC6609": {"steps_per_rev": 1600},
    "DM556": {"steps_per_rev": 1600},
}
DEFAULT_DRIVER = "GC6609"
SPEED_MIN_RPM = 1
SPEED_MAX_RPM = 1875
ACCEL_MIN_RPMPS = 4
ACCEL_MAX_RPMPS = 1875
DEFAULT_SPEED_RPM = 10
DEFAULT_ACCEL_RPMPS = 60

BG = "#ebe6dc"
PANEL = "#f7f3eb"
PANEL_ALT = "#efe7da"
TEXT = "#2f2a24"
MUTED = "#786e62"
ACCENT = "#c55a3f"
ACCENT_SOFT = "#ead6c9"
BTN = "#d8cfbf"
BTN_ACTIVE = "#c8bba8"
BTN_GO = "#93a66e"
BTN_WARN = "#d5a056"
BTN_STOP = "#c86f63"
VALUE_BG = "#fffdf8"
LINE = "#d6cab8"
M1_PANEL = "#fff1ed"
M1_HEAD = "#f6d5cb"
M1_LINE = "#d07a60"
M2_PANEL = "#eef8f1"
M2_HEAD = "#d5eadc"
M2_LINE = "#6f9d7e"
OK_BG = "#9ab07b"
ERR_BG = "#bf6c62"
INFO_BG = "#b8ad9f"

MOTOR_STYLE = {
    "m1": {"title": "M1 / PAN", "panel": M1_PANEL, "head": M1_HEAD, "line": M1_LINE, "tag": "TIM1 PA8 STEP | PA0 DIR | PA1 EN"},
    "m2": {"title": "M2 / TILT", "panel": M2_PANEL, "head": M2_HEAD, "line": M2_LINE, "tag": "TIM3 PB4 STEP | PB0 DIR | PB1 EN"},
}


@dataclass
class MotorTelemetry:
    driver: str = DEFAULT_DRIVER
    steps_rev: int = DRIVER_PROFILES[DEFAULT_DRIVER]["steps_per_rev"]
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
        self.speed_var = tk.StringVar(value=str(DEFAULT_SPEED_RPM))
        self.accel_var = tk.StringVar(value=str(DEFAULT_ACCEL_RPMPS))
        self.driver_var = tk.StringVar(value=DEFAULT_DRIVER)
        self.badge_var = tk.StringVar(value=f"{style['title']} IDLE")
        self.target_var = tk.StringVar(value="0 rpm")
        self.actual_var = tk.StringVar(value="0 rpm")
        self.state_var = tk.StringVar(value="IDLE")
        self.dir_var = tk.StringVar(value="STOP")
        self.zero_var = tk.StringVar(value="0")
        self.fault_var = tk.StringVar(value="NONE")
        self.override_var = tk.StringVar(value="0")
        self.accel_status_var = tk.StringVar(value=f"{DEFAULT_ACCEL_RPMPS} rpm/s")

        self.panel, _head, body = app.create_panel(parent, style["title"], style["tag"], style["panel"], style["head"], style["line"])
        self.panel.pack(fill=tk.X, pady=(0, 14))

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
            pady=9,
            highlightthickness=1,
            highlightbackground=style["line"],
            font=("Helvetica", 11, "bold"),
            cursor="arrow",
        )
        self.badge.pack(fill=tk.X)

        cfg = tk.Frame(body, bg=style["panel"])
        cfg.pack(fill=tk.X, pady=(12, 10))
        self._build_driver_row(cfg, style["panel"])
        self._build_speed_row(cfg, style["panel"])
        self._build_accel_row(cfg, style["panel"])

        metrics = tk.Frame(body, bg=style["panel"])
        metrics.pack(fill=tk.X, pady=(0, 10))
        for col in range(4):
            metrics.grid_columnconfigure(col, weight=1)
        app.metric_tile(metrics, 0, "State", self.state_var)
        app.metric_tile(metrics, 1, "Dir", self.dir_var)
        app.metric_tile(metrics, 2, "Target", self.target_var)
        app.metric_tile(metrics, 3, "Actual", self.actual_var)

        metrics2 = tk.Frame(body, bg=style["panel"])
        metrics2.pack(fill=tk.X, pady=(0, 10))
        for col in range(4):
            metrics2.grid_columnconfigure(col, weight=1)
        app.metric_tile(metrics2, 0, "0-bit", self.zero_var)
        app.metric_tile(metrics2, 1, "Fault", self.fault_var)
        app.metric_tile(metrics2, 2, "Pin Override", self.override_var)
        app.metric_tile(metrics2, 3, "Accel", self.accel_status_var)

        ctrl = tk.Frame(body, bg=style["panel"])
        ctrl.pack(fill=tk.X, pady=(0, 10))
        app.button(ctrl, f"{motor_key.upper()} Forward", lambda: app.drive_motor(motor_key, "f"), width=13, bg=BTN_GO, fg="#ffffff").pack(side=tk.LEFT)
        app.button(ctrl, f"{motor_key.upper()} Reverse", lambda: app.drive_motor(motor_key, "r"), width=13, bg=ACCENT, fg="#ffffff").pack(side=tk.LEFT, padx=8)
        app.button(ctrl, f"{motor_key.upper()} Stop", lambda: app.stop_motor(motor_key), width=11, bg=BTN_STOP, fg="#ffffff").pack(side=tk.LEFT)
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
        self.root.title("PTZ Dual Motor Console")
        self.root.geometry("1480x920")
        self.root.minsize(1260, 820)
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
        self.cards = {}
        self.telemetry = {"m1": MotorTelemetry(), "m2": MotorTelemetry()}
        self.pulse_job = {"m1": None, "m2": None}
        self.pulse_active = {"m1": False, "m2": False}
        self.pulse_direction = {"m1": "f", "m2": "f"}
        self.port_menu = None
        self.build_badge = None
        self.link_badge = None
        self.event_badge = None
        self.log = None

        self.jog_ms_var.trace_add("write", lambda *_args: self._refresh_mode_value_labels())
        self.pulse_hz_var.trace_add("write", lambda *_args: self._refresh_mode_value_labels())
        self._build_ui()
        self.mode_var.trace_add("write", self._on_mode_changed)
        self.refresh_ports()
        self.root.after(80, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._refresh_mode_value_labels()

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
        tk.Label(header, text="PTZ Dual Motor Console", bg=BG, fg=TEXT, font=("Helvetica", 22, "bold")).pack(side=tk.LEFT)
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

        main = tk.Frame(self.root, bg=BG, padx=18, pady=8)
        main.pack(fill=tk.BOTH, expand=True)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky=tk.NS, padx=(0, 14))
        center = tk.Frame(main, bg=BG)
        center.grid(row=0, column=1, sticky=tk.NSEW, padx=(0, 14))
        center.grid_columnconfigure(0, weight=1)
        right = tk.Frame(main, bg=BG)
        right.grid(row=0, column=2, sticky=tk.NSEW)
        right.grid_rowconfigure(1, weight=1)

        self._build_link_panel(left)
        self._build_mode_panel(left)
        self._build_system_panel(left)
        self._build_log_panel(right)

        self.cards["m1"] = MotorCard(self, center, "m1")
        self.cards["m2"] = MotorCard(self, center, "m2")

    def _build_link_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Communication", "USB VCP and firmware handshake")
        panel.pack(fill=tk.X, pady=(0, 14))
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
            wraplength=280,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="arrow",
        )
        self.build_badge.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(2, 0))

    def _build_mode_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Run Mode", "Continuous, single jog, or repeated jog with adjustable frequency")
        panel.pack(fill=tk.X, pady=(0, 14))

        tk.Radiobutton(body, text="Continuous", variable=self.mode_var, value="continuous", bg=PANEL, fg=TEXT, selectcolor=VALUE_BG, activebackground=PANEL, font=("Helvetica", 11)).grid(row=0, column=0, sticky=tk.W, pady=4)
        tk.Radiobutton(body, text="Jog", variable=self.mode_var, value="jog", bg=PANEL, fg=TEXT, selectcolor=VALUE_BG, activebackground=PANEL, font=("Helvetica", 11)).grid(row=1, column=0, sticky=tk.W, pady=4)
        tk.Radiobutton(body, text="Pulse Repeat", variable=self.mode_var, value="pulse_repeat", bg=PANEL, fg=TEXT, selectcolor=VALUE_BG, activebackground=PANEL, font=("Helvetica", 11)).grid(row=2, column=0, sticky=tk.W, pady=4)
        jog_row = tk.Frame(body, bg=PANEL)
        jog_row.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=(10, 4))
        self.button(jog_row, "Jog -100", lambda: self.adjust_jog_ms(-100), width=8).pack(side=tk.LEFT)
        self.button(jog_row, "Jog -10", lambda: self.adjust_jog_ms(-10), width=7).pack(side=tk.LEFT, padx=6)
        self.value_button(jog_row, self.jog_display_var, lambda: self.prompt_mode_value("Jog time (ms)", self.jog_ms_var, 20, 60000, is_float=False), width=12).pack(side=tk.LEFT)
        self.button(jog_row, "Jog +10", lambda: self.adjust_jog_ms(10), width=7).pack(side=tk.LEFT, padx=6)
        self.button(jog_row, "Jog +100", lambda: self.adjust_jog_ms(100), width=8).pack(side=tk.LEFT)

        pulse_row = tk.Frame(body, bg=PANEL)
        pulse_row.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(4, 4))
        self.button(pulse_row, "Hz -0.5", lambda: self.adjust_pulse_hz(-0.5), width=8).pack(side=tk.LEFT)
        self.button(pulse_row, "Hz -0.1", lambda: self.adjust_pulse_hz(-0.1), width=8).pack(side=tk.LEFT, padx=6)
        self.value_button(pulse_row, self.pulse_display_var, lambda: self.prompt_mode_value("Pulse rate (Hz)", self.pulse_hz_var, 0.2, 10.0, is_float=True), width=12).pack(side=tk.LEFT)
        self.button(pulse_row, "Hz +0.1", lambda: self.adjust_pulse_hz(0.1), width=8).pack(side=tk.LEFT, padx=6)
        self.button(pulse_row, "Hz +0.5", lambda: self.adjust_pulse_hz(0.5), width=8).pack(side=tk.LEFT)

        tk.Button(
            body,
            text="Pulse Repeat periodically sends jog commands at the selected frequency",
            bg=INFO_BG,
            fg="#ffffff",
            activebackground=INFO_BG,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
            wraplength=300,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 9, "bold"),
            cursor="arrow",
        ).grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(4, 0))
        self.button(body, "ALL STOP", self.stop_all, width=26, bg=BTN_STOP, fg="#ffffff").grid(row=6, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))

    def _build_system_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "System", "Status, telemetry and manual protocol")
        panel.pack(fill=tk.BOTH, expand=True)

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
            wraplength=300,
            justify=tk.LEFT,
            anchor=tk.W,
            highlightthickness=1,
            highlightbackground=LINE,
            font=("Helvetica", 10, "bold"),
            cursor="arrow",
        )
        self.event_badge.pack(fill=tk.X, pady=(0, 8))

        tk.Label(body, text="Manual Cmd", bg=PANEL, fg=TEXT, font=("Helvetica", 11, "bold")).pack(anchor=tk.W)
        entry = self.entry(body, self.manual_var, width=28, justify=tk.LEFT)
        entry.pack(fill=tk.X, pady=(6, 8))
        entry.bind("<Return>", lambda _evt: self.send_manual())

        cmds = tk.Frame(body, bg=PANEL)
        cmds.pack(fill=tk.X)
        self.button(cmds, "Send", self.send_manual, width=8, bg=ACCENT_SOFT).pack(side=tk.LEFT)
        self.button(cmds, "M1 Diag", lambda: self.send_line("m1 diag"), width=9).pack(side=tk.LEFT, padx=8)
        self.button(cmds, "M2 Diag", lambda: self.send_line("m2 diag"), width=9).pack(side=tk.LEFT)

    def _build_log_panel(self, parent):
        panel, _head, body = self.create_panel(parent, "Protocol Log", "Structured replies, telemetry and diagnostics")
        panel.grid(row=0, column=0, sticky=tk.NSEW)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self.button(body, "Clear Log", self.clear_log, width=10).grid(row=0, column=0, sticky=tk.E)
        wrap = tk.Frame(body, bg=VALUE_BG, highlightthickness=1, highlightbackground=LINE)
        wrap.grid(row=1, column=0, sticky=tk.NSEW, pady=(8, 0))

        self.log = tk.Text(wrap, wrap=tk.WORD, bg=VALUE_BG, fg=TEXT, insertbackground=TEXT, relief=tk.FLAT, bd=0, padx=12, pady=10, font=("Menlo", 10))
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

        self.link_var.set(f"Connected {port}")
        self.link_badge.configure(bg=OK_BG, activebackground=OK_BG)
        self.build_var.set("FW reading...")
        self.set_event("Connected. Querying firmware...", INFO_BG)
        self.append_log(f"[INFO] connected {port} @ {self.baud_var.get()}\n")
        self.root.after(100, lambda: self.send_line("version"))
        self.root.after(160, lambda: self.send_line("status"))

    def disconnect(self):
        self._cancel_all_pulse_jobs()
        self.client.disconnect()
        self.link_var.set("Disconnected")
        self.link_badge.configure(bg=INFO_BG, activebackground=INFO_BG)
        self.build_var.set("FW unknown")
        self.set_event("Disconnected", INFO_BG)
        self.append_log("[INFO] disconnected\n")

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
        self.pulse_job[motor_key] = self.root.after(
            period_ms, lambda m=motor_key, hz=speed_hz, ms=jog_ms, p=period_ms: self._schedule_next_pulse(m, hz, ms, p)
        )

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
        self.append_log(
            f"[CTRL] {motor_key.upper()} PULSE_REPEAT {direction.upper()} {speed_rpm}rpm {jog_ms}ms @ {pulse_hz:.1f}Hz ({period_ms}ms)\n"
        )
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

    def set_driver(self, motor_key: str, driver_name: str):
        driver_name = driver_name.strip().upper()
        if driver_name not in DRIVER_PROFILES:
            return
        self._cancel_pulse_job(motor_key)
        self.cards[motor_key].driver_var.set(driver_name)
        self.telemetry[motor_key].driver = driver_name
        self.telemetry[motor_key].steps_rev = DRIVER_PROFILES[driver_name]["steps_per_rev"]
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

    def append_log(self, text: str):
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def set_event(self, text: str, bg: str):
        self.event_var.set(text)
        self.event_badge.configure(bg=bg, activebackground=bg)

    def _poll_queue(self):
        try:
            while True:
                line = self.client.queue.get_nowait()
                self.append_log(line + "\n")
                self._handle_line(line)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _handle_line(self, line: str):
        if line.startswith("BUILD "):
            data = self._parse_kv_tokens(line)
            fw = data.get("fw", "fw")
            tm = data.get("time", "?")
            self.build_var.set(f"FW {fw} | {tm}")
            self.build_badge.configure(bg=ACCENT, activebackground=ACCENT)
            return
        if line.startswith("STAT "):
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
            tel.steps_rev = int(data.get(f"{motor_key}_steps_rev", tel.steps_rev))
            tel.state = data.get(f"{motor_key}_state", tel.state)
            tel.dir = data.get(f"{motor_key}_dir", tel.dir)
            tel.target_hz = int(data.get(f"{motor_key}_target_hz", tel.target_hz))
            tel.actual_hz = int(data.get(f"{motor_key}_actual_hz", tel.actual_hz))
            tel.rpm = int(data.get(f"{motor_key}_rpm", tel.rpm))
            tel.zero = int(data.get(f"{motor_key}_zero", tel.zero))
            tel.edges = int(data.get(f"{motor_key}_edges", tel.edges))
            tel.accel_hzps = int(data.get(f"{motor_key}_accel_hzps", tel.accel_hzps))
            tel.fault = data.get(f"{motor_key}_fault", tel.fault)
            tel.override = int(data.get(f"{motor_key}_override", tel.override))
            self.cards[motor_key].update_from_telemetry(tel)

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
        self.client.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    PTZGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
