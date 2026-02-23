import random
import sys
import threading
import subprocess
import os
import shutil
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

# Determine project root that works when running normally or when bundled by PyInstaller
if getattr(sys, "frozen", False):
    # When frozen by PyInstaller, resources are available in sys._MEIPASS
    ROOT = Path(getattr(sys, "_MEIPASS", "."))
else:
    ROOT = Path(__file__).parent.parent

CLIP_DURATION = 5.0  # seconds

from urllib.parse import urlparse, parse_qs
import csv

def ffmpeg_available() -> bool:
    """Return True if ffmpeg is available on PATH or bundled with the exe."""
    # check bundled location first
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", ".")) / "ffmpeg" / "bin" / "ffmpeg.exe"
        if bundled.exists():
            return True
    return shutil.which("ffmpeg") is not None


def clean_youtube_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "v" in params:
            video_id = params["v"][0]
            return f"https://www.youtube.com/watch?v={video_id}"
    except:
        pass
    return url


from yt_dlp import YoutubeDL

def download_clip(
    url: str,
    start_time: float,
    duration: float,
    output_template: str,
    log_callback=print,
    stop_event=None,
) -> None:
    """
    Download a clip.
    """
    start = int(start_time)
    end = int(start_time + duration)

    ydl_opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",

        "outtmpl": output_template,

        # 🔑 THIS is the critical part
        "download_ranges": lambda info_dict, ydl: [
            {"start_time": start, "end_time": end}
        ],

        "merge_output_format": "mp4",

        "postprocessor_args": [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
        ],

        "quiet": True,
        "no_warnings": True,
        "no-cache-dir": True,
        "socket_timeout": 30,
        "sleep_requests": random.uniform(1.5, 3.0),
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },
    }

    log_callback(f"    Downloading {start}-{end}s ... ")

    with YoutubeDL(ydl_opts) as ydl:
        ydl.cache.remove()
        ydl.download([url])

    log_callback("OK\n")



def parse_input_csv(csv_path: str):
    rows = []

    def convert_timestamp(ts: str) -> float:
        parts = ts.split(".")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            return float(ts)

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not any(row):
                rows.append([])
                continue

            pairs = []
            for i in range(0, len(row), 2):
                if i + 1 >= len(row):
                    continue

                url = row[i].strip()
                ts_raw = row[i + 1].strip()

                if not url or not ts_raw:
                    continue

                # Clean URL to remove playlist parameters
                url = clean_youtube_url(url)

                timestamps = [
                    convert_timestamp(t.strip())
                    for t in ts_raw.split(";")
                    if t.strip()
                ]

                pairs.append((url, timestamps))

            rows.append(pairs)

    return rows


