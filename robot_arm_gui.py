import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports


BAUD_RATE = 115200
SERVO_COUNT = 6
HOME_ANGLES = [90, 90, 90, 90, 90, 90]
RECORD_FILE = "robot_arm_recording.json"


class RobotArmApp:
    def __init__(self, root):
        self.root = root
        self.root.title("6DOF Robot Arm Controller")
        self.root.geometry("700x520")
        self.root.resizable(False, False)

        self.ser = None
        self.angles = HOME_ANGLES.copy()
        self.recording = False
        self.recorded_frames = []
        self.record_start_time = None
        self.stop_event = threading.Event()
        self.play_thread = None
        self.ignore_slider_callback = False
        self.send_after_id = None

        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Disconnected")
        self.file_var = tk.StringVar(value=f"Recording file: {os.path.abspath(RECORD_FILE)}")

        self.sliders = []
        self.value_labels = []

        self.build_ui()
        self.refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Serial Port:").pack(side="left")
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=20, state="readonly")
        self.port_combo.pack(side="left", padx=5)

        ttk.Button(top, text="Refresh", command=self.refresh_ports).pack(side="left", padx=5)
        ttk.Button(top, text="Connect", command=self.connect_serial).pack(side="left", padx=5)
        ttk.Button(top, text="Disconnect", command=self.disconnect_serial).pack(side="left", padx=5)

        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        slider_frame = ttk.LabelFrame(self.root, text="Servo Control", padding=10)
        slider_frame.pack(fill="both", expand=True, padx=10, pady=10)

        for i in range(SERVO_COUNT):
            row = ttk.Frame(slider_frame)
            row.pack(fill="x", pady=8)

            ttk.Label(row, text=f"Servo {i + 1}", width=10).pack(side="left")

            slider = tk.Scale(
                row,
                from_=0,
                to=180,
                orient="horizontal",
                length=420,
                resolution=1,
                command=lambda value, idx=i: self.on_slider_change(idx, value)
            )
            slider.set(self.angles[i])
            slider.pack(side="left", padx=10)

            value_label = ttk.Label(row, text=str(self.angles[i]), width=5)
            value_label.pack(side="left")

            self.sliders.append(slider)
            self.value_labels.append(value_label)

        button_frame = ttk.Frame(self.root, padding=10)
        button_frame.pack(fill="x")

        self.record_button = ttk.Button(button_frame, text="Record", command=self.toggle_recording)
        self.record_button.pack(side="left", padx=5)

        ttk.Button(button_frame, text="Play", command=self.play_recording).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Stop", command=self.stop_all).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Home", command=self.go_home).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Save Current Angles", command=self.save_current_pose).pack(side="left", padx=5)

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")

        ttk.Label(bottom, textvariable=self.file_var).pack(side="left")

        info = ttk.LabelFrame(self.root, text="Notes", padding=10)
        info.pack(fill="x", padx=10, pady=(0, 10))

        msg = (
            "1. Connect Arduino by USB.\n"
            "2. Select COM port and press Connect.\n"
            "3. Move sliders to control the arm.\n"
            "4. Press Record, move sliders, then press Record again to stop and save.\n"
            "5. Press Play to replay saved movement.\n"
            "6. Stop will stop playback and send the arm to Home."
        )
        ttk.Label(info, text=msg, justify="left").pack(anchor="w")

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def connect_serial(self):
        if self.ser and self.ser.is_open:
            messagebox.showinfo("Info", "Already connected.")
            return

        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Error", "Select a COM port first.")
            return

        try:
            self.ser = serial.Serial(port, BAUD_RATE, timeout=0.2)
            time.sleep(2.0)  # allow Arduino to reset
            self.status_var.set(f"Connected: {port}")
            self.send_all_angles(record_frame=False)
        except Exception as e:
            self.ser = None
            messagebox.showerror("Connection Error", str(e))
            self.status_var.set("Disconnected")

    def disconnect_serial(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        finally:
            self.ser = None
            self.status_var.set("Disconnected")

    def send_command(self, cmd: str):
        if not self.ser or not self.ser.is_open:
            return
        try:
            self.ser.write((cmd + "\n").encode("utf-8"))
        except Exception as e:
            self.status_var.set(f"Send error: {e}")

    def send_all_angles(self, record_frame=True):
        cmd = "ALL," + ",".join(str(a) for a in self.angles)
        self.send_command(cmd)

        if record_frame and self.recording:
            self.record_current_frame()

    def on_slider_change(self, idx, value):
        if self.ignore_slider_callback:
            return

        angle = int(float(value))
        self.angles[idx] = angle
        self.value_labels[idx].config(text=str(angle))

        if self.send_after_id is not None:
            self.root.after_cancel(self.send_after_id)

        self.send_after_id = self.root.after(20, self.delayed_send)

    def delayed_send(self):
        self.send_after_id = None
        self.send_all_angles(record_frame=True)

    def set_sliders_silently(self, new_angles):
        self.ignore_slider_callback = True
        for i, angle in enumerate(new_angles):
            self.angles[i] = int(angle)
            self.sliders[i].set(int(angle))
            self.value_labels[i].config(text=str(int(angle)))
        self.ignore_slider_callback = False

    def toggle_recording(self):
        if self.recording:
            self.stop_recording_and_save()
        else:
            self.start_recording()

    def start_recording(self):
        if not self.ser or not self.ser.is_open:
            messagebox.showerror("Error", "Connect to Arduino first.")
            return

        self.stop_event.set()
        self.recording = True
        self.recorded_frames = []
        self.record_start_time = time.time()
        self.record_button.config(text="Stop Recording")

        self.record_current_frame()
        self.status_var.set("Recording...")

    def stop_recording_and_save(self):
        self.recording = False
        self.record_button.config(text="Record")

        if not self.recorded_frames:
            self.status_var.set("Recording stopped. No frames saved.")
            return

        data = {
            "servo_count": SERVO_COUNT,
            "home_angles": HOME_ANGLES,
            "frames": self.recorded_frames
        }

        try:
            with open(RECORD_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.file_var.set(f"Recording file: {os.path.abspath(RECORD_FILE)}")
            self.status_var.set(f"Recording saved: {len(self.recorded_frames)} frames")
            messagebox.showinfo("Saved", f"Recording saved to:\n{os.path.abspath(RECORD_FILE)}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
            self.status_var.set("Save failed")

    def record_current_frame(self):
        if self.record_start_time is None:
            return

        t = round(time.time() - self.record_start_time, 3)
        frame = {
            "t": t,
            "angles": self.angles.copy()
        }

        if not self.recorded_frames:
            self.recorded_frames.append(frame)
            return

        last = self.recorded_frames[-1]
        if last["angles"] != frame["angles"]:
            self.recorded_frames.append(frame)

    def play_recording(self):
        if not self.ser or not self.ser.is_open:
            messagebox.showerror("Error", "Connect to Arduino first.")
            return

        if not os.path.exists(RECORD_FILE):
            messagebox.showerror("Error", f"No recording file found:\n{os.path.abspath(RECORD_FILE)}")
            return

        if self.recording:
            messagebox.showerror("Error", "Stop recording before playback.")
            return

        self.stop_event.set()
        time.sleep(0.05)
        self.stop_event.clear()

        self.play_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.play_thread.start()

    def _playback_worker(self):
        try:
            with open(RECORD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            frames = data.get("frames", [])
            if not frames:
                self.root.after(0, lambda: messagebox.showerror("Error", "Recording file is empty."))
                return

            self.root.after(0, lambda: self.status_var.set("Playing..."))

            start_time = time.perf_counter()

            for frame in frames:
                if self.stop_event.is_set():
                    self.root.after(0, lambda: self.status_var.set("Playback stopped"))
                    return

                target_t = float(frame["t"])
                while not self.stop_event.is_set():
                    elapsed = time.perf_counter() - start_time
                    remaining = target_t - elapsed
                    if remaining <= 0:
                        break
                    time.sleep(min(0.01, remaining))

                angles = [int(a) for a in frame["angles"]]
                self.angles = angles.copy()
                self.send_all_angles(record_frame=False)
                self.root.after(0, lambda a=angles: self.set_sliders_silently(a))

            self.root.after(0, lambda: self.status_var.set("Playback finished"))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Playback Error", str(e)))
            self.root.after(0, lambda: self.status_var.set("Playback error"))

    def stop_all(self):
        self.stop_event.set()

        if self.recording:
            self.recording = False
            self.record_button.config(text="Record")

        self.go_home()
        self.status_var.set("Stopped")

    def go_home(self):
        self.set_sliders_silently(HOME_ANGLES)
        self.send_command("HOME")

    def save_current_pose(self):
        pose_file = "robot_arm_current_pose.json"
        data = {"angles": self.angles}
        try:
            with open(pose_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Saved", f"Current pose saved to:\n{os.path.abspath(pose_file)}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def on_close(self):
        self.stop_event.set()
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = RobotArmApp(root)
    root.mainloop()