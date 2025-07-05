import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk, font
import subprocess
import os
import threading
import sys
import multiprocessing
import re

# --- Constants and Configuration (unchanged) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_SCRIPTS_DIR = SCRIPT_DIR

FFMPEG_EXECUTABLE_PATH = os.path.join(VENV_SCRIPTS_DIR, "ffmpeg_binary", "bin", "ffmpeg.exe")
MODEL_CACHE_ROOT_DIR = os.path.join(VENV_SCRIPTS_DIR, "models")
PYTHON_EXECUTABLE = os.path.join(VENV_SCRIPTS_DIR, "python.exe")

AVAILABLE_MODELS_FROM_IMAGE = [
    "tiny.en", "tiny", "base.en", "base", "small.en", "small",
    "medium.en", "medium", "large-v1", "large-v2", "large-v3", "large-v3-turbo"
]
DEFAULT_MODEL = "small"

LANGUAGES_MAP = {
    "Auto Detect": "auto", "English": "en", "Spanish": "es", "French": "fr",
    "German": "de", "Italian": "it", "Japanese": "ja", "Chinese": "zh",
    "Russian": "ru", "Portuguese": "pt", "Afrikaans": "af", "Arabic": "ar",
    "Hindi": "hi", "Korean": "ko", "Turkish": "tr", "Ukrainian": "uk",
    "Czech": "cs", "Dutch": "nl", "Greek": "el", "Hungarian": "hu",
    "Indonesian": "id", "Malay": "ms", "Norwegian": "no", "Polish": "pl",
    "Swedish": "sv", "Thai": "th", "Vietnamese": "vi"
}
DEFAULT_LANGUAGE_DISPLAY_NAME = "English"
DEFAULT_NO_SPEECH_THRESHOLD = "0.6"
DEFAULT_MERGE_REPETITIONS = True
DEFAULT_USE_VAD = True
DEFAULT_VAD_THRESHOLD = "0.5"
DEFAULT_MIN_SPEECH_MS = "250"
DEFAULT_MIN_SILENCE_MS = "100"
try:
    _default_cpu_workers_val = os.cpu_count() // 2 if (os.cpu_count() or 0) > 1 else 1
    DEFAULT_NUM_WORKERS = str(_default_cpu_workers_val)
except NotImplementedError:
    DEFAULT_NUM_WORKERS = "1"

DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop")