def process_clips(csv_path: str, output_base_dir: str, log_callback=print, stop_event=None) -> None:
    rows = parse_input_csv(csv_path)

    # Filter out empty rows and count only non-empty rows
    non_empty_rows = [(idx, pairs) for idx, pairs in enumerate(rows) if pairs]

    log_callback(f"Processing {len(non_empty_rows)} non-empty rows\n\n")

    total_clips = sum(len(ts) for _, pairs in non_empty_rows for _, ts in pairs)
    clips_done = 0

    for output_row_num, (_, pairs) in enumerate(non_empty_rows, start=1):
        if stop_event and stop_event.is_set():
            log_callback("Processing canceled by user.\n")
            return

        log_callback(f"Row {output_row_num}:\n")
        row_start_time = time.perf_counter()
        clip_count = 1

        row_out = os.path.join(output_base_dir, str(output_row_num))
        os.makedirs(row_out, exist_ok=True)
        urlIndex = 0

        for url, timestamps in pairs:
            log_callback(f"  URL: {url} with {len(timestamps)} timestamp(s)\n")

            urlIndex += 1
            for ts in timestamps:
                if stop_event and stop_event.is_set():
                    log_callback("Processing canceled by user.\n")
                    return

                clips_done += 1
                # Save as x.y without extension (yt-dlp will add it)
                output_template = os.path.join(
                    row_out, f"{output_row_num}.{urlIndex}.{clip_count}"
                )

                log_callback(f"    [{clips_done}/{total_clips}] {int(ts)}s ")
                try:
                    download_clip(
                        url,
                        ts,
                        CLIP_DURATION,
                        output_template,
                        log_callback=log_callback,
                        stop_event=stop_event,
                    )
                    clip_count += 1
                    stampsleep = random.uniform(1, 2)
                    log_callback(f"         Pausing before next clip in {stampsleep.__round__(2)}s\n")
                    time.sleep(stampsleep)  # brief pause between downloads
                except Exception as e:
                    log_callback(f"Error: {str(e)[:200]}\n")
            clip_count = 1
        row_end_time = time.perf_counter()
        row_duration = row_end_time - row_start_time
        log_callback(f"Row {output_row_num}: completed in {row_duration.__round__(2)}s\n")
        rowsleep = random.uniform(10, 15)
        log_callback(f"         Pausing before next row in {rowsleep.__round__(2)}s\n\n")
        time.sleep(rowsleep)  # brief pause between rows


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("5Sec Downloader")
        self.geometry("800x620")

        self.csv_path = tk.StringVar() #tk.StringVar(value=str(ROOT / "input" / "input.csv"))
        self.output_path = tk.StringVar() #tk.StringVar(value=str(ROOT / "output"))

        self.proc = None
        self.proc_thread = None
        self.stop_event = threading.Event()

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)

        credit_row = ttk.Frame(frm)
        credit_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(0,6))
        ttk.Label(credit_row, text="2026 TranDucThang's 5-Sec Downloader").pack(side=tk.LEFT)
        fb_lbl = tk.Label(credit_row, text="Facebook", fg="blue", cursor="hand2")
        fb_lbl.pack(side=tk.RIGHT)
        fb_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://www.facebook.com/rhymx2k3/"))

        # CSV selector
        csv_row = ttk.Frame(frm)
        csv_row.pack(fill=tk.X, pady=6)
        ttk.Label(csv_row, text="Input CSV:").pack(side=tk.LEFT)
        csv_entry = ttk.Entry(csv_row, textvariable=self.csv_path)
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(csv_row, text="Browse", command=self.browse_csv).pack(side=tk.RIGHT)

        # Output selector
        out_row = ttk.Frame(frm)
        out_row.pack(fill=tk.X, pady=6)
        ttk.Label(out_row, text="Output folder:").pack(side=tk.LEFT)
        out_entry = ttk.Entry(out_row, textvariable=self.output_path)
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(out_row, text="Browse", command=self.browse_output).pack(side=tk.RIGHT)

        # Controls
        ctrl_row = ttk.Frame(frm)
        ctrl_row.pack(fill=tk.X, pady=6)
        self.start_btn = ttk.Button(ctrl_row, text="Start", command=self.start)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(ctrl_row, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)
        ttk.Button(ctrl_row, text="Open output", command=self.open_output).pack(side=tk.LEFT)

        # Log area
        log_row = ttk.Frame(frm)
        log_row.pack(fill=tk.BOTH, expand=True, pady=6)
        self.log = tk.Text(log_row, state=tk.NORMAL, wrap=tk.NONE)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_row, orient=tk.VERTICAL, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scrollbar.set)

        # Credits row: left text and right clickable Facebook link (pinned to bottom so always visible)
        
        # Prevent the window from being resized smaller than the current layout so credits remain visible
        self.update_idletasks()
        self.minsize(self.winfo_width(), self.winfo_height())

    def browse_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv" )])
        if path:
            self.csv_path.set(path)

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_path.set(path)

    def open_output(self):
        path = Path(self.output_path.get())
        if not path.exists():
            messagebox.showwarning("Not found", "Output folder does not exist yet")
            return
        # Open in file explorer
        subprocess.run(["explorer", str(path)])

    def _find_ffmpeg_exe(self):
        # If running as a PyInstaller bundle, prefer the bundled ffmpeg (inside sys._MEIPASS)
        if getattr(sys, "frozen", False):
            meipass = Path(getattr(sys, "_MEIPASS", "."))
            bundled = meipass / "ffmpeg" / "bin" / "ffmpeg.exe"
            if bundled.exists():
                return bundled

        # Search common installation locations and fallback to which()
        # Returns Path or None
        # 1) WinGet packages
        local_winget = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet' / 'Packages'
        candidates = [local_winget, Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Gyan', Path('C:/Program Files/Gyan')]
        for base in candidates:
            if base.exists():
                for p in base.rglob('ffmpeg.exe'):
                    return p
        # fallback to PATH lookup
        path = shutil.which('ffmpeg')
        if path:
            return Path(path)
        return None

    def _install_ffmpeg(self):
        # Attempt to install via winget
        if shutil.which('winget') is None:
            self._append_log("winget not found, cannot install ffmpeg automatically. Please install ffmpeg manually and add to PATH.\n")
            return False

        self._append_log("Installing ffmpeg via winget... (may take a few minutes)\n")
        proc = subprocess.run([
            "winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-package-agreements", "--accept-source-agreements"
        ], capture_output=True, text=True)

        if proc.stdout:
            self._append_log(proc.stdout + "\n")
        if proc.stderr:
            self._append_log(proc.stderr + "\n")

        # Try to find ffmpeg after installation
        ff = self._find_ffmpeg_exe()
        if ff:
            # add to PATH for current session
            bin_dir = str(ff.parent)
            os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')
            self._append_log(f"ffmpeg found at {ff}. Added to PATH for this session.\n")
            return True

        self._append_log("ffmpeg still not found after installation. You may need to restart the GUI or add ffmpeg to PATH manually.\n")
        return False

    def _install_ffmpeg_and_start(self, csv_path, output_path):
        success = self._install_ffmpeg()
        if success:
            # Schedule start in the main thread
            self.after(0, lambda: self.start())
        else:
            self.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

    def _append_log(self, text: str):
        def append():
            self.log.insert(tk.END, text)
            self.log.see(tk.END)
        self.log.after(0, append)

    def _run_proc(self, cmd):
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            for line in self.proc.stdout:
                self._append_log(line)

            self.proc.wait()
            self._append_log(f"\nProcess exited with {self.proc.returncode}\n")
        except Exception as e:
            self._append_log(f"\nError running process: {e}\n")
        finally:
            self.proc = None
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def _run_processor(self, csv_path, output_path):
        try:
            # Clear any prior cancel request
            self.stop_event.clear()
            process_clips(csv_path, output_path, log_callback=lambda s: self._append_log(s), stop_event=self.stop_event)
            self._append_log("\nProcessing finished.\n")
        except Exception as e:
            self._append_log(f"\nError: {e}\n")
        finally:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.stop_event.clear()

    def start(self):
        csv_path = self.csv_path.get()
        output_path = self.output_path.get()

        if not Path(csv_path).exists():
            messagebox.showerror("Error", "Input CSV not found")
            return

        # Ensure ffmpeg is available (or offer to install it)
        ff = self._find_ffmpeg_exe()
        if ff is None:
            if messagebox.askyesno("ffmpeg not found", "ffmpeg not found. Install via winget now?"):
                # Run installer in background and start after install
                self._append_log("User agreed to install ffmpeg. Installing...\n")
                threading.Thread(target=self._install_ffmpeg_and_start, args=(csv_path, output_path), daemon=True).start()
                return
            else:
                messagebox.showerror("ffmpeg required", "ffmpeg is required to download partial clips. Aborting.")
                return
        else:
            # Ensure ffmpeg directory is on PATH for subprocesses (so yt-dlp/ffmpeg can be found)
            os.environ['PATH'] = str(ff.parent) + os.pathsep + os.environ.get('PATH', '')

        # UI state
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log.delete(1.0, tk.END)
        self._append_log("Starting processing...\n\n")

        # Start processing in a background thread (merged processor)
        self.proc_thread = threading.Thread(target=self._run_processor, args=(csv_path, output_path), daemon=True)
        self.proc_thread.start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self._append_log("\nTermination requested.\n")
            except Exception as e:
                self._append_log(f"\nError terminating process: {e}\n")
        elif self.proc_thread and self.proc_thread.is_alive():
            # Signal the running processor thread to stop
            self.stop_event.set()
            self._append_log("\nCancellation requested. Current download will finish and then stop.\n")
        else:
            self._append_log("\nNo running process.\n")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
