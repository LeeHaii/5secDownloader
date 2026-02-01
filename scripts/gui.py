import sys
import threading
import subprocess
import os
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

ROOT = Path(__file__).parent.parent


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("5Sec Downloader")
        self.geometry("800x520")

        self.csv_path = tk.StringVar(value=str(ROOT / "input" / "input.csv"))
        self.output_path = tk.StringVar(value=str(ROOT / "output"))

        self.proc = None
        self.proc_thread = None

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)

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
        credit_row = ttk.Frame(frm)
        credit_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(0,6))
        ttk.Label(credit_row, text="2025 TranDucThang 5-sec Donwloader").pack(side=tk.LEFT)
        fb_lbl = tk.Label(credit_row, text="Facebook", fg="blue", cursor="hand2")
        fb_lbl.pack(side=tk.RIGHT)
        fb_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://www.facebook.com/rhymx2k3/"))
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

    def start(self):
        csv_path = self.csv_path.get()
        output_path = self.output_path.get()

        if not Path(csv_path).exists():
            messagebox.showerror("Error", "Input CSV not found")
            return

        # Ensure ffmpeg is available (or offer to install it)
        if shutil.which('ffmpeg') is None:
            if messagebox.askyesno("ffmpeg not found", "ffmpeg not found on PATH. Install via winget now?"):
                # Run installer in background and start after install
                self._append_log("User agreed to install ffmpeg. Installing...\n")
                threading.Thread(target=self._install_ffmpeg_and_start, args=(csv_path, output_path), daemon=True).start()
                return
            else:
                messagebox.showerror("ffmpeg required", "ffmpeg is required to download partial clips. Aborting.")
                return

        # Choose python executable: .venv if present, else current interpreter
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            python_exe = str(venv_python)
        else:
            python_exe = sys.executable

        script = ROOT / "scripts" / "online_clip_processor.py"
        cmd = [python_exe, str(script), "--csv", csv_path, "--output", output_path]

        # UI state
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log.delete(1.0, tk.END)
        self._append_log(f"Starting: {' '.join(cmd)}\n\n")

        # Start background thread
        self.proc_thread = threading.Thread(target=self._run_proc, args=(cmd,), daemon=True)
        self.proc_thread.start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self._append_log("\nTermination requested.\n")
            except Exception as e:
                self._append_log(f"\nError terminating process: {e}\n")
        else:
            self._append_log("\nNo running process.\n")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
