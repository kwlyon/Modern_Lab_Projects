"""Tkinter and Matplotlib interface for Serial Plotter V3."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import queue
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import serial.tools.list_ports

from . import config
from .core import (
    AcquisitionController,
    Calibration,
    average_command,
    downsample_for_display,
)
from .export import export_xlsx
from .transport import SerialTransport, SimulatorTransport


class PlotNavigationToolbar(NavigationToolbar2Tk):
    """Matplotlib toolbar whose Home action resumes live plot autoscaling."""

    def __init__(self, *args, home_callback, **kwargs) -> None:
        self._home_callback = home_callback
        super().__init__(*args, **kwargs)

    def home(self, *args) -> None:
        del args
        self._home_callback()


class SerialPlotterV3App(tk.Tk):
    """General two-channel voltage strip recorder."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Serial Plotter V3")
        self.geometry("1180x760")
        self.minsize(900, 600)

        self._transport: SerialTransport | SimulatorTransport | None = None
        self._event_queue: queue.Queue[tuple[str, bytes | str]] = queue.Queue()
        self._handshake_timeout_id: str | None = None
        self._identity_probe_id: str | None = None
        self._hardware_banner_seen = False
        self._resume_after_protocol = False
        self._last_plotted_count = -1
        self._changing_plot_limits = False
        self._closing = False
        self._port_open = False
        self._requested_average_count: int | None = None
        self.average_applied_count: int | None = None

        self.autoscale_var = tk.BooleanVar(value=True)
        self.autorange_var = tk.BooleanVar(value=True)
        self.channel_a_enabled_var = tk.BooleanVar(value=True)
        self.channel_b_enabled_var = tk.BooleanVar(value=True)
        self.average_var = tk.StringVar(value=str(config.DEFAULT_AVERAGES))
        self.average_status_var = tk.StringVar(value="Arduino averaging: not connected")
        default_range = self._format_adc_range(config.DEFAULT_ADC_RANGE_VOLTS)
        self.range_a_var = tk.StringVar(value=default_range)
        self.range_b_var = tk.StringVar(value=default_range)
        self.controller = AcquisitionController(self._write, Calibration())

        self._build_ui()
        self._refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(config.UI_UPDATE_MS, self._process_events)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        controls = ttk.Frame(self, padding=(10, 10, 10, 4))
        controls.pack(fill=tk.X)
        self.connection_led = tk.Canvas(
            controls, width=18, height=18, highlightthickness=0
        )
        self.connection_led.grid(row=0, column=0, padx=(0, 7), pady=2)
        self._led = self.connection_led.create_oval(
            2, 2, 16, 16, fill="#777777", outline="#555555"
        )

        ttk.Label(controls, text="Arduino port:").grid(row=0, column=1, sticky="w")
        self.port_combo = ttk.Combobox(controls, width=26, state="readonly")
        self.port_combo.grid(row=0, column=2, padx=(5, 6))
        ttk.Button(controls, text="Refresh", command=self._refresh_ports).grid(
            row=0, column=3, padx=(0, 8)
        )
        self.connect_button = ttk.Button(
            controls, text="Connect", command=self._toggle_connection
        )
        self.connect_button.grid(row=0, column=4, padx=(0, 18))
        self.start_button = ttk.Button(
            controls,
            text="Start Acquisition",
            command=self._start_acquisition,
            state=tk.DISABLED,
        )
        self.start_button.grid(row=0, column=5, padx=(0, 6))
        self.stop_button = ttk.Button(
            controls,
            text="Stop Acquisition",
            command=self._stop_acquisition,
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=6, padx=(0, 18))
        self.clear_button = ttk.Button(
            controls, text="Clear Data", command=self._clear_data
        )
        self.clear_button.grid(row=0, column=7, padx=(0, 6))
        self.export_button = ttk.Button(
            controls, text="Export Data", command=self._export_data
        )
        self.export_button.grid(row=0, column=8)
        controls.columnconfigure(9, weight=1)

        ttk.Label(controls, text="Display:").grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        self.channel_a_checkbutton = ttk.Checkbutton(
            controls,
            text="Channel A",
            variable=self.channel_a_enabled_var,
            command=lambda: self._channel_selection_changed("A"),
        )
        self.channel_a_checkbutton.grid(
            row=1, column=2, sticky="w", padx=(5, 0), pady=(8, 0)
        )
        self.channel_b_checkbutton = ttk.Checkbutton(
            controls,
            text="Channel B",
            variable=self.channel_b_enabled_var,
            command=lambda: self._channel_selection_changed("B"),
        )
        self.channel_b_checkbutton.grid(
            row=1, column=3, sticky="w", pady=(8, 0)
        )
        self.autorange_checkbutton = ttk.Checkbutton(
            controls,
            text="ADC Autorange",
            variable=self.autorange_var,
            command=self._toggle_autorange,
            state=tk.DISABLED,
        )
        self.autorange_checkbutton.grid(
            row=1, column=4, sticky="w", padx=(0, 14), pady=(8, 0)
        )

        range_labels = tuple(
            self._format_adc_range(value) for value in config.ADC_RANGE_VOLTS
        )
        ttk.Label(controls, text="A range:").grid(
            row=1, column=5, sticky="e", pady=(8, 0)
        )
        self.range_a_combo = ttk.Combobox(
            controls,
            width=10,
            state=tk.DISABLED,
            textvariable=self.range_a_var,
            values=range_labels,
        )
        self.range_a_combo.grid(
            row=1, column=6, sticky="w", padx=(5, 12), pady=(8, 0)
        )
        ttk.Label(controls, text="B range:").grid(
            row=1, column=7, sticky="e", pady=(8, 0)
        )
        self.range_b_combo = ttk.Combobox(
            controls,
            width=10,
            state=tk.DISABLED,
            textvariable=self.range_b_var,
            values=range_labels,
        )
        self.range_b_combo.grid(
            row=1, column=8, sticky="w", pady=(8, 0)
        )
        self.range_a_combo.bind("<<ComboboxSelected>>", self._manual_range_changed)
        self.range_b_combo.bind("<<ComboboxSelected>>", self._manual_range_changed)

        ttk.Label(controls, text="Averages / point:").grid(
            row=2, column=1, sticky="w", pady=(8, 2)
        )
        self.average_combo = ttk.Combobox(
            controls,
            width=5,
            state="readonly",
            textvariable=self.average_var,
            values=tuple(
                str(count)
                for count in range(config.MIN_AVERAGES, config.MAX_AVERAGES + 1)
            ),
        )
        self.average_combo.grid(row=2, column=2, sticky="w", pady=(8, 2))
        self.average_combo.bind("<<ComboboxSelected>>", self._average_selection_changed)
        self.apply_average_button = ttk.Button(
            controls, text="Apply on Arduino", command=self._apply_average,
            state=tk.DISABLED,
        )
        self.apply_average_button.grid(row=2, column=3, sticky="w", pady=(8, 2))
        ttk.Label(controls, textvariable=self.average_status_var).grid(
            row=2, column=4, columnspan=5, sticky="w", pady=(8, 2)
        )

        status_frame = ttk.Frame(self, padding=(12, 2, 12, 4))
        status_frame.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = tk.Label(
            status_frame, textvariable=self.status_var, anchor="w", fg="#555555"
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.count_var = tk.StringVar(value="0 points")
        ttk.Label(status_frame, textvariable=self.count_var).pack(side=tk.RIGHT)

        calibration = self.controller.calibration
        ttk.Label(
            self,
            text=(
                f"Channel A correction: {calibration.channel_a_scale:g}×, "
                f"{calibration.channel_a_offset_v:+g} V    "
                f"Channel B correction: {calibration.channel_b_scale:g}×, "
                f"{calibration.channel_b_offset_v:+g} V"
            ),
            foreground="#555555",
        ).pack(anchor="w", padx=12, pady=(0, 2))
        ttk.Label(
            self,
            text="Hardware: differential J1 (AIN0−AIN1), J3 (AIN2−AIN3); "
            "flash Frank_Herz_DAQ.ino",
            foreground="#555555",
        ).pack(anchor="w", padx=12, pady=(0, 2))

        self.figure = Figure(figsize=(10.8, 6.2), dpi=100, constrained_layout=True)
        self.axes = self.figure.add_subplot(111)
        self.secondary_axes = self.axes.twinx()
        self.axes.set_title("Two-Channel Strip Recorder")
        self.axes.set_xlabel("Elapsed Time (s)")
        self.axes.grid(True, color="#d8d8d8", linewidth=0.8)
        self.axes.set_axisbelow(True)
        (self.channel_a_line,) = self.axes.plot(
            [], [], color="#145DA0", linewidth=1.35, label="Channel A"
        )
        (self.channel_b_left_line,) = self.axes.plot(
            [], [], color="#C43B3B", linewidth=1.35, label="Channel B"
        )
        (self.channel_b_right_line,) = self.secondary_axes.plot(
            [], [], color="#C43B3B", linewidth=1.35, label="Channel B"
        )
        self.axes.margins(x=0.05, y=0.08)
        self.secondary_axes.margins(y=0.08)

        plot_frame = ttk.Frame(self, padding=(10, 2, 10, 8))
        plot_frame.pack(fill=tk.BOTH, expand=True)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.navigation_frame = ttk.Frame(plot_frame)
        self.navigation_frame.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.toolbar = PlotNavigationToolbar(
            self.canvas,
            self.navigation_frame,
            pack_toolbar=False,
            home_callback=self._home_plot,
        )
        self.toolbar.update()
        self.autoscale_checkbutton = ttk.Checkbutton(
            self.navigation_frame,
            text="Auto-scale live",
            variable=self.autoscale_var,
            command=self._toggle_autoscale,
        )
        self.autoscale_checkbutton.pack(side=tk.RIGHT, padx=(10, 4))
        self.toolbar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.axes.callbacks.connect("xlim_changed", self._manual_limits_changed)
        self.axes.callbacks.connect("ylim_changed", self._manual_limits_changed)
        self.secondary_axes.callbacks.connect(
            "ylim_changed", self._manual_limits_changed
        )
        self._apply_channel_layout()

    def _channel_selection_changed(self, changed_channel: str) -> None:
        if not self.channel_a_enabled_var.get() and not self.channel_b_enabled_var.get():
            if changed_channel == "A":
                self.channel_a_enabled_var.set(True)
            else:
                self.channel_b_enabled_var.set(True)
            self._set_status("At least one display channel must remain selected.", "waiting")
        self._apply_channel_layout()
        self._last_plotted_count = -1
        self._redraw_plot(force=True)

    def _apply_channel_layout(self) -> None:
        channel_a = self.channel_a_enabled_var.get()
        channel_b = self.channel_b_enabled_var.get()
        both = channel_a and channel_b
        self._changing_plot_limits = True
        try:
            self.channel_a_line.set_visible(channel_a)
            self.channel_b_left_line.set_visible(channel_b and not channel_a)
            self.channel_b_right_line.set_visible(both)
            self.secondary_axes.set_visible(both)
            if channel_a:
                self.axes.set_ylabel("Channel A Voltage (V)", color="#145DA0")
                self.axes.tick_params(axis="y", colors="#145DA0")
            else:
                self.axes.set_ylabel("Channel B Voltage (V)", color="#C43B3B")
                self.axes.tick_params(axis="y", colors="#C43B3B")
            if both:
                self.secondary_axes.set_ylabel("Channel B Voltage (V)", color="#C43B3B")
                self.secondary_axes.tick_params(axis="y", colors="#C43B3B")
        finally:
            self._changing_plot_limits = False

    def _refresh_ports(self) -> None:
        previous = self.port_combo.get()
        ports = [port.device for port in serial.tools.list_ports.comports()]
        values = ports + [config.SIMULATOR_PORT]
        self.port_combo.configure(values=values)
        if previous in values:
            self.port_combo.set(previous)
        elif ports:
            self.port_combo.set(ports[0])
        else:
            self.port_combo.set(config.SIMULATOR_PORT)

    def _toggle_connection(self) -> None:
        if self._port_open:
            self._disconnect("Disconnected")
        else:
            self._connect()

    def _connect(self) -> None:
        selected = self.port_combo.get().strip()
        if not selected:
            messagebox.showerror("No port selected", "Select an Arduino serial port.")
            return
        transport_class = (
            SimulatorTransport if selected == config.SIMULATOR_PORT else SerialTransport
        )
        transport = transport_class(
            on_line=lambda line: self._event_queue.put(("line", line)),
            on_error=lambda error: self._event_queue.put(("error", error)),
        )
        try:
            transport.open(selected, config.BAUD_RATE)
        except (ConnectionError, OSError) as exc:
            messagebox.showerror("Connection failed", str(exc))
            self._set_status(f"Connection failed: {exc}", "error")
            return
        self._transport = transport
        self._port_open = True
        self.controller.disconnect()
        self._requested_average_count = None
        self.average_applied_count = None
        self.average_status_var.set("Arduino averaging: waiting for connection")
        self._hardware_banner_seen = False
        self._resume_after_protocol = False
        self.connect_button.configure(text="Disconnect")
        self.port_combo.configure(state=tk.DISABLED)
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)
        self.apply_average_button.configure(state=tk.DISABLED)
        self._update_adc_control_states()
        self._set_led("waiting")
        self._set_status(
            f"Port open at {config.BAUD_RATE:,} baud; waiting for device handshake…",
            "waiting",
        )
        self._cancel_handshake_timeout()
        self._handshake_timeout_id = self.after(
            int(config.HANDSHAKE_TIMEOUT_SECONDS * 1000), self._handshake_timeout
        )
        self._schedule_identity_probe(500)

    def _handshake_timeout(self) -> None:
        self._handshake_timeout_id = None
        if self._port_open and not self.controller.device_ready:
            self._set_led("error")
            detail = (
                "the version-4 dual-channel protocol was not reported"
                if self._hardware_banner_seen
                else "no compatible acquisition device responded"
            )
            self._set_status(f"Connection incomplete: {detail}.", "error")

    def _disconnect(self, status: str, error: bool = False) -> None:
        self._cancel_handshake_timeout()
        self._cancel_identity_probe()
        try:
            if self.controller.running:
                self.controller.stop()
        except ConnectionError:
            pass
        transport = self._transport
        self._transport = None
        if transport is not None:
            transport.close()
        self._port_open = False
        self.controller.disconnect()
        self._requested_average_count = None
        self.average_applied_count = None
        self.average_status_var.set("Arduino averaging: not connected")
        self._hardware_banner_seen = False
        self._resume_after_protocol = False
        self.connect_button.configure(text="Connect")
        self.port_combo.configure(state="readonly")
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.DISABLED)
        self.apply_average_button.configure(state=tk.DISABLED)
        self._update_adc_control_states()
        self._set_led("error" if error else "off")
        self._set_status(status, "error" if error else "neutral")

    def _write(self, data: bytes) -> None:
        if self._transport is None or not self._transport.is_open():
            raise ConnectionError("Arduino connection is not open.")
        self._transport.write(data)

    def _send_acquisition_settings(self) -> None:
        self._send_average_setting()
        self._write(f"delay,{config.DEFAULT_SAMPLE_INTERVAL_MS}\n".encode("ascii"))
        self._write(config.AUTORANGE_QUERY_COMMAND)
        self._write(config.RANGE_QUERY_COMMAND)

    def _send_average_setting(self) -> None:
        command = average_command(self.average_var.get())
        self._requested_average_count = int(self.average_var.get())
        self.average_status_var.set(
            f"Arduino averaging: applying {self._requested_average_count} pairs / point"
        )
        self._write(command)

    def _average_selection_changed(self, _event) -> None:
        selected = self.average_var.get()
        if self.average_applied_count is None:
            self.average_status_var.set(
                f"Arduino averaging: {selected} selected; applies on connection"
                if not self.controller.device_ready
                else f"Arduino averaging: {selected} selected; click Apply on Arduino"
            )
        elif selected != str(self.average_applied_count):
            self.average_status_var.set(
                f"Arduino averaging: {self.average_applied_count} confirmed; "
                f"{selected} selected, not applied"
            )

    def _apply_average(self) -> None:
        if not self.controller.device_ready:
            return
        try:
            self._send_average_setting()
        except (ConnectionError, ValueError) as exc:
            self._set_status(f"Could not set Arduino averaging: {exc}", "error")

    def _schedule_identity_probe(self, delay_ms: int = config.IDENTIFY_RETRY_MS) -> None:
        self._cancel_identity_probe()
        self._identity_probe_id = self.after(delay_ms, self._probe_identity)

    def _probe_identity(self) -> None:
        self._identity_probe_id = None
        if not self._port_open or self.controller.device_ready:
            return
        try:
            self._write(config.IDENTIFY_COMMAND)
        except ConnectionError as exc:
            self._event_queue.put(("error", f"Device identification failed: {exc}"))
            return
        self._schedule_identity_probe()

    def _start_acquisition(self) -> None:
        try:
            self.controller.start()
        except (ConnectionError, RuntimeError) as exc:
            self._event_queue.put(("error", f"Could not start acquisition: {exc}"))
            return
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self._set_status("Acquiring dual-channel voltage data…", "good")

    def _stop_acquisition(self) -> None:
        try:
            self.controller.stop()
        except ConnectionError as exc:
            self._event_queue.put(("error", f"Acquisition stopped after serial error: {exc}"))
            return
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self._set_status(
            f"Acquisition paused; {len(self.controller.dataset):,} points retained.",
            "neutral",
        )

    def _clear_data(self) -> bool:
        cleared = self.controller.confirm_and_clear(
            lambda: messagebox.askyesno(
                "Permanently clear data?",
                "Are you sure you want to permanently clear the current data?",
                icon="warning",
                default="no",
            )
        )
        if not cleared:
            return False
        self._discard_queued_data_lines()
        self.autoscale_var.set(True)
        self._last_plotted_count = -1
        self._redraw_plot(force=True)
        self._set_status("Current dataset and plot cleared.", "neutral")
        return True

    def _discard_queued_data_lines(self) -> None:
        retained: list[tuple[str, bytes | str]] = []
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            kind, payload = event
            is_data = kind == "line" and (
                (isinstance(payload, bytes) and payload.startswith(b"DATA,"))
                or (isinstance(payload, str) and payload.startswith("DATA,"))
            )
            if not is_data:
                retained.append(event)
        for event in retained:
            self._event_queue.put(event)

    def _export_data(self) -> Path | None:
        points = self.controller.dataset.snapshot()
        if not points:
            messagebox.showinfo("No data", "There is no collected data to export.")
            return None
        include_a = self.channel_a_enabled_var.get()
        include_b = self.channel_b_enabled_var.get()
        selected = filedialog.asksaveasfilename(
            title="Export serial data",
            defaultextension=".xlsx",
            filetypes=(("Excel workbook", "*.xlsx"),),
            initialfile=f"serial_plotter_v3_{datetime.now():%Y%m%d-%H%M%S}.xlsx",
        )
        if not selected:
            return None
        try:
            row_count = export_xlsx(
                selected,
                points,
                self.controller.calibration,
                include_a,
                include_b,
            )
        except (OSError, PermissionError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc))
            self._set_status(f"Excel export failed: {exc}", "error")
            return None
        destination = Path(selected)
        if destination.suffix.lower() != ".xlsx":
            destination = destination.with_suffix(".xlsx")
        self._set_status(f"Exported {row_count:,} points to {destination}", "good")
        return destination

    def _process_events(self) -> None:
        if self._closing:
            return
        changed = False
        for _ in range(1000):
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "error":
                self._disconnect(str(payload), error=True)
                continue
            if kind != "line":
                continue
            text = (
                payload.decode("ascii", errors="replace").strip()
                if isinstance(payload, bytes)
                else payload.strip()
            )
            if text == config.HANDSHAKE_BANNER:
                self._handle_hardware_banner()
            elif text == config.PROTOCOL_CAPABILITY:
                self._handle_protocol_capability()
            elif text.startswith("#autorange,"):
                self._handle_autorange_status(text)
            elif text.startswith("#range,"):
                self._handle_range_status(text)
            elif text.startswith("OK,avg,"):
                self._handle_average_ack(text)
            elif text.startswith("ERR,"):
                if text.startswith("ERR,INVALID_AVERAGE"):
                    self.average_status_var.set("Arduino averaging: setting rejected")
                self._set_status(f"Arduino reported: {text}", "error")
            elif text.startswith("#") or text.startswith("OK,") or not text:
                continue
            else:
                before = len(self.controller.dataset)
                self.controller.ingest(text)
                changed = changed or len(self.controller.dataset) != before
                if self.controller.storage_full:
                    self.start_button.configure(state=tk.NORMAL)
                    self.stop_button.configure(state=tk.DISABLED)
                    self._set_status("Stored-point safety limit reached.", "error")
        if changed or len(self.controller.dataset) != self._last_plotted_count:
            self._redraw_plot()
        self.after(config.UI_UPDATE_MS, self._process_events)

    def _handle_hardware_banner(self) -> None:
        if self.controller.device_ready:
            self._resume_after_protocol = self.controller.running
            self.controller.disconnect()
            self.start_button.configure(state=tk.DISABLED)
            self.stop_button.configure(state=tk.DISABLED)
        self.apply_average_button.configure(state=tk.DISABLED)
        self.average_applied_count = None
        self.average_status_var.set("Arduino averaging: waiting for firmware")
        self._hardware_banner_seen = True
        self._set_led("waiting")
        self._set_status("Acquisition hardware detected; verifying firmware…", "waiting")

    def _handle_protocol_capability(self) -> None:
        self._hardware_banner_seen = True
        if self.controller.device_ready:
            return
        resume_after_reset = self._resume_after_protocol
        self._resume_after_protocol = False
        self.controller.mark_device_ready()
        self._cancel_handshake_timeout()
        self._cancel_identity_probe()
        self._set_led("on")
        try:
            self._send_acquisition_settings()
            if resume_after_reset:
                self.controller.start()
        except (ConnectionError, ValueError) as exc:
            self._event_queue.put(("error", f"Device setup failed: {exc}"))
            return
        self.start_button.configure(
            state=tk.DISABLED if self.controller.running else tk.NORMAL
        )
        self.stop_button.configure(
            state=tk.NORMAL if self.controller.running else tk.DISABLED
        )
        self.apply_average_button.configure(state=tk.NORMAL)
        self._update_adc_control_states()
        self._set_status(
            "Arduino reset detected; streaming resumed."
            if resume_after_reset
            else "Arduino connected and ready.",
            "waiting" if resume_after_reset else "good",
        )

    def _handle_average_ack(self, text: str) -> None:
        try:
            count = int(text.split(",", 2)[2])
            self.controller.set_average_count(count)
        except (IndexError, ValueError):
            self._set_status(f"Invalid averaging response: {text}", "error")
            return
        if count == self._requested_average_count:
            self.average_applied_count = count
            self.average_status_var.set(
                f"Arduino averaging: {count} pairs / point confirmed"
            )

    @staticmethod
    def _format_adc_range(range_v: float) -> str:
        return f"±{range_v:.3f} V"

    @staticmethod
    def _parse_adc_range_label(label: str) -> float:
        return float(label.replace("±", "").replace("V", "").strip())

    def _update_adc_control_states(self) -> None:
        ready = self._port_open and self.controller.device_ready
        self.autorange_checkbutton.configure(
            state=tk.NORMAL if ready else tk.DISABLED
        )
        range_state = "readonly" if ready and not self.autorange_var.get() else tk.DISABLED
        self.range_a_combo.configure(state=range_state)
        self.range_b_combo.configure(state=range_state)

    def _toggle_autorange(self) -> None:
        if not self.controller.device_ready:
            self._update_adc_control_states()
            return
        self._update_adc_control_states()
        enabled = 1 if self.autorange_var.get() else 0
        try:
            self._write(f"autorange,{enabled}\n".encode("ascii"))
        except ConnectionError as exc:
            self._event_queue.put(("error", f"Could not change ADC autorange: {exc}"))

    def _manual_range_changed(self, event) -> None:
        if self.autorange_var.get() or not self.controller.device_ready:
            self._update_adc_control_states()
            return
        channel = "A" if event.widget is self.range_a_combo else "B"
        variable = self.range_a_var if channel == "A" else self.range_b_var
        try:
            range_v = self._parse_adc_range_label(variable.get())
            self._write(f"range,{channel},{range_v:.3f}\n".encode("ascii"))
        except (ConnectionError, ValueError) as exc:
            self._event_queue.put(("error", f"Could not change ADC range: {exc}"))

    def _handle_autorange_status(self, text: str) -> None:
        fields = text.split(",")
        if len(fields) != 2 or fields[1] not in {"0", "1"}:
            self._set_status(f"Invalid autorange status: {text}", "error")
            return
        self.autorange_var.set(fields[1] == "1")
        self._update_adc_control_states()

    def _handle_range_status(self, text: str) -> None:
        try:
            fields = dict(field.split("=", 1) for field in text.split(",")[1:])
            self.controller.set_adc_ranges(float(fields["A"]), float(fields["B"]))
        except (KeyError, ValueError):
            self._set_status(f"Invalid ADC range status: {text}", "error")
            return
        self.range_a_var.set(
            self._format_adc_range(self.controller.channel_a_adc_range_v)
        )
        self.range_b_var.set(
            self._format_adc_range(self.controller.channel_b_adc_range_v)
        )
        self._update_adc_control_states()

    def _redraw_plot(self, force: bool = False) -> None:
        points = self.controller.dataset.snapshot()
        count = len(points)
        if not force and count == self._last_plotted_count:
            return
        self.count_var.set(f"{count:,} point" + ("" if count == 1 else "s"))
        self._last_plotted_count = count
        times, channel_a_values, channel_b_values = downsample_for_display(points)
        show_a = self.channel_a_enabled_var.get()
        show_b = self.channel_b_enabled_var.get()
        self.channel_a_line.set_data(
            (times, channel_a_values) if show_a else ([], [])
        )
        self.channel_b_left_line.set_data(
            (times, channel_b_values) if show_b and not show_a else ([], [])
        )
        self.channel_b_right_line.set_data(
            (times, channel_b_values) if show_a and show_b else ([], [])
        )
        if times:
            self.axes.relim(visible_only=True)
            self.secondary_axes.relim(visible_only=True)
            if self.autoscale_var.get():
                self._apply_autoscale(times, channel_a_values, channel_b_values)
        else:
            self._reset_empty_plot()
        self.canvas.draw_idle()

    def _apply_autoscale(
        self,
        times: list[float],
        channel_a_values: list[float],
        channel_b_values: list[float],
    ) -> None:
        show_a = self.channel_a_enabled_var.get()
        show_b = self.channel_b_enabled_var.get()
        primary_values = channel_a_values if show_a else channel_b_values
        self._changing_plot_limits = True
        try:
            self.axes.set_autoscalex_on(True)
            self.axes.set_autoscaley_on(True)
            self.axes.relim(visible_only=True)
            self.axes.autoscale_view()
            self._pad_equal_range(times, self.axes.set_xlim)
            self._pad_equal_range(primary_values, self.axes.set_ylim)
            if show_a and show_b:
                self.secondary_axes.set_autoscaley_on(True)
                self.secondary_axes.relim(visible_only=True)
                self.secondary_axes.autoscale_view(scalex=False, scaley=True)
                self._pad_equal_range(channel_b_values, self.secondary_axes.set_ylim)
                self.secondary_axes.set_autoscaley_on(True)
            self.axes.set_autoscalex_on(True)
            self.axes.set_autoscaley_on(True)
        finally:
            self._changing_plot_limits = False

    def _reset_empty_plot(self) -> None:
        self._changing_plot_limits = True
        try:
            self.axes.set_xlim(0.0, 1.0)
            self.axes.set_ylim(0.0, 1.0)
            self.secondary_axes.set_ylim(0.0, 1.0)
            self.axes.set_autoscalex_on(True)
            self.axes.set_autoscaley_on(True)
            self.secondary_axes.set_autoscaley_on(True)
        finally:
            self._changing_plot_limits = False

    def _manual_limits_changed(self, _axes) -> None:
        if self._changing_plot_limits:
            return
        self.autoscale_var.set(False)
        self.axes.set_autoscalex_on(False)
        self.axes.set_autoscaley_on(False)
        self.secondary_axes.set_autoscaley_on(False)

    def _toggle_autoscale(self) -> None:
        if self.autoscale_var.get():
            self._home_plot()
        else:
            self.axes.set_autoscalex_on(False)
            self.axes.set_autoscaley_on(False)
            self.secondary_axes.set_autoscaley_on(False)

    def _home_plot(self) -> None:
        self.autoscale_var.set(True)
        self._redraw_plot(force=True)

    @staticmethod
    def _pad_equal_range(values: list[float], setter) -> None:
        low, high = min(values), max(values)
        if low == high:
            padding = max(1.0, abs(low) * 0.1)
            setter(low - padding, high + padding)

    def _set_led(self, state: str) -> None:
        colors = {
            "off": ("#777777", "#555555"),
            "waiting": ("#E6A700", "#A87800"),
            "on": ("#2EAD5B", "#18793A"),
            "error": ("#D64545", "#8E2525"),
        }
        fill, outline = colors[state]
        self.connection_led.itemconfigure(self._led, fill=fill, outline=outline)

    def _set_status(self, text: str, state: str) -> None:
        colors = {
            "neutral": "#555555",
            "waiting": "#9A6800",
            "good": "#18793A",
            "error": "#B22929",
        }
        self.status_var.set(text)
        self.status_label.configure(fg=colors[state])

    def _cancel_handshake_timeout(self) -> None:
        if self._handshake_timeout_id is not None:
            try:
                self.after_cancel(self._handshake_timeout_id)
            except tk.TclError:
                pass
            self._handshake_timeout_id = None

    def _cancel_identity_probe(self) -> None:
        if self._identity_probe_id is not None:
            try:
                self.after_cancel(self._identity_probe_id)
            except tk.TclError:
                pass
            self._identity_probe_id = None

    def _on_close(self) -> None:
        self._closing = True
        self._cancel_handshake_timeout()
        self._cancel_identity_probe()
        try:
            if self.controller.running:
                self.controller.stop()
        except ConnectionError:
            pass
        if self._transport is not None:
            self._transport.close()
        self.destroy()


