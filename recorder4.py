# stream_plot_tk.py — Tkinter + Matplotlib real-time plotter (Python 3.14 OK)
# UI: Port picker + Connect, Start/Stop/Clear/Export, Gain (1x/10x), Averages, live time→mV plot.
# Handshake: waits for "Modern Lab Data Acquisition Shield" after opening; lights a green LED and applies defaults then.

import threading
import time
import queue
from collections import deque

import numpy as np
import serial
import serial.tools.list_ports as list_ports

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ------------------ FIXED SETTINGS (edit here) ------------------
BAUD_RATE = 115200         # fixed baud
SEND_LINE_ENDING = b"\n"   # fixed line ending for commands
START_CMD = b"run" + SEND_LINE_ENDING
STOP_CMD  = b"stop" + SEND_LINE_ENDING

DEFAULT_GAIN = "1x"        # applied only after handshake banner received
DEFAULT_AVG = 100          # applied only after handshake banner received (1..10000)

HANDSHAKE_BANNER = "Modern Lab Data Acquisition Shield"
HANDSHAKE_TIMEOUT_SEC = 10.0

MAX_POINTS = 2_000_000     # hard cap on stored points (safety)
UI_UPDATE_MS = 33          # ~30 FPS plot updates
READ_CHUNK = 2048          # serial bytes per read
# ----------------------------------------------------------------


def list_com_ports():
    return [p.device for p in list_ports.comports()]


class SerialReader:
    """Background serial reader that assembles lines and hands them to a callback."""
    def __init__(self, on_line):
        self._ser = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thr = None
        self._buff = bytearray()
        self._on_line = on_line  # callback(bline: bytes)

    def open(self, port: str, baud: int):
        self.close()
        try:
            self._ser = serial.Serial(port=port, baudrate=baud, timeout=0.1)
        except Exception as e:
            self._ser = None
            raise e
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def is_open(self):
        return self._ser is not None and self._ser.is_open

    def write(self, data: bytes):
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.write(data)

    def close(self):
        self._stop.set()
        with self._lock:
            if self._ser:
                try:
                    self._ser.close()
                except Exception:
                    pass
        self._ser = None
        self._buff = bytearray()

    def _loop(self):
        while not self._stop.is_set():
            try:
                with self._lock:
                    s = self._ser
                if not (s and s.is_open):
                    time.sleep(0.05)
                    continue
                chunk = s.read(READ_CHUNK)
                if chunk:
                    self._buff.extend(chunk)
                    while True:
                        nl = self._buff.find(b"\n")
                        if nl < 0:
                            break
                        line = self._buff[:nl]
                        # strip \r if present
                        if line.endswith(b"\r"):
                            line = line[:-1]
                        if self._on_line:
                            self._on_line(bytes(line))
                        del self._buff[:nl+1]
            except Exception:
                # transient read error; back off a beat
                time.sleep(0.1)


class PlotApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Modern Lab – Stream Plot (time → mV)")
        self.geometry("1220x740")

        # Serial & parser
        self.reader = SerialReader(on_line=self._handle_line)
        self.running = False  # start/stop gate

        # Handshake / defaults
        self.banner_seen = False
        self.defaults_applied = False
        self._handshake_timeout_id = None

        # Data buffers
        self.t_buf = deque()   # seconds (float, relative to first point after a clear/connect)
        self.y_buf = deque()   # millivolts (float)
        self._t0 = None        # reference time for relative axis

        # Thread-safe handoff from parser to UI
        self.point_q: queue.Queue[tuple[float, float]] = queue.Queue()

        # Build UI
        self._build_ui()

        # Plot timer
        self.after(UI_UPDATE_MS, self._update_plot)

        # Clean close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -------------------- UI --------------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        # LED (left of Port)
        self.led = tk.Canvas(top, width=14, height=14, highlightthickness=0)
        self.led.grid(row=0, column=0, padx=(0, 6))
        self._led_item = self.led.create_oval(2, 2, 12, 12, fill="#666", outline="#444")

        # Port + connect
        ttk.Label(top, text="Port:").grid(row=0, column=1, sticky="w")
        self.port_combo = ttk.Combobox(top, width=18, state="readonly", values=list_com_ports())
        if self.port_combo["values"]:
            self.port_combo.set(self.port_combo["values"][0])
        self.port_combo.grid(row=0, column=2, padx=(4, 12))

        ttk.Button(top, text="Refresh", command=self._refresh_ports)\
            .grid(row=0, column=3, padx=(0, 12))

        self.connect_btn = ttk.Button(top, text="Connect", command=self._toggle_connect)
        self.connect_btn.grid(row=0, column=4, padx=(0, 16))

        # Start/Stop
        self.start_btn = ttk.Button(top, text="Start", command=self._start_stream, state="disabled")
        self.start_btn.grid(row=0, column=5, padx=(0, 8))
        self.stop_btn  = ttk.Button(top, text="Stop",  command=self._stop_stream,  state="disabled")
        self.stop_btn.grid(row=0, column=6, padx=(0, 16))

        # Gain dropdown
        ttk.Label(top, text="Gain:").grid(row=0, column=7, sticky="e")
        self.gain_var = tk.StringVar(value=DEFAULT_GAIN)
        self.gain_combo = ttk.Combobox(top, width=6, state="disabled",
                                       values=["1x", "10x"], textvariable=self.gain_var)
        self.gain_combo.grid(row=0, column=8, padx=(4, 16))
        self.gain_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_gain())

        # Averages input
        ttk.Label(top, text="Averages:").grid(row=0, column=9, sticky="e")
        self.avg_var = tk.StringVar(value=str(DEFAULT_AVG))
        try:
            Spinbox = ttk.Spinbox  # type: ignore[attr-defined]
        except Exception:
            Spinbox = tk.Spinbox
        self.avg_spin = Spinbox(top, from_=1, to=10000, width=8, textvariable=self.avg_var, state="disabled")
        self.avg_spin.grid(row=0, column=10, padx=(4, 8))
        if hasattr(self.avg_spin, "configure"):
            self.avg_spin.configure(command=self._apply_avg)
        self.avg_spin.bind("<Return>", lambda e: self._apply_avg())
        self.avg_spin.bind("<FocusOut>", lambda e: self._apply_avg())

        # Clear / Export
        self.clear_btn = ttk.Button(top, text="Clear Data", command=self._clear_data, state="normal")
        self.clear_btn.grid(row=0, column=11, padx=(8, 8))

        self.export_btn = ttk.Button(top, text="Export CSV", command=self._export_csv, state="normal")
        self.export_btn.grid(row=0, column=12)

        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(self, textvariable=self.status_var, foreground="#666")\
            .pack(side=tk.TOP, anchor="w", padx=12, pady=(4, 0))

        # ---- Plot area ----
        fig = Figure(figsize=(11.2, 6.2), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (mV)")
        self.ax.grid(True, alpha=0.3)
        (self.line,) = self.ax.plot([], [], linewidth=2)
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _set_led(self, on: bool):
        self.led.itemconfigure(self._led_item, fill="#2ecc71" if on else "#666", outline="#2a7" if on else "#444")

    # -------------------- Serial control --------------------
    def _refresh_ports(self):
        ports = list_com_ports()
        self.port_combo.configure(values=ports)
        if ports and self.port_combo.get() not in ports:
            self.port_combo.set(ports[0])
        if not ports:
            self.port_combo.set("")

    def _toggle_connect(self):
        # Cancel any pending timeout checker
        if self._handshake_timeout_id is not None:
            try:
                self.after_cancel(self._handshake_timeout_id)
            except Exception:
                pass
            self._handshake_timeout_id = None

        if self.reader.is_open():
            # disconnect
            self._stop_stream()
            self.reader.close()
            self.banner_seen = False
            self.defaults_applied = False
            self._set_led(False)
            self._set_status("Disconnected")
            self.connect_btn.configure(text="Connect")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            self.gain_combo.configure(state="disabled")
            self.avg_spin.configure(state="disabled")
            return

        # connect
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showerror("No port", "Select a serial port.")
            return
        try:
            self.reader.open(port, BAUD_RATE)
        except Exception as e:
            messagebox.showerror("Open failed", str(e))
            return

        # Fresh session after connecting
        self._reset_buffers()
        self.banner_seen = False
        self.defaults_applied = False
        self._set_led(False)

        # UI enablement
        self.connect_btn.configure(text="Disconnect")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.gain_combo.configure(state="readonly")
        self.avg_spin.configure(state="normal")

        # Show connecting… while waiting for the banner
        self._set_status(f"Connecting… waiting for handshake (up to {int(HANDSHAKE_TIMEOUT_SEC)} s)")
        self._handshake_timeout_id = self.after(int(HANDSHAKE_TIMEOUT_SEC * 1000), self._handshake_timeout)

    def _handshake_timeout(self):
        self._handshake_timeout_id = None
        if not self.banner_seen and self.reader.is_open():
            # No banner yet — proceed without LED/defaults
            self._set_status("Connected (no handshake)")
            self._set_led(False)

    def _apply_defaults_after_banner(self):
        if self.defaults_applied or not self.reader.is_open():
            return
        # Set gain → 1x
        self.gain_var.set(DEFAULT_GAIN)
        self._apply_gain()
        # Set averages → 100
        self.avg_var.set(str(DEFAULT_AVG))
        self._apply_avg()
        self.defaults_applied = True
        self._set_status("Handshake OK — defaults applied")

    def _start_stream(self):
        """Start or resume streaming WITHOUT clearing existing data."""
        if not self.reader.is_open():
            return
        self.running = True
        try:
            self.reader.write(START_CMD)
        except Exception as e:
            self._set_status(f"Write error: {e}", bad=True)

    def _stop_stream(self):
        """Pause plotting/collection; keep data on screen."""
        self.running = False
        if self.reader.is_open():
            try:
                self.reader.write(STOP_CMD)
            except Exception as e:
                self._set_status(f"Write error: {e}", bad=True)

    # -------------------- Gain / Averages --------------------
    def _apply_gain(self):
        """Send '1x' or '10x' when the dropdown changes."""
        if not self.reader.is_open():
            return
        val = self.gain_var.get().strip()
        if val not in ("1x", "10x"):
            self._set_status(f"Invalid gain: {val}", bad=True)
            return
        cmd = (val.encode("utf-8") + SEND_LINE_ENDING)
        try:
            self.reader.write(cmd)
            self._set_status(f"Gain set → {val}")
        except Exception as e:
            self._set_status(f"Write error: {e}", bad=True)

    def _apply_avg(self):
        """Validate (1..10000) and send 'avg,<n>' when averages changes."""
        if not self.reader.is_open():
            return
        raw = self.avg_var.get().strip()
        try:
            n = int(float(raw))  # allow '100.0' typed in
        except ValueError:
            n = DEFAULT_AVG
        n = max(1, min(10_000, n))
        self.avg_var.set(str(n))
        cmd = f"avg,{n}".encode("utf-8") + SEND_LINE_ENDING
        try:
            self.reader.write(cmd)
            self._set_status(f"Averages set → {n}")
        except Exception as e:
            self._set_status(f"Write error: {e}", bad=True)

    # -------------------- Clear / Export --------------------
    def _clear_data(self):
        if len(self.t_buf) > 0:
            ok = messagebox.askokcancel(
                "Clear data?",
                "This will irreversibly erase the data on the active plot.\n\nProceed?",
                icon="warning",
                default=messagebox.CANCEL
            )
            if not ok:
                return
        self._reset_buffers()
        self.canvas.draw_idle()
        self._set_status("Data cleared.")

    def _export_csv(self):
        if not self.t_buf:
            messagebox.showinfo("No data", "There is no data to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export data to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"stream_{time.strftime('%Y%m%d-%H%M%S')}.csv",
        )
        if not path:
            return
        try:
            x = list(self.t_buf)
            y = list(self.y_buf)
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["time_s", "mV"])
                w.writerows(zip(x, y))
            self._set_status(f"Exported {len(x)} rows → {path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    # -------------------- Data path --------------------
    def _handle_line(self, bline: bytes):
        """
        Process every line for the handshake banner.
        Then, if streaming is active, parse data lines:
          - "t,value" where t is seconds or milliseconds
          - "value" only (we time-stamp on arrival)
        """
        try:
            txt = bline.decode("utf-8", errors="ignore").strip()
        except Exception:
            txt = ""

        # Handshake detection (always active)
        if txt == HANDSHAKE_BANNER and not self.banner_seen:
            self.banner_seen = True
            self._set_led(True)
            self._set_status("Handshake received — device ready")
            # Apply defaults once banner seen
            self._apply_defaults_after_banner()

        # Data processing only when running
        if not self.running:
            return
        if not txt:
            return
        try:
            parts = [p.strip() for p in txt.split(",") if p.strip()]
            if len(parts) == 1:
                # only a value → stamp time now
                t_sec_abs = time.perf_counter()
                y_mv = float(parts[0])
            else:
                # t,value
                t_raw = float(parts[0])
                # heuristic: if looks like ms, convert to s
                t_sec_abs = t_raw / 1000.0 if t_raw > 1000 else t_raw
                y_mv = float(parts[1])

            self.point_q.put((t_sec_abs, y_mv))
        except Exception:
            # ignore malformed lines
            pass

    def _reset_buffers(self):
        self.t_buf.clear()
        self.y_buf.clear()
        self._t0 = None
        self.line.set_data([], [])
        self.ax.relim()
        self.ax.autoscale_view()

    # -------------------- Plot update --------------------
    def _update_plot(self):
        # drain queue
        drained = 0
        while drained < 200 and not self.point_q.empty():
            t_abs, y_mv = self.point_q.get_nowait()
            if self._t0 is None:
                # Use first point as time zero (nice clean axis)
                self._t0 = t_abs
            t_rel = t_abs - self._t0
            self.t_buf.append(t_rel)
            self.y_buf.append(y_mv)
            drained += 1

        if self.t_buf:
            # Safety cap
            if len(self.t_buf) > MAX_POINTS:
                drop = len(self.t_buf) - MAX_POINTS
                for _ in range(drop):
                    self.t_buf.popleft()
                    self.y_buf.popleft()

            x = np.fromiter(self.t_buf, dtype=float)
            y = np.fromiter(self.y_buf, dtype=float)
            self.line.set_data(x, y)

            # X: show whole collected range (no rolling trim)
            xmin = 0.0
            xmax = x[-1] if len(x) else 1.0
            if xmax <= xmin:
                xmax = xmin + 1.0
            self.ax.set_xlim(xmin, xmax)

            # Y: autoscale to current data with small padding
            if len(y):
                ymin = np.nanmin(y)
                ymax = np.nanmax(y)
                if ymin == ymax:
                    pad = 1.0 if ymin == 0 else abs(ymin) * 0.1
                    self.ax.set_ylim(ymin - pad, ymax + pad)
                else:
                    pad = 0.05 * (ymax - ymin)
                    self.ax.set_ylim(ymin - pad, ymax + pad)

            self.canvas.draw_idle()

        self.after(UI_UPDATE_MS, self._update_plot)

    # -------------------- utils --------------------
    def _set_status(self, msg: str, bad: bool = False):
        self.status_var.set(msg)
        color = "#c33" if bad else "#2a7" if ("Handshake" in msg or "Connected" in msg or "Exported" in msg or "set →" in msg) else "#666"
        for w in self.children.values():
            if isinstance(w, ttk.Label) and w.cget("textvariable") == str(self.status_var):
                w.configure(foreground=color)

    def _on_close(self):
        try:
            self.running = False
            if self.reader.is_open():
                try:
                    self.reader.write(STOP_CMD)
                except Exception:
                    pass
                self.reader.close()
        finally:
            self.destroy()


if __name__ == "__main__":
    PlotApp().mainloop()