class SubtitleApp:
    def __init__(self, master):
        self.master = master
        self.video_files = []
        
        self._configure_styles()
        self._create_widgets()
        self.check_paths()

    def _configure_styles(self):
        """Configure fonts, colors, and ttk styles for the application."""
        # Colors
        self.BG_COLOR = "#F5F5F5"
        self.FRAME_COLOR = "#FFFFFF"
        self.ACCENT_COLOR = "#0078D7"
        self.TEXT_COLOR = "#1F1F1F"
        self.SUBTLE_TEXT_COLOR = "#605E5C"
        self.BORDER_COLOR = "#D1D1D1"
        self.SUCCESS_COLOR = "#107C10"
        self.ERROR_COLOR = "#A80000"

        self.master.title("Auto Subtitle GUI (Portable) V2.2")
        self.master.geometry("750x950")
        self.master.minsize(650, 800)
        self.master.configure(bg=self.BG_COLOR)

        # Fonts
        self.default_font = font.nametofont("TkDefaultFont")
        self.default_font.configure(family="Segoe UI", size=10)
        self.title_font = font.Font(family="Segoe UI", size=12, weight="bold")
        self.label_font = font.Font(family="Segoe UI", size=10)

        # ttk Styles
        style = ttk.Style(self.master)
        style.theme_use('clam')

        style.configure("TFrame", background=self.BG_COLOR)
        style.configure("TLabel", background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=self.label_font)
        style.configure("TButton", font=self.label_font, padding=6, borderwidth=1, relief="solid", bordercolor=self.BORDER_COLOR, background="#FFFFFF")
        style.map("TButton", background=[('active', '#E1E1E1')])
        style.configure("Accent.TButton", foreground="white", background=self.ACCENT_COLOR, font=(self.label_font.cget("family"), self.label_font.cget("size"), "bold"), padding=8, borderwidth=0)
        style.map("Accent.TButton", background=[('active', '#005A9E')])
        style.configure("TLabelframe", background=self.BG_COLOR, bordercolor=self.BORDER_COLOR, font=self.title_font, relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=self.title_font)
        style.configure("TCheckbutton", background=self.BG_COLOR, font=self.label_font)
        style.configure("TEntry", fieldbackground=self.FRAME_COLOR, borderwidth=1, relief="solid")
        style.configure("TCombobox", fieldbackground=self.FRAME_COLOR, borderwidth=1, relief="solid")
        style.configure("Horizontal.TProgressbar", thickness=18, background=self.ACCENT_COLOR, troughcolor=self.FRAME_COLOR, borderwidth=1, relief="solid")

    def _create_widgets(self):
        """Create and layout all widgets in the main window."""
        main_frame = ttk.Frame(self.master, padding="15 15 15 15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- File Selection ---
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill=tk.X, pady=(0, 10))
        self.select_button = ttk.Button(file_frame, text="Select Video File(s)", command=self.select_files)
        self.select_button.pack(side=tk.LEFT, padx=(0, 5))
        self.clear_button = ttk.Button(file_frame, text="Clear List", command=self.clear_file_list)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        # --- File Listbox ---
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(pady=5, fill=tk.X)
        self.file_listbox_label = ttk.Label(list_frame, text="Selected Files:")
        self.file_listbox_label.pack(anchor=tk.W, pady=(5, 2))
        listbox_inner_frame = ttk.Frame(list_frame)
        listbox_inner_frame.pack(fill=tk.X, expand=True)
        scrollbar = ttk.Scrollbar(listbox_inner_frame, orient=tk.VERTICAL)
        self.file_listbox = tk.Listbox(listbox_inner_frame, selectmode=tk.EXTENDED, height=5, yscrollcommand=scrollbar.set,
                                       bg=self.FRAME_COLOR, relief=tk.SOLID, borderwidth=1, highlightthickness=0)
        scrollbar.config(command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # --- Options ---
        options_frame = ttk.LabelFrame(main_frame, text="Processing Options", padding="15 10 15 10")
        options_frame.pack(pady=(15, 10), fill=tk.X)
        options_frame.columnconfigure(1, weight=1)

        # Model
        ttk.Label(options_frame, text="Model:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.model_var = tk.StringVar(self.master, value=DEFAULT_MODEL)
        self.model_dropdown = ttk.Combobox(options_frame, textvariable=self.model_var, values=AVAILABLE_MODELS_FROM_IMAGE, state="readonly", width=25)
        self.model_dropdown.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5, columnspan=2)

        # Language
        ttk.Label(options_frame, text="Source Language:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.language_var = tk.StringVar(self.master, value=DEFAULT_LANGUAGE_DISPLAY_NAME)
        self.language_dropdown = ttk.Combobox(options_frame, textvariable=self.language_var, values=list(LANGUAGES_MAP.keys()), state="readonly")
        self.language_dropdown.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5, columnspan=2)

        # Task Selection
        ttk.Label(options_frame, text="Task:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.task_var = tk.StringVar(self.master, value="Translate")
        self.task_dropdown = ttk.Combobox(options_frame, textvariable=self.task_var, values=["Transcribe", "Translate"], state="readonly")
        self.task_dropdown.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        ttk.Label(options_frame, text="(Translate Option is to English)", foreground=self.SUBTLE_TEXT_COLOR).grid(row=2, column=2, sticky=tk.W, padx=5, pady=5)

        # No Speech Threshold
        ttk.Label(options_frame, text="No Speech Threshold:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.no_speech_threshold_var = tk.StringVar(self.master, value=DEFAULT_NO_SPEECH_THRESHOLD)
        self.no_speech_threshold_entry = ttk.Entry(options_frame, textvariable=self.no_speech_threshold_var, width=12)
        self.no_speech_threshold_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(options_frame, text="(0.0-1.0, lower = more strict)", foreground=self.SUBTLE_TEXT_COLOR).grid(row=3, column=2, sticky=tk.W, padx=5, pady=5)

        # Merge Repetitions
        self.merge_repetitions_var = tk.BooleanVar(self.master, value=DEFAULT_MERGE_REPETITIONS)
        self.merge_repetitions_checkbox = ttk.Checkbutton(options_frame, text="Merge Repetitive Segments", variable=self.merge_repetitions_var)
        self.merge_repetitions_checkbox.grid(row=4, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)

        # Use VAD
        self.use_vad_var = tk.BooleanVar(self.master, value=DEFAULT_USE_VAD)
        self.use_vad_checkbox = ttk.Checkbutton(options_frame, text="Use Voice Activity Detection (VAD)", variable=self.use_vad_var, command=self.toggle_vad_options)
        self.use_vad_checkbox.grid(row=5, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)

        # VAD Options Frame
        self.vad_options_frame = ttk.Frame(options_frame, padding="20 5 5 5")
        self.vad_options_frame.grid(row=6, column=0, columnspan=3, sticky=tk.EW)
        
        ttk.Label(self.vad_options_frame, text="VAD Threshold:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.vad_threshold_var = tk.StringVar(self.master, value=DEFAULT_VAD_THRESHOLD)
        self.vad_threshold_entry = ttk.Entry(self.vad_options_frame, textvariable=self.vad_threshold_var, width=7)
        self.vad_threshold_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(self.vad_options_frame, text="Min Speech (ms):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.min_speech_duration_ms_var = tk.StringVar(self.master, value=DEFAULT_MIN_SPEECH_MS)
        self.min_speech_duration_ms_entry = ttk.Entry(self.vad_options_frame, textvariable=self.min_speech_duration_ms_var, width=7)
        self.min_speech_duration_ms_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(self.vad_options_frame, text="Min Silence (ms):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.min_silence_duration_ms_var = tk.StringVar(self.master, value=DEFAULT_MIN_SILENCE_MS)
        self.min_silence_duration_ms_entry = ttk.Entry(self.vad_options_frame, textvariable=self.min_silence_duration_ms_var, width=7)
        self.min_silence_duration_ms_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        # CPU Workers
        max_cores = os.cpu_count() or 1
        self.num_workers_label = ttk.Label(options_frame, text="CPU Workers:")
        self.num_workers_label.grid(row=7, column=0, sticky=tk.W, padx=5, pady=5)
        self.num_workers_var = tk.StringVar(self.master, value=str(min(int(DEFAULT_NUM_WORKERS), max_cores)))
        self.num_workers_spinbox = ttk.Spinbox(options_frame, from_=0, to=max_cores, textvariable=self.num_workers_var, width=5, state="readonly")
        self.num_workers_spinbox.grid(row=7, column=1, sticky=tk.W, padx=5, pady=5)
        self.num_workers_tooltip_label = ttk.Label(options_frame, text=f"(0=auto, max {max_cores})", foreground=self.SUBTLE_TEXT_COLOR)
        self.num_workers_tooltip_label.grid(row=7, column=2, sticky=tk.W, padx=5, pady=5)

        # Output Directory
        ttk.Label(options_frame, text="Output Directory:").grid(row=8, column=0, sticky=tk.W, padx=5, pady=10)
        self.output_dir_var = tk.StringVar(self.master, value=DEFAULT_OUTPUT_DIR)
        self.output_dir_entry = ttk.Entry(options_frame, textvariable=self.output_dir_var, state="readonly")
        self.output_dir_entry.grid(row=8, column=1, sticky=tk.EW, padx=5, pady=10)
        self.output_dir_button = ttk.Button(options_frame, text="Browse...", command=self.select_output_dir)
        self.output_dir_button.grid(row=8, column=2, sticky=tk.EW, padx=5, pady=10)
        
        # --- Start Button ---
        self.start_button = ttk.Button(main_frame, text="Start Processing", command=self.start_processing_thread, style="Accent.TButton")
        self.start_button.pack(pady=15, ipady=5, ipadx=10)
        
        # --- Progress Bars ---
        progress_frame = ttk.Frame(main_frame, padding="0 10 0 0")
        progress_frame.pack(fill=tk.X, expand=False, pady=5)
        progress_frame.columnconfigure(1, weight=1)

        self.file_progress_label = ttk.Label(progress_frame, text="File Progress:")
        self.file_progress_label.grid(row=0, column=0, sticky=tk.W, padx=(0,10))
        self.file_progress = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate', style="Horizontal.TProgressbar")
        self.file_progress.grid(row=0, column=1, sticky=tk.EW)
        self.file_progress_percent_label = ttk.Label(progress_frame, text="0%", width=10, anchor=tk.E)
        self.file_progress_percent_label.grid(row=0, column=2, sticky=tk.W, padx=(10,0))

        self.overall_progress_label = ttk.Label(progress_frame, text="Overall Progress:")
        self.overall_progress_label.grid(row=1, column=0, sticky=tk.W, padx=(0,10), pady=(5,0))
        self.overall_progress = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate', style="Horizontal.TProgressbar")
        self.overall_progress.grid(row=1, column=1, sticky=tk.EW, pady=(5,0))
        self.overall_progress_count_label = ttk.Label(progress_frame, text="0 / 0", width=10, anchor=tk.E)
        self.overall_progress_count_label.grid(row=1, column=2, sticky=tk.W, padx=(10,0), pady=(5,0))

        # --- Log Output ---
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        self.log_label = ttk.Label(log_frame, text="Summary Log:")
        self.log_label.pack(anchor=tk.W, pady=(5, 2))
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state=tk.DISABLED, wrap=tk.WORD, relief=tk.SOLID,
                                                  borderwidth=1, font=("Courier New", 9), bg=self.FRAME_COLOR)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Final setup
        self.toggle_vad_options()

    def _update_ui_progress(self, file_percent, overall_val, overall_max):
        """Thread-safe method to update progress bars."""
        if file_percent is not None:
            self.file_progress['value'] = file_percent
            self.file_progress_percent_label.config(text=f"{int(file_percent)}%")
        
        if overall_val is not None and overall_max is not None:
            self.overall_progress['maximum'] = overall_max
            self.overall_progress['value'] = overall_val
            self.overall_progress_count_label.config(text=f"{overall_val} / {overall_max}")
        
        self.master.update_idletasks()
        
    def toggle_vad_options(self):
        """Enable or disable VAD-related options based on the checkbox."""
        is_vad_enabled = self.use_vad_var.get()
        new_state = tk.NORMAL if is_vad_enabled else tk.DISABLED
        spinbox_state = "readonly" if is_vad_enabled else tk.DISABLED
        
        for widget in self.vad_options_frame.winfo_children():
            if isinstance(widget, (ttk.Entry, ttk.Label)):
                widget.config(state=new_state)
        
        self.num_workers_label.config(state=new_state)
        self.num_workers_spinbox.config(state=spinbox_state)
        self.num_workers_tooltip_label.config(state=new_state)

    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select SRT Output Directory", initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)
            self.log_message(f"SRT output directory set to: {directory}")

    def check_paths(self):
        paths_ok = True
        if not os.path.isfile(PYTHON_EXECUTABLE):
            self.log_message(f"ERROR: Python executable not found: {PYTHON_EXECUTABLE}", self.ERROR_COLOR)
            paths_ok = False
        if not os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            self.log_message(f"ERROR: FFMPEG not found: {FFMPEG_EXECUTABLE_PATH}", self.ERROR_COLOR)
            paths_ok = False
        else:
            self.log_message(f"INFO: Using FFMPEG from: {FFMPEG_EXECUTABLE_PATH}", self.SUCCESS_COLOR)
        
        if not paths_ok:
            self.start_button.config(state=tk.DISABLED)
            messagebox.showerror("Path Error", "Critical files like python.exe or ffmpeg.exe are missing. Check the application structure.")
        else:
            self.log_message("Initial path checks OK.", self.SUCCESS_COLOR)

    def log_message(self, message, color=None):
        """Logs a message to the ScrolledText widget in a thread-safe way."""
        def _update_log():
            self.log_text.config(state=tk.NORMAL)
            if color:
                tag_name = f"color_{color.replace('#', '')}"
                self.log_text.tag_configure(tag_name, foreground=color)
                self.log_text.insert(tk.END, message + "\n", tag_name)
            else:
                self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.master.after(0, _update_log)

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=(("Video files", "*.avi *.mp4 *.mkv *.mov *.webm"), ("All files", "*.*"))
        )
        if files:
            for f_path in files:
                if f_path not in self.video_files:
                    self.video_files.append(f_path)
            self.update_file_listbox()

    def clear_file_list(self):
        self.video_files.clear()
        self.update_file_listbox()
        self.log_message("Cleared selected files list.")

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for f_path in self.video_files:
            self.file_listbox.insert(tk.END, os.path.basename(f_path))

    def set_ui_state(self, state):
        """Enable or disable UI elements during processing."""
        element_state = tk.NORMAL if state == "normal" else tk.DISABLED
        combobox_state = "readonly" if state == "normal" else tk.DISABLED
        
        for button in [self.select_button, self.clear_button, self.start_button, self.output_dir_button]:
            button.config(state=element_state)

        for checkbox in [self.merge_repetitions_checkbox, self.use_vad_checkbox]:
            checkbox.config(state=element_state)

        for combobox in [self.model_dropdown, self.language_dropdown, self.task_dropdown]:
            combobox.config(state=combobox_state)
            
        self.no_speech_threshold_entry.config(state=element_state)

        if state == "normal":
            self.toggle_vad_options()
        else:
            for widget in self.vad_options_frame.winfo_children():
                widget.config(state=tk.DISABLED)
            self.num_workers_label.config(state=tk.DISABLED)
            self.num_workers_spinbox.config(state=tk.DISABLED)
            self.num_workers_tooltip_label.config(state=tk.DISABLED)

    def start_processing_thread(self):
        if not self.video_files:
            messagebox.showwarning("No Files", "Please select at least one video file.")
            return
        try:
            float(self.no_speech_threshold_var.get())
            if self.use_vad_var.get(): float(self.vad_threshold_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Threshold values must be valid numbers.")
            return

        self.set_ui_state("disabled")
        self.log_message("="*60, self.ACCENT_COLOR)
        self.log_message("Starting video processing...", self.ACCENT_COLOR)
        self.log_message("Detailed real-time progress is shown in the console/terminal window.", self.SUBTLE_TEXT_COLOR)
        
        thread = threading.Thread(target=self.process_videos_sequentially, daemon=True)
        thread.start()

    def process_videos_sequentially(self):
        all_successful = True
        num_files = len(self.video_files)
        self.master.after(0, self._update_ui_progress, 0, 0, num_files)
        
        for i, video_file_path in enumerate(self.video_files):
            self.log_message(f"\nProcessing file {i+1}/{num_files}: {os.path.basename(video_file_path)}", self.ACCENT_COLOR)
            
            print("\n" + "="*80)
            print(f"--> Starting file {i+1}/{num_files}: {os.path.basename(video_file_path)}")
            print("="*80)
            
            # Reset per-file progress and state
            self.master.after(0, self._update_ui_progress, 0, None, None)
            is_single_chunk_mode = None  # None: undetermined, True: single-chunk (time), False: multi-chunk
            processed_chunks = 0
            total_chunks = 0

            # --- UPDATED: Build the command conditionally ---
            command = [
                PYTHON_EXECUTABLE, "-u", "-m", "auto_subtitle.cli", video_file_path,
                "--task", self.task_var.get().lower(),
                "--model", self.model_var.get(),
                "--language", LANGUAGES_MAP.get(self.language_var.get(), "en"),
                "--output_dir", self.output_dir_var.get(),
                "--srt_only", "True",
                "--output_srt", "True",
                "--verbose", "True", # Keep verbose for progress parsing
                "--ffmpeg_executable_path", FFMPEG_EXECUTABLE_PATH,
                "--model_download_root", MODEL_CACHE_ROOT_DIR,
                "--no_speech_threshold", self.no_speech_threshold_var.get(),
                "--merge_repetitive_segments", str(self.merge_repetitions_var.get())
            ]

            user_wants_vad = self.use_vad_var.get()
            if user_wants_vad:
                self.log_message("INFO: VAD is enabled. Using specified VAD settings.")
                command.extend([
                    "--use_vad", "True",
                    "--vad_threshold", self.vad_threshold_var.get(),
                    "--min_speech_duration_ms", self.min_speech_duration_ms_var.get(),
                    "--min_silence_duration_ms", self.min_silence_duration_ms_var.get(),
                    "--num_workers", self.num_workers_var.get()
                ])
            else:
                self.log_message("INFO: VAD is disabled. Simulating a single audio chunk to ensure progress reporting.", self.SUBTLE_TEXT_COLOR)
                # Force VAD with parameters that treat the whole file as one chunk
                command.extend([
                    "--use_vad", "True",
                    "--vad_threshold", "0.1",
                    "--min_speech_duration_ms", "10",
                    "--min_silence_duration_ms", "60000000", # Impossibly high silence duration
                    "--num_workers", "1"
                ])
            # --- END OF UPDATE ---

            try:
                process_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    bufsize=1, cwd=VENV_SCRIPTS_DIR, creationflags=process_flags,
                    encoding='utf-8', errors='replace'
                )
                
                for raw_line in iter(process.stdout.readline, ''):
                    line = raw_line.rstrip()
                    final_part = line.split('\r')[-1]
                    if final_part:
                        print(final_part, flush=True)

                        # --- UPDATED: Intelligent Progress Parsing ---
                        # State machine: First, determine the mode (single vs multi-chunk)
                        if is_single_chunk_mode is None:
                            total_chunks_match = re.search(r'VAD found (\d+) speech segments', final_part)
                            if total_chunks_match:
                                total_chunks = int(total_chunks_match.group(1))
                                if total_chunks == 1:
                                    is_single_chunk_mode = True
                                    self.log_message("INFO: Processing as a single segment. Progress will be time-based.")
                                    self.master.after(0, self.file_progress.config, {'maximum': 100, 'value': 0})
                                elif total_chunks > 1:
                                    is_single_chunk_mode = False
                                    self.log_message(f"INFO: VAD detected {total_chunks} speech segments.")
                                    self.master.after(0, self.file_progress.config, {'maximum': total_chunks, 'value': 0})
                                    self.master.after(0, self.file_progress_percent_label.config, {'text': f"0 / {total_chunks}"})

                        # Now, parse progress based on the determined mode
                        if is_single_chunk_mode is True:
                            progress_match = re.search(r'([\d\.]+)/([\d\.]+)[\s\[]', final_part)
                            if progress_match:
                                current_val = float(progress_match.group(1))
                                total_val = float(progress_match.group(2))
                                if total_val > 0:
                                    percent = (current_val / total_val) * 100
                                    self.master.after(0, self._update_ui_progress, percent, None, None)
                        
                        elif is_single_chunk_mode is False:
                            if 'Transcription finished for VAD chunk' in final_part:
                                processed_chunks += 1
                                if total_chunks > 0:
                                    self.master.after(0, self.file_progress.config, {'value': processed_chunks})
                                    self.master.after(0, self.file_progress_percent_label.config, {'text': f"{processed_chunks} / {total_chunks}"})
                        
                        # Independent language detection
                        lang_detect_match = re.search(r'INFO: Detected language: (\w+)', final_part)
                        if lang_detect_match:
                            detected_language = lang_detect_match.group(1)
                            self.log_message(f"INFO: Auto-detected language as: {detected_language.capitalize()}", self.SUCCESS_COLOR)
                        # --- END OF UPDATE ---

                process.stdout.close()
                return_code = process.wait()
                print() 
                
                if return_code == 0:
                    self.log_message(f"Successfully processed {os.path.basename(video_file_path)}.", self.SUCCESS_COLOR)
                    self.master.after(0, self._update_ui_progress, 100, i + 1, num_files)
                    
                    try:
                        video_basename = os.path.splitext(os.path.basename(video_file_path))[0]
                        srt_filename = f"{video_basename}.srt"
                        srt_filepath = os.path.join(self.output_dir_var.get(), srt_filename)
                        if os.path.exists(srt_filepath):
                            self.log_message(f"--- Content of {srt_filename} ---", self.SUBTLE_TEXT_COLOR)
                            with open(srt_filepath, 'r', encoding='utf-8') as f:
                                srt_content = f.read()
                                if len(srt_content) > 2000:
                                     self.log_message(srt_content[:2000] + "\n... (file truncated in log)")
                                else:
                                     self.log_message(srt_content)
                            self.log_message(f"--- End of {srt_filename} ---", self.SUBTLE_TEXT_COLOR)
                    except Exception as e:
                        self.log_message(f"ERROR: Could not read SRT file: {e}", self.ERROR_COLOR)

                else:
                    self.log_message(f"ERROR processing {os.path.basename(video_file_path)}. CLI returned code: {return_code}", self.ERROR_COLOR)
                    all_successful = False
                    self.master.after(0, self._update_ui_progress, None, i + 1, num_files)

            except Exception as e:
                self.log_message(f"A critical error occurred: {e}", self.ERROR_COLOR)
                print(f"CRITICAL ERROR: {e}")
                all_successful = False
                break
        
        self.master.after(0, self._processing_finished, all_successful)

    def _processing_finished(self, success_flag=True):
        self.log_message("="*60, self.ACCENT_COLOR)
        if success_flag and self.video_files:
            self.log_message("All processing finished successfully.", self.SUCCESS_COLOR)
            messagebox.showinfo("Complete", "All selected videos have been processed.")
            self.overall_progress_count_label.config(text="Complete!")
        else:
            self.log_message("Processing finished with errors. See console for details.", self.ERROR_COLOR)
            messagebox.showerror("Error / Incomplete", "Processing encountered errors. Check the console and GUI log for details.")
            self.overall_progress_count_label.config(text="Errors")

        self.set_ui_state("normal")


# --- Main execution block ---
if __name__ == "__main__":
    if os.name == 'nt':
        multiprocessing.freeze_support()

    try:
        root = tk.Tk()
        app = SubtitleApp(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"A fatal error occurred on startup:\n{e}")