def run_self_test() -> None:
    calibration = Calibration()
    sent: list[bytes] = []
    controller = AcquisitionController(sent.append, calibration)
    controller.mark_device_ready()
    controller.start()
    controller.ingest("DATA,100,1600,3200,1.000000,2.000000")
    controller.stop()
    if len(controller.dataset) != 1:
        raise RuntimeError("Acquisition pipeline self-test failed.")
    path = Path.cwd() / ".serial_plotter_v3_self_test.xlsx"
    try:
        export_xlsx(path, controller.dataset.snapshot(), calibration)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Excel export self-test failed.")
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def run_gui_smoke_test() -> None:
    """Exercise both channel axes and hardware controls against the simulator."""

    app = SerialPlotterV3App()
    app.port_combo.set(config.SIMULATOR_PORT)
    failures: list[str] = []

    def limits_include(values, limits) -> bool:
        if not values:
            return False
        low, high = sorted(limits)
        tolerance = max(1.0, abs(low), abs(high)) * 1e-9
        return min(values) >= low - tolerance and max(values) <= high + tolerance

    def connect() -> None:
        app.update_idletasks()
        if not app.channel_a_checkbutton.winfo_ismapped() or not (
            app.channel_b_checkbutton.winfo_ismapped()
        ):
            failures.append("channel selection controls were not visible")
        if not app.autorange_checkbutton.winfo_ismapped():
            failures.append("ADC autorange control was not visible")
        if not app.average_combo.winfo_ismapped() or not (
            app.apply_average_button.winfo_ismapped()
        ):
            failures.append("Arduino averaging controls were not visible")
        if not app.autoscale_checkbutton.winfo_ismapped():
            failures.append("plot autoscale control was not visible")
        toolbar_tools = {item[0] for item in app.toolbar.toolitems if item[0]}
        if not {"Home", "Pan", "Zoom"}.issubset(toolbar_tools):
            failures.append("plot navigation tools were incomplete")
        app._connect()

    def start() -> None:
        if not app.controller.device_ready:
            failures.append("simulator handshake was not processed")
            return
        if not app.autorange_var.get():
            failures.append("ADC autorange was not enabled by default")
        app.autorange_var.set(False)
        app._toggle_autorange()
        app.range_a_var.set(app._format_adc_range(1.024))
        app._manual_range_changed(type("Event", (), {"widget": app.range_a_combo})())
        transport = app._transport
        if not isinstance(transport, SimulatorTransport) or not math_isclose(
            transport.active_ranges[0], 1.024
        ):
            failures.append("manual Channel A range was not applied")
        app.autorange_var.set(True)
        app._toggle_autorange()
        app.average_var.set("8")
        app._apply_average()
        app._start_acquisition()

    def test_channel_layouts() -> None:
        if not len(app.controller.dataset):
            failures.append("no simulator data reached the GUI")
            return
        if app.average_applied_count != 8 or (
            app.controller.dataset.snapshot()[-1].average_count != 8
        ):
            failures.append("Arduino averaging was not confirmed or recorded")
        times = list(app.channel_a_line.get_xdata())
        values_a = list(app.channel_a_line.get_ydata())
        values_b = list(app.channel_b_right_line.get_ydata())
        if not times or not values_a or not values_b:
            failures.append("both-channel plot was incomplete")
        if not app.channel_a_line.get_visible() or not app.channel_b_right_line.get_visible():
            failures.append("both-channel traces were not assigned to opposite axes")
        if not app.secondary_axes.get_visible():
            failures.append("right axis was hidden with both channels selected")

        app.channel_b_enabled_var.set(False)
        app._channel_selection_changed("B")
        if not app.channel_a_line.get_visible() or app.secondary_axes.get_visible():
            failures.append("Channel A-only axis assignment was incorrect")
        if app.axes.get_ylabel() != "Channel A Voltage (V)":
            failures.append("Channel A-only left-axis label was incorrect")

        app.channel_a_enabled_var.set(False)
        app.channel_b_enabled_var.set(True)
        app._channel_selection_changed("A")
        if not app.channel_b_left_line.get_visible() or app.secondary_axes.get_visible():
            failures.append("Channel B-only trace was not moved to the left axis")
        if app.axes.get_ylabel() != "Channel B Voltage (V)":
            failures.append("Channel B-only left-axis label was incorrect")

        app.channel_b_enabled_var.set(False)
        app._channel_selection_changed("B")
        if not app.channel_b_enabled_var.get():
            failures.append("the GUI allowed both channels to become disabled")

        app.channel_a_enabled_var.set(True)
        app.channel_b_enabled_var.set(True)
        app._channel_selection_changed("A")
        if not app.secondary_axes.get_visible() or app.channel_b_left_line.get_visible():
            failures.append("switching back to both channels left stale axes")
        if not limits_include(times, app.axes.get_xlim()) or not limits_include(
            values_a, app.axes.get_ylim()
        ):
            failures.append("live plot autoscaling did not contain Channel A data")

        before_malformed = app.controller.malformed_lines
        app.controller.ingest("not-a-data-record")
        if app.controller.malformed_lines != before_malformed + 1:
            failures.append("malformed serial data was not handled safely")
        app._stop_acquisition()

    def resume_and_disconnect() -> None:
        retained = len(app.controller.dataset)
        app._start_acquisition()
        if not app.controller.running or len(app.controller.dataset) != retained:
            failures.append("resume changed retained data or failed to start")
        transport = app._transport
        if isinstance(transport, SimulatorTransport):
            transport.simulate_disconnect()
        else:
            failures.append("GUI lost its simulator transport")

    def finish() -> None:
        if app.controller.device_ready or app.controller.running:
            failures.append("connection loss did not stop acquisition")
        app._on_close()

    app.after(50, connect)
    app.after(250, start)
    app.after(650, test_channel_layouts)
    app.after(900, resume_and_disconnect)
    app.after(1100, finish)
    app.mainloop()
    if failures:
        raise RuntimeError("; ".join(failures))


def math_isclose(left: float, right: float) -> bool:
    return abs(left - right) < 1e-9


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serial Plotter V3")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--gui-smoke-test", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if options.smoke_test:
        run_self_test()
        return 0
    if options.gui_smoke_test:
        run_gui_smoke_test()
        return 0
    SerialPlotterV3App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
