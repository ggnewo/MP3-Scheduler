import pygame
import time
import random
import os
import threading
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class MP3SchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3 Scheduler")
        self.root.resizable(False, False)

        self.selected_path = tk.StringVar()
        self.selection_mode = tk.StringVar(value="file")  # "file" or "folder"

        self.mode = tk.StringVar(value="specific")  # "specific", "random", "now"
        self.specific_time = tk.StringVar()
        self.random_start = tk.StringVar()
        self.random_end = tk.StringVar()

        self.stop_flag = False  # lets us cancel a wait in progress
        self.target_time = None  # set while a wait is in progress, used for countdown

        # Options
        self.show_countdown_var = tk.BooleanVar(value=True)
        self.dark_mode_var = tk.BooleanVar(value=False)

        self.light_colors = {"bg": "#f0f0f0", "fg": "#000000", "entry_bg": "#ffffff"}
        self.dark_colors = {"bg": "#2b2b2b", "fg": "#e0e0e0", "entry_bg": "#3c3c3c"}

        self.style = ttk.Style()
        self._build_menu()
        self._build_ui()
        self.mode.trace_add("write", lambda *args: self.update_mode_ui())
        self.apply_theme()

        # Size the window to fit its actual content instead of a guessed fixed size
        self.root.update_idletasks()
        req_w = max(480, self.root.winfo_reqwidth())
        req_h = self.root.winfo_reqheight()
        self.root.geometry(f"{req_w}x{req_h}")

    # ---------------- Menu ----------------

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_checkbutton(
            label="Show countdown timer",
            variable=self.show_countdown_var,
            command=self.on_countdown_toggle,
        )
        options_menu.add_checkbutton(
            label="Dark mode",
            variable=self.dark_mode_var,
            command=self.apply_theme,
        )
        menubar.add_cascade(label="Options", menu=options_menu)

        self.root.config(menu=menubar)

    # ---------------- UI ----------------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # File / folder picker
        self.file_frame = ttk.LabelFrame(self.root, text="MP3 Source")
        self.file_frame.pack(fill="x", **pad)

        ttk.Entry(self.file_frame, textvariable=self.selected_path, width=45).pack(
            anchor="w", padx=8, pady=(8, 2)
        )

        browse_row = ttk.Frame(self.file_frame)
        browse_row.pack(anchor="w", padx=8, pady=(0, 4))
        ttk.Button(browse_row, text="Browse File...", command=self.browse_file).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(browse_row, text="Browse Folder...", command=self.browse_folder).pack(
            side="left"
        )

        self.source_hint_var = tk.StringVar(value="")
        ttk.Label(self.file_frame, textvariable=self.source_hint_var).pack(
            anchor="w", padx=8, pady=(0, 8)
        )

        # Mode selector — order: specific time, random, now
        self.mode_frame = ttk.LabelFrame(self.root, text="When to Play")
        self.mode_frame.pack(fill="x", **pad)

        ttk.Radiobutton(
            self.mode_frame, text="At a specific time (HH:MM:SS, 24hr)",
            variable=self.mode, value="specific", command=self.update_mode_ui
        ).pack(anchor="w", padx=8, pady=(8, 2))
        self.specific_entry = ttk.Entry(self.mode_frame, textvariable=self.specific_time, width=15)
        self.specific_entry.pack(anchor="w", padx=28, pady=(0, 6))

        ttk.Radiobutton(
            self.mode_frame, text="Random time within a range", variable=self.mode,
            value="random", command=self.update_mode_ui
        ).pack(anchor="w", padx=8, pady=2)

        range_row = ttk.Frame(self.mode_frame)
        range_row.pack(anchor="w", padx=28, pady=(0, 8))
        ttk.Label(range_row, text="From:").grid(row=0, column=0, padx=(0, 4))
        self.random_start_entry = ttk.Entry(range_row, textvariable=self.random_start, width=10)
        self.random_start_entry.grid(row=0, column=1, padx=(0, 10))
        ttk.Label(range_row, text="To:").grid(row=0, column=2, padx=(0, 4))
        self.random_end_entry = ttk.Entry(range_row, textvariable=self.random_end, width=10)
        self.random_end_entry.grid(row=0, column=3)

        ttk.Radiobutton(
            self.mode_frame, text="Play now", variable=self.mode, value="now",
            command=self.update_mode_ui
        ).pack(anchor="w", padx=8, pady=(2, 8))

        # Controls
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", **pad)

        self.schedule_btn = ttk.Button(
            control_frame, text="Schedule", command=self.on_schedule
        )
        self.schedule_btn.pack(side="left", padx=(0, 8))

        self.cancel_btn = ttk.Button(
            control_frame, text="Cancel", command=self.on_cancel, state="disabled"
        )
        self.cancel_btn.pack(side="left")

        # Status
        self.status_frame = ttk.LabelFrame(self.root, text="Status")
        self.status_frame.pack(fill="x", **pad)

        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(self.status_frame, textvariable=self.status_var, wraplength=440, justify="left").pack(
            anchor="w", padx=8, pady=8
        )

        self.update_mode_ui()

    def update_mode_ui(self):
        mode = self.mode.get()
        self.specific_entry.configure(
            state="normal" if mode == "specific" else "disabled"
        )
        state = "normal" if mode == "random" else "disabled"
        self.random_start_entry.configure(state=state)
        self.random_end_entry.configure(state=state)

        # Change button label depending on mode
        self.schedule_btn.configure(text="Play" if mode == "now" else "Schedule")

    # ---------------- Options ----------------

    def on_countdown_toggle(self):
        # If we're mid-wait and countdown was just turned off, clear the live text
        # back to a static message; if turned on, the next tick will pick it up.
        if not self.show_countdown_var.get() and self.target_time is not None:
            self.set_status(f"Waiting until {self.target_time.strftime('%H:%M:%S')}...")

    def apply_theme(self):
        dark = self.dark_mode_var.get()
        colors = self.dark_colors if dark else self.light_colors

        theme = "clam"
        self.style.theme_use(theme)

        self.style.configure(".", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TFrame", background=colors["bg"])
        self.style.configure("TLabelframe", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TLabel", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TRadiobutton", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TCheckbutton", background=colors["bg"], foreground=colors["fg"])
        self.style.configure("TButton", background=colors["bg"], foreground=colors["fg"])
        self.style.configure(
            "TEntry",
            fieldbackground=colors["entry_bg"],
            foreground=colors["fg"],
            insertcolor=colors["fg"],
        )
        self.style.map(
            "TRadiobutton",
            background=[("active", colors["bg"])],
            foreground=[("active", colors["fg"])],
        )

        self.root.configure(background=colors["bg"])

    # ---------------- Helpers ----------------

    def browse_file(self):
        path = filedialog.askopenfilename(
            title="Select an MP3 file",
            filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")],
        )
        if path:
            self.selected_path.set(path)
            self.selection_mode.set("file")
            self.source_hint_var.set("")

    def browse_folder(self):
        path = filedialog.askdirectory(title="Select a folder of MP3s")
        if path:
            self.selected_path.set(path)
            self.selection_mode.set("folder")
            self.source_hint_var.set("A random MP3 from this folder will be picked at play time.")

    def find_mp3s_in_folder(self, folder):
        try:
            files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith(".mp3")
            ]
        except OSError as e:
            raise ValueError(f"Couldn't read folder: {e}")
        return files

    def set_status(self, message):
        self.status_var.set(message)

    def parse_clock(self, text):
        """Parse HH:MM:SS into a time object, raises ValueError if invalid."""
        return datetime.strptime(text.strip(), "%H:%M:%S").time()

    def compute_target_time(self):
        """Returns a datetime for when to play, based on the selected mode.
        Raises ValueError with a user-facing message on bad input."""
        mode = self.mode.get()
        now = datetime.now()

        if mode == "now":
            return now

        if mode == "specific":
            text = self.specific_time.get()
            if not text.strip():
                raise ValueError("Enter a time in HH:MM:SS format.")
            clock = self.parse_clock(text)
            target = datetime.combine(now.date(), clock)
            if target <= now:
                target += timedelta(days=1)
            return target

        if mode == "random":
            start_text = self.random_start.get()
            end_text = self.random_end.get()
            if not start_text.strip() or not end_text.strip():
                raise ValueError("Enter both a start and end time in HH:MM:SS format.")

            entry_time = now
            start_clock = self.parse_clock(start_text)
            end_clock = self.parse_clock(end_text)

            start = datetime.combine(entry_time.date(), start_clock)
            end = datetime.combine(entry_time.date(), end_clock)

            if end <= start:
                end += timedelta(days=1)
            if end <= entry_time:
                start += timedelta(days=1)
                end += timedelta(days=1)
            if start <= entry_time:
                start = entry_time

            seconds_range = (end - start).total_seconds()
            random_offset = random.uniform(0, seconds_range)
            return start + timedelta(seconds=random_offset)

        raise ValueError("Unknown mode.")

    def display_name(self, path):
        """Just the file name, no folder path and no .mp3 extension."""
        name = os.path.basename(path)
        if name.lower().endswith(".mp3"):
            name = name[:-4]
        return name

    def format_remaining(self, seconds):
        seconds = max(0, int(seconds))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # ---------------- Scheduling / playback ----------------

    def on_schedule(self):
        source = self.selected_path.get().strip()
        if not source:
            messagebox.showerror("No source", "Please select an MP3 file or folder first.")
            return

        if self.selection_mode.get() == "folder":
            mp3s = self.find_mp3s_in_folder(source) if os.path.isdir(source) else []
            if not mp3s:
                messagebox.showerror("Empty folder", "That folder has no MP3 files in it.")
                return
        else:
            if not os.path.isfile(source):
                messagebox.showerror("File not found", "That file doesn't exist.")
                return

        try:
            target_time = self.compute_target_time()
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return

        self.stop_flag = False
        self.target_time = target_time
        self.schedule_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        if self.mode.get() == "now":
            if self.selection_mode.get() == "file":
                self.set_status(f"Playing: {self.display_name(source)}")
            else:
                self.set_status("Playing now...")
        elif self.show_countdown_var.get():
            self.set_status(f"Waiting... {self.format_remaining((target_time - datetime.now()).total_seconds())} remaining")
        else:
            self.set_status(f"Waiting until {target_time.strftime('%H:%M:%S')}...")

        thread = threading.Thread(
            target=self.run_schedule, args=(source, target_time), daemon=True
        )
        thread.start()

    def on_cancel(self):
        self.stop_flag = True
        self.set_status("Cancelling...")

    def run_schedule(self, source, target_time):
        last_tick = 0.0
        # Wait loop, checking the cancel flag periodically
        while True:
            if self.stop_flag:
                self.root.after(0, self.finish_cancelled)
                return

            now = datetime.now()
            if now >= target_time:
                break

            remaining = (target_time - now).total_seconds()

            # Refresh the countdown roughly once a second, not every 0.5s tick
            if self.show_countdown_var.get() and (time.monotonic() - last_tick) >= 1.0:
                last_tick = time.monotonic()
                self.root.after(0, lambda r=remaining: self.set_status(f"Waiting... {self.format_remaining(r)} remaining"))

            time.sleep(min(remaining, 0.5))

        # Resolve the actual file to play now, in case it's a folder pick
        if self.selection_mode.get() == "folder":
            mp3s = self.find_mp3s_in_folder(source)
            if not mp3s:
                self.root.after(0, lambda: messagebox.showerror("Empty folder", "That folder has no MP3 files in it."))
                self.root.after(0, self.finish_cancelled)
                return
            path = random.choice(mp3s)
        else:
            path = source

        name = self.display_name(path)
        self.root.after(0, lambda: self.set_status(f"Playing: {name}"))
        self.play_mp3(path)
        self.root.after(0, self.finish_played)

    def play_mp3(self, path):
        pygame.mixer.init()
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self.stop_flag:
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.1)
        except pygame.error as e:
            self.root.after(0, lambda: messagebox.showerror("Playback error", str(e)))
        finally:
            pygame.mixer.quit()

    def finish_played(self):
        self.target_time = None
        self.set_status("Idle.")
        self.schedule_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def finish_cancelled(self):
        self.target_time = None
        self.set_status("Idle.")
        self.schedule_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = MP3SchedulerApp(root)
    root.mainloop()