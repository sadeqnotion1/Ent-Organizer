import os
import sys
import shutil
import re
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk

# Set modern dark styling
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TextRedirector:
    """Helper to redirect stdout/stderr to a Tkinter Text widget safely in real-time."""
    def __init__(self, text_widget, queue_obj):
        self.text_widget = text_widget
        self.queue = queue_obj

    def write(self, string):
        self.queue.put(string)

    def flush(self):
        pass

class FolderOrganizerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window settings
        self.title("Folder Organizer & Poster Icon Wizard")
        self.geometry("960x660")
        self.minimum_size = (900, 600)
        self.minsize(900, 600)

        # Queue for real-time thread-safe logging
        self.log_queue = queue.Queue()
        self.is_running = False

        # Grid config
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Create sidebar
        self.create_sidebar()

        # Create main panel
        self.create_main_panel()

        # Load default directories
        self.load_defaults()

        # Start real-time log polling
        self.after(100, self.poll_log_queue)

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)

        # App Logo / Title
        self.logo_label = ctk.CTkLabel(
            self.sidebar, 
            text="🎬 FOLDER ORGANIZER\n   & POSTER WIZARD", 
            font=ctk.CTkFont(size=20, weight="bold"),
            justify="left"
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="w")

        # Description
        self.desc_label = ctk.CTkLabel(
            self.sidebar,
            text="Automated folder cleanup, IMDb poster downloader, custom circular icon set, and dual subtitle fetching.",
            font=ctk.CTkFont(size=12),
            wraplength=240,
            text_color="#8a8a8a",
            justify="left"
        )
        self.desc_label.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        # Utilities Card
        self.stats_frame = ctk.CTkFrame(self.sidebar, fg_color="#1d1e22", corner_radius=10)
        self.stats_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.stats_frame.grid_columnconfigure(0, weight=1)

        self.stats_title = ctk.CTkLabel(
            self.stats_frame,
            text="SYSTEM UTILITIES",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#3b8ed0"
        )
        self.stats_title.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        # Utilities Buttons
        self.fix_bg_btn = ctk.CTkButton(
            self.stats_frame,
            text="🧹 Clear Icon Cache (Fix BG)",
            fg_color="#2b2d30",
            hover_color="#3e4147",
            command=self.fix_explorer_cache,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.fix_bg_btn.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        self.refresh_btn = ctk.CTkButton(
            self.stats_frame,
            text="🔄 Explorer Shell Refresh",
            fg_color="#2b2d30",
            hover_color="#3e4147",
            command=self.send_shell_refresh,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.refresh_btn.grid(row=2, column=0, padx=15, pady=(5, 15), sticky="ew")

        # Theme Settings
        self.theme_label = ctk.CTkLabel(self.sidebar, text="Appearance Mode:", anchor="w")
        self.theme_label.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="w")
        self.theme_optionmenu = ctk.CTkOptionMenu(
            self.sidebar, 
            values=["Dark", "Light", "System"],
            command=self.change_appearance_mode_event
        )
        self.theme_optionmenu.grid(row=7, column=0, padx=20, pady=(5, 20), sticky="ew")

    def create_main_panel(self):
        self.main_panel = ctk.CTkFrame(self, fg_color="#18191d", corner_radius=0)
        self.main_panel.grid(row=0, column=1, sticky="nsew")
        self.main_panel.grid_columnconfigure(0, weight=1)
        self.main_panel.grid_rowconfigure(2, weight=1)

        # Paths Panel
        self.paths_card = ctk.CTkFrame(self.main_panel, corner_radius=12, fg_color="#1e2024")
        self.paths_card.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.paths_card.grid_columnconfigure(1, weight=1)

        # Directory selector
        self.movies_lbl = ctk.CTkLabel(self.paths_card, text="📂 Target Directory:", font=ctk.CTkFont(weight="bold"))
        self.movies_lbl.grid(row=0, column=0, padx=(15, 5), pady=(15, 5), sticky="w")
        self.movies_entry = ctk.CTkEntry(self.paths_card, font=ctk.CTkFont(size=13))
        self.movies_entry.grid(row=0, column=1, padx=5, pady=(15, 5), sticky="ew")
        self.movies_browse = ctk.CTkButton(self.paths_card, text="Browse", width=80, command=self.browse_movies)
        self.movies_browse.grid(row=0, column=2, padx=(5, 15), pady=(15, 5))

        # API Keys Panel
        self.api_lbl_row = ctk.CTkLabel(self.paths_card, text="🔑 API Keys Configuration:", font=ctk.CTkFont(weight="bold"))
        self.api_lbl_row.grid(row=1, column=0, padx=(15, 5), pady=(5, 5), sticky="w")
        
        self.subsource_entry = ctk.CTkEntry(self.paths_card, placeholder_text="Subsource API Key (For Subtitles)", font=ctk.CTkFont(size=12))
        self.subsource_entry.grid(row=1, column=1, padx=5, pady=(5, 5), sticky="ew")
        self.subsource_entry.insert(0, "sk_f09acde5b3891eac1fa07375cfde7910f2b82ecab83b3a308ed258b809ed4213")

        self.omdb_entry = ctk.CTkEntry(self.paths_card, placeholder_text="OMDb API Key (For Details)", font=ctk.CTkFont(size=12))
        self.omdb_entry.grid(row=1, column=2, padx=(5, 15), pady=(5, 5), sticky="ew")
        self.omdb_entry.insert(0, "trilogy")

        # Configuration Options Panel
        self.options_card = ctk.CTkFrame(self.main_panel, corner_radius=12, fg_color="#1e2024")
        self.options_card.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.options_card.grid_columnconfigure((0, 1, 2), weight=1)

        self.options_lbl = ctk.CTkLabel(
            self.options_card, 
            text="PIPELINE OPTIONS & COMPONENT SWITCHES", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#3b8ed0"
        )
        self.options_lbl.grid(row=0, column=0, columnspan=3, padx=15, pady=(12, 10), sticky="w")

        # Checkboxes
        self.opt_poster_icon = ctk.CTkCheckBox(self.options_card, text="⭐ Download & Set Folder Icon")
        self.opt_poster_icon.grid(row=1, column=0, padx=15, pady=(5, 15), sticky="w")
        self.opt_poster_icon.select()

        self.opt_info_txt = ctk.CTkCheckBox(self.options_card, text="📝 Query details & write info.txt")
        self.opt_info_txt.grid(row=1, column=1, padx=15, pady=(5, 15), sticky="w")
        self.opt_info_txt.select()

        self.opt_download_subs = ctk.CTkCheckBox(self.options_card, text="📥 Download English Subtitles")
        self.opt_download_subs.grid(row=1, column=2, padx=15, pady=(5, 15), sticky="w")
        self.opt_download_subs.select()

        self.opt_download_farsi = ctk.CTkCheckBox(self.options_card, text="📥 Download Farsi/Persian Subtitles")
        self.opt_download_farsi.grid(row=2, column=0, padx=15, pady=(5, 15), sticky="w")
        self.opt_download_farsi.select()

        # Terminal Console Output Area
        self.terminal_card = ctk.CTkFrame(self.main_panel, corner_radius=12, fg_color="#121316")
        self.terminal_card.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        self.terminal_card.grid_columnconfigure(0, weight=1)
        self.terminal_card.grid_rowconfigure(1, weight=1)

        self.term_lbl = ctk.CTkLabel(
            self.terminal_card, 
            text="REAL-TIME DIAGNOSTIC PIPELINE CONSOLE", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8a8a8a"
        )
        self.term_lbl.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        # Text Console
        self.console = tk.Text(
            self.terminal_card,
            bg="#121316",
            fg="#a8ffb2",
            insertbackground="white",
            relief="flat",
            borderwidth=0,
            font=("Consolas", 11)
        )
        self.console.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        
        # Scrollbar for console
        self.console_scroll = ctk.CTkScrollbar(self.terminal_card, command=self.console.yview)
        self.console_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 5), pady=(0, 15))
        self.console.config(yscrollcommand=self.console_scroll.set)

        # Control Panel / Run Buttons
        self.control_card = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.control_card.grid(row=3, column=0, padx=20, pady=(5, 20), sticky="ew")
        self.control_card.grid_columnconfigure(2, weight=1)

        self.revert_btn = ctk.CTkButton(
            self.control_card,
            text="🗑️ Revert Custom Icons",
            fg_color="#a82b2b",
            hover_color="#7a2020",
            width=160,
            command=self.revert_custom_icons,
            font=ctk.CTkFont(weight="bold")
        )
        self.revert_btn.grid(row=0, column=0, padx=(0, 10))

        self.dry_run_btn = ctk.CTkButton(
            self.control_card,
            text="🔬 Run dry-run scan",
            fg_color="#3e4147",
            hover_color="#4d5159",
            width=150,
            command=self.trigger_dry_run,
            font=ctk.CTkFont(weight="bold")
        )
        self.dry_run_btn.grid(row=0, column=1, padx=5)

        self.run_btn = ctk.CTkButton(
            self.control_card,
            text="⚡ Launch Organizer Pipeline",
            fg_color="#2ba84a",
            hover_color="#207a35",
            command=self.trigger_active_run,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.run_btn.grid(row=0, column=2, sticky="ew", padx=(10, 0))

    def load_defaults(self):
        self.movies_entry.insert(0, r"C:\Users\SadeQ\Videos\Ent\Movies")
        self.write_console("🎬 System initialized and ready for execution.\n")
        self.write_console("👉 Select directory, configure switches, and click Launch to organize!\n\n")

    def browse_movies(self):
        path = filedialog.askdirectory(title="Select Target Directory", initialdir=self.movies_entry.get())
        if path:
            self.movies_entry.delete(0, tk.END)
            self.movies_entry.insert(0, os.path.normpath(path))

    def write_console(self, text):
        self.console.config(state="normal")
        self.console.insert(tk.END, text)
        self.console.see(tk.END)
        self.console.config(state="disabled")

    def poll_log_queue(self):
        try:
            while True:
                string = self.log_queue.get_nowait()
                string_clean = string.replace("\r", "\n")
                self.write_console(string_clean)
                self.log_queue.task_done()
        except queue.Empty:
            pass
        self.after(50, self.poll_log_queue)

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

    def trigger_dry_run(self):
        if self.is_running:
            messagebox.showwarning("Busy", "The organizer wizard is already running in the background!")
            return
        self.run_pipeline(dry_run=True)

    def trigger_active_run(self):
        if self.is_running:
            messagebox.showwarning("Busy", "The organizer wizard is already running in the background!")
            return
        
        confirm = messagebox.askyesno(
            "Confirm Launch", 
            "Are you sure you want to run the Folder Organizer Pipeline on the target directory?"
        )
        if confirm:
            self.run_pipeline(dry_run=False)

    def run_pipeline(self, dry_run=False):
        self.is_running = True
        self.console.config(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.config(state="disabled")
        
        self.run_btn.configure(state="disabled", text="⚡ Execution in progress...")
        self.dry_run_btn.configure(state="disabled")
        self.revert_btn.configure(state="disabled")

        # Gather arguments
        target_dir = self.movies_entry.get()
        subsource_key = self.subsource_entry.get()
        omdb_key = self.omdb_entry.get()

        options = {
            'dir': target_dir,
            'dry_run': dry_run,
            'skip_icons': not self.opt_poster_icon.get(),
            'skip_info': not self.opt_info_txt.get(),
            'skip_subs': not self.opt_download_subs.get(),
            'skip_farsi': not self.opt_download_farsi.get(),
            'subsource_key': subsource_key,
            'omdb_key': omdb_key
        }

        # Run background thread
        thread = threading.Thread(target=self.execute_worker_thread, args=(options,))
        thread.daemon = True
        thread.start()

    def execute_worker_thread(self, options):
        # Redirect stdout and stderr thread-safely
        sys.stdout = TextRedirector(self.console, self.log_queue)
        sys.stderr = TextRedirector(self.console, self.log_queue)

        try:
            import organize_folders
            
            # Map options to organize_folders environment
            organize_folders.LOG_FILE_PATH = os.path.join(options['dir'], "folder_organizer.log")
            organize_folders.SUBSOURCE_API_KEY = options['subsource_key']
            organize_folders.OMDB_API_KEY = options['omdb_key']
            
            # Intercept args in sys.argv
            sys.argv = [
                "organize_folders.py",
                "--dir", options['dir'],
                "--subsource-key", options['subsource_key'],
                "--omdb-key", options['omdb_key']
            ]
            if options['dry_run']: sys.argv.append("--dry-run")
            if options['skip_icons']: sys.argv.append("--skip-icons")
            if options['skip_info']: sys.argv.append("--skip-info")
            if options['skip_subs']: sys.argv.append("--skip-subs")
            if options['skip_farsi']: sys.argv.append("--skip-farsi")
            
            original_exit = sys.exit
            sys.exit = lambda code=0: None
            
            try:
                organize_folders.main()
            finally:
                sys.exit = original_exit

        except Exception as e:
            self.log_queue.put(f"\n❌ GUI Engine execution crash: {e}\n")
            import traceback
            self.log_queue.put(f"{traceback.format_exc()}\n")
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__

            self.is_running = False
            self.run_btn.configure(state="normal", text="⚡ Launch Organizer Pipeline")
            self.dry_run_btn.configure(state="normal")
            self.revert_btn.configure(state="normal")
            self.log_queue.put("\n✔️ Finished Pipeline Execution Run!\n")

    def revert_custom_icons(self):
        if self.is_running:
            messagebox.showwarning("Busy", "The organizer wizard is currently running in the background!")
            return
            
        confirm = messagebox.askyesno(
            "Confirm Revert",
            "This will remove all custom circular folder icons from your movie directories. Are you sure?"
        )
        if not confirm:
            return

        self.console.config(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.config(state="disabled")
        
        self.is_running = True
        self.run_btn.configure(state="disabled")
        self.dry_run_btn.configure(state="disabled")
        self.revert_btn.configure(state="disabled", text="🗑️ Reverting icons...")

        def worker():
            sys.stdout = TextRedirector(self.console, self.log_queue)
            try:
                import core
                target_dir = self.movies_entry.get()
                self.log_queue.put(f"📂 Scanning subfolders inside: '{target_dir}' to revert icons...\n")
                
                subfolders = os.listdir(target_dir)
                count = 0
                for folder_name in subfolders:
                    folder_path = os.path.join(target_dir, folder_name)
                    if os.path.isdir(folder_path) and not folder_name.startswith('.'):
                        if core.remove_folder_icon(folder_path):
                            self.log_queue.put(f"  ✔️ Reverted custom icon for folder: '{folder_name}'\n")
                            count += 1
                
                core.refresh_explorer()
                self.log_queue.put(f"\n✔️ Revert completed successfully! Restored {count} folders to default Windows icons.\n")
            except Exception as e:
                self.log_queue.put(f"\n❌ Error during revert: {e}\n")
            finally:
                sys.stdout = sys.__stdout__
                self.is_running = False
                self.run_btn.configure(state="normal")
                self.dry_run_btn.configure(state="normal")
                self.revert_btn.configure(state="normal", text="🗑️ Revert Custom Icons")

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()

    def fix_explorer_cache(self):
        confirm = messagebox.askyesno(
            "Confirm Cache Clear",
            "This will kill Windows Explorer, delete all icon and thumbnail caches to fix the black background bug, and restart Explorer. Proceed?"
        )
        if not confirm:
            return
            
        def worker():
            sys.stdout = TextRedirector(self.console, self.log_queue)
            try:
                import core
                self.log_queue.put("🧹 Preparing to clean Windows icon caches...\n")
                self.log_queue.put("🔴 Killing explorer.exe...\n")
                core.clear_windows_cache()
                self.log_queue.put("🟢 Icon and thumbnail caches successfully cleared!\n")
            except Exception as e:
                self.log_queue.put(f"❌ Cache clear failed: {e}\n")
            finally:
                sys.stdout = sys.__stdout__

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()

    def send_shell_refresh(self):
        try:
            import core
            core.refresh_explorer()
            self.write_console("✔️ Sent shell refresh notification to redraw custom icons instantly!\n")
            messagebox.showinfo("Success", "Explorer shell refresh sent successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send refresh: {e}")

if __name__ == "__main__":
    app = FolderOrganizerGUI()
    app.mainloop()
