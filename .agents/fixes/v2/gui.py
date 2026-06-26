import os
import sys
import queue
import threading
import subprocess

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
except Exception as e:
    raise SystemExit(
        "customtkinter is required. Install dependencies first:\n"
        "    pip install -r requirements.txt\n\n"
        f"(import error: {e})"
    )

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ORGANIZER = os.path.join(APP_DIR, "organize_folders.py")
sys.path.append(APP_DIR)

try:
    from organize_folders import load_api_keys, save_api_keys, API_KEYS_PATH
except Exception:
    API_KEYS_PATH = os.path.join(APP_DIR, "api_keys.txt")

    def load_api_keys(path=API_KEYS_PATH):
        keys = {"subsource": "", "omdb": ""}
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith(";"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip().lower()
                            v = v.strip().strip('"').strip("'")
                            if k in keys:
                                keys[k] = v
        except Exception:
            pass
        return keys

    def save_api_keys(keys, path=API_KEYS_PATH):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"subsource = {keys.get('subsource', '')}\nomdb = {keys.get('omdb', '')}\n")
        return True


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MUTED = "#8b93a7"


class OrganizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ent Organizer - Movies & TV Wizard")
        self.geometry("900x700")
        self.minsize(820, 620)
        self.proc = None
        self.log_queue = queue.Queue()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color="#1f2430")
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(header, text="Ent Organizer",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(side="left", padx=20, pady=16)
        ctk.CTkLabel(header, text="Movies & TV  -  posters  -  info  -  subtitles",
                     text_color=MUTED).pack(side="left", pady=16)

        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.grid(row=1, column=0, sticky="ew", padx=16, pady=(14, 6))
        self.tab_org = self.tabs.add("Organize")
        self.tab_keys = self.tabs.add("API Keys")
        self._build_organize_tab()
        self._build_keys_tab()

        console_frame = ctk.CTkFrame(self, corner_radius=12)
        console_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(6, 6))
        console_frame.grid_rowconfigure(1, weight=1)
        console_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(console_frame, text="Console", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
        self.console = ctk.CTkTextbox(console_frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.console.grid(row=1, column=0, sticky="nsew", padx=12, pady=10)
        self.console.configure(state="disabled")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        bar.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(bar, text="Ready.", anchor="w", text_color=MUTED)
        self.status.grid(row=0, column=0, sticky="w")
        self.run_btn = ctk.CTkButton(bar, text="Run", width=150, height=40,
                                     font=ctk.CTkFont(size=15, weight="bold"), command=self.run)
        self.run_btn.grid(row=0, column=1, padx=(8, 0))

        self.after(120, self._drain_log)

    def _build_organize_tab(self):
        t = self.tab_org
        t.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(t, text="Target folder").grid(row=0, column=0, sticky="w", padx=12, pady=(14, 4))
        self.dir_entry = ctk.CTkEntry(t, placeholder_text="Pick the folder with your movies / shows...")
        self.dir_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12)
        ctk.CTkButton(t, text="Browse...", width=110, command=self.browse).grid(row=1, column=2, padx=12)

        opts = ctk.CTkFrame(t, fg_color="transparent")
        opts.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=12)
        self.var_dry = ctk.BooleanVar(value=False)
        self.var_icons = ctk.BooleanVar(value=False)
        self.var_subs = ctk.BooleanVar(value=False)
        self.var_farsi = ctk.BooleanVar(value=False)
        self.var_info = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="Dry run (preview only)", variable=self.var_dry).grid(row=0, column=0, padx=10, pady=6, sticky="w")
        ctk.CTkCheckBox(opts, text="Skip folder icons", variable=self.var_icons).grid(row=0, column=1, padx=10, pady=6, sticky="w")
        ctk.CTkCheckBox(opts, text="Skip English subs", variable=self.var_subs).grid(row=1, column=0, padx=10, pady=6, sticky="w")
        ctk.CTkCheckBox(opts, text="Skip Farsi subs", variable=self.var_farsi).grid(row=1, column=1, padx=10, pady=6, sticky="w")
        ctk.CTkCheckBox(opts, text="Skip info.txt", variable=self.var_info).grid(row=2, column=0, padx=10, pady=6, sticky="w")

        ctk.CTkLabel(
            t,
            text=("Movies and TV episodes (SxxExx) are auto-detected. TV is nested as\n"
                  "Series (Year) / Season 01 / Episode. Folder icons are square & move-safe."),
            justify="left", text_color=MUTED,
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

    def _build_keys_tab(self):
        t = self.tab_keys
        t.grid_columnconfigure(0, weight=1)
        keys = load_api_keys()
        ctk.CTkLabel(
            t,
            text=("These keys are saved to api_keys.txt on your PC only.\n"
                  "That file is gitignored and never uploaded to GitHub."),
            justify="left", text_color=MUTED,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(14, 8))
        ctk.CTkLabel(t, text="Subsource API key").grid(row=1, column=0, sticky="w", padx=12)
        self.subsource_entry = ctk.CTkEntry(t, show="*")
        self.subsource_entry.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 10))
        self.subsource_entry.insert(0, keys.get("subsource", ""))
        ctk.CTkLabel(t, text="OMDb API key  (free at omdbapi.com/apikey.aspx)").grid(row=3, column=0, sticky="w", padx=12)
        self.omdb_entry = ctk.CTkEntry(t, show="*")
        self.omdb_entry.grid(row=4, column=0, sticky="ew", padx=12, pady=(2, 10))
        self.omdb_entry.insert(0, keys.get("omdb", ""))
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.grid(row=5, column=0, sticky="w", padx=8, pady=6)
        ctk.CTkButton(row, text="Save keys", command=self.save_keys).grid(row=0, column=0, padx=8)
        self.show_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="Show", variable=self.show_var, command=self.toggle_show).grid(row=0, column=1, padx=8)
        self.keys_status = ctk.CTkLabel(t, text=f"File: {API_KEYS_PATH}", text_color=MUTED)
        self.keys_status.grid(row=6, column=0, sticky="w", padx=12, pady=6)

    def toggle_show(self):
        ch = "" if self.show_var.get() else "*"
        self.subsource_entry.configure(show=ch)
        self.omdb_entry.configure(show=ch)

    def save_keys(self):
        try:
            save_api_keys({"subsource": self.subsource_entry.get().strip(),
                           "omdb": self.omdb_entry.get().strip()})
            self.keys_status.configure(text="Saved to api_keys.txt.")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def browse(self):
        path = filedialog.askdirectory(title="Choose the folder to organize")
        if path:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, path)

    def _log(self, text):
        self.console.configure(state="normal")
        self.console.insert("end", text)
        self.console.see("end")
        self.console.configure(state="disabled")

    def _drain_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._log(line)
        except queue.Empty:
            pass
        self.after(120, self._drain_log)

    def run(self):
        if self.proc is not None:
            messagebox.showinfo("Busy", "A run is already in progress.")
            return
        target = self.dir_entry.get().strip()
        if not target or not os.path.isdir(target):
            messagebox.showwarning("Pick a folder", "Choose a valid target folder first.")
            return
        try:
            save_api_keys({"subsource": self.subsource_entry.get().strip(),
                           "omdb": self.omdb_entry.get().strip()})
        except Exception:
            pass
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        cmd = [sys.executable, ORGANIZER, "--dir", target]
        if self.var_dry.get():
            cmd.append("--dry-run")
        if self.var_icons.get():
            cmd.append("--skip-icons")
        if self.var_subs.get():
            cmd.append("--skip-subs")
        if self.var_farsi.get():
            cmd.append("--skip-farsi")
        if self.var_info.get():
            cmd.append("--skip-info")
        self.run_btn.configure(state="disabled", text="Running...")
        self.status.configure(text="Running...")
        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    def _worker(self, cmd):
        code = -1
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                cwd=APP_DIR, bufsize=1,
            )
            for line in self.proc.stdout:
                self.log_queue.put(line)
            self.proc.wait()
            code = self.proc.returncode
        except Exception as e:
            self.log_queue.put(f"\n[GUI] Failed to run organizer: {e}\n")
        finally:
            self.proc = None
            self.after(0, lambda: self._finish(code))

    def _finish(self, code):
        self.run_btn.configure(state="normal", text="Run")
        self.status.configure(text=f"Done (exit {code}).")


if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
