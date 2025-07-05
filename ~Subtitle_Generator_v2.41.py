import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk, font
import subprocess
import os
import threading
import sys
import multiprocessing
import re

# --- Constants and Configuration ---
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.getcwd()

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
DEFAULT_NO_SPEECH_THRESHOLD = "0.2"
DEFAULT_MERGE_REPETITIONS = True
DEFAULT_USE_VAD = True
DEFAULT_VAD_THRESHOLD = "0.3"
DEFAULT_MIN_SPEECH_MS = "50"
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
        self.BG_COLOR = "#F5F5F5"
        self.FRAME_COLOR = "#FFFFFF"
        self.ACCENT_COLOR = "#0078D7"
        self.TEXT_COLOR = "#1F1F1F"
        self.SUBTLE_TEXT_COLOR = "#605E5C"
        self.BORDER_COLOR = "#D1D1D1"
        self.SUCCESS_COLOR = "#107C10"
        self.ERROR_COLOR = "#A80000"

        self.master.title("Auto Subtitle GUI (Portable) V2.4")
        self.master.geometry("850x820")
        self.master.minsize(800, 750)
        self.master.configure(bg=self.BG_COLOR)

        self.default_font = font.nametofont("TkDefaultFont")
        self.default_font.configure(family="Segoe UI", size=10)
        self.title_font = font.Font(family="Segoe UI", size=12, weight="bold")
        self.label_font = font.Font(family="Segoe UI", size=10)

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
        # Style for the help button in its new location
        style.configure("Help.TButton", font=self.label_font, padding=6, borderwidth=1, relief="solid", bordercolor=self.BORDER_COLOR, background="#E1F0FA")
        style.map("Help.TButton", background=[('active', '#CCE4F7')])

    def _create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="15 15 15 15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- TOP BUTTON BAR ---
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill=tk.X, pady=(0, 5))
        self.select_button = ttk.Button(file_frame, text="Select Video File(s)", command=self.select_files)
        self.select_button.pack(side=tk.LEFT, padx=(0, 5))
        self.clear_button = ttk.Button(file_frame, text="Clear List", command=self.clear_file_list)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        # --- FIX: Moved Help Button to the top bar for stability and visibility ---
        self.help_button = ttk.Button(file_frame, text="❓ Parameter Help", command=self.show_help, style="Help.TButton")
        self.help_button.pack(side=tk.LEFT, padx=15)


        list_frame = ttk.Frame(main_frame)
        list_frame.pack(pady=5, fill=tk.X)
        ttk.Label(list_frame, text="Selected Files:").pack(anchor=tk.W, pady=(0, 2))
        listbox_inner_frame = ttk.Frame(list_frame)
        listbox_inner_frame.pack(fill=tk.X, expand=True)
        scrollbar = ttk.Scrollbar(listbox_inner_frame, orient=tk.VERTICAL)
        self.file_listbox = tk.Listbox(listbox_inner_frame, selectmode=tk.EXTENDED, height=5, yscrollcommand=scrollbar.set,
                                       bg=self.FRAME_COLOR, relief=tk.SOLID, borderwidth=1, highlightthickness=0)
        scrollbar.config(command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.view_container = ttk.Frame(main_frame)
        self.view_container.pack(pady=10, fill=tk.X)

        self._create_options_view(self.view_container)
        self._create_help_view(self.view_container)
        
        self.options_view.pack(fill=tk.X)
        
        self.start_button = ttk.Button(main_frame, text="Start Processing", command=self.start_processing_thread, style="Accent.TButton")
        self.start_button.pack(pady=15, ipady=5, ipadx=10)

        self.shutdown_var = tk.BooleanVar(self.master, value=False)
        self.shutdown_checkbox = ttk.Checkbutton(main_frame, text="Shutdown computer upon completion (forced)", variable=self.shutdown_var)
        self.shutdown_checkbox.pack(pady=(0, 10))
        
        progress_frame = ttk.Frame(main_frame, padding="0 10 0 0")
        progress_frame.pack(fill=tk.X, expand=False, pady=5)
        progress_frame.columnconfigure(1, weight=1)

        self.file_progress_label = ttk.Label(progress_frame, text="File Progress: 0%", anchor=tk.W)
        self.file_progress_label.grid(row=0, column=0, sticky=tk.W, padx=(0,10))
        self.file_progress = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate', style="Horizontal.TProgressbar")
        self.file_progress.grid(row=0, column=1, sticky=tk.EW)

        self.overall_progress_label = ttk.Label(progress_frame, text="Overall Progress: 0 / 0", anchor=tk.W)
        self.overall_progress_label.grid(row=1, column=0, sticky=tk.W, padx=(0,10), pady=(5,0))
        self.overall_progress = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate', style="Horizontal.TProgressbar")
        self.overall_progress.grid(row=1, column=1, sticky=tk.EW, pady=(5,0))

        log_frame = ttk.Frame(main_frame)
        log_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        ttk.Label(log_frame, text="Summary Log:").pack(anchor=tk.W, pady=(0, 2))
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state=tk.DISABLED, wrap=tk.WORD, relief=tk.SOLID,
                                                  borderwidth=1, font=("Courier New", 9), bg=self.FRAME_COLOR)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.toggle_vad_options()

    def _create_options_view(self, parent):
        self.options_view = ttk.LabelFrame(parent, text="Processing Options", padding="15 10 15 15")
        self.options_view.columnconfigure((0, 2), weight=1)
        
        # Help button has been moved, so it's no longer created here.
        
        left_col = ttk.Frame(self.options_view)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        left_col.columnconfigure(1, weight=1)
        
        ttk.Label(left_col, text="Model:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.model_var = tk.StringVar(self.master, value=DEFAULT_MODEL)
        self.model_dropdown = ttk.Combobox(left_col, textvariable=self.model_var, values=AVAILABLE_MODELS_FROM_IMAGE, state="readonly")
        self.model_dropdown.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(left_col, text="Source Language:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.language_var = tk.StringVar(self.master, value=DEFAULT_LANGUAGE_DISPLAY_NAME)
        self.language_dropdown = ttk.Combobox(left_col, textvariable=self.language_var, values=list(LANGUAGES_MAP.keys()), state="readonly")
        self.language_dropdown.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(left_col, text="Task:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.task_var = tk.StringVar(self.master, value="Translate")
        self.task_dropdown = ttk.Combobox(left_col, textvariable=self.task_var, values=["Transcribe", "Translate"], state="readonly")
        self.task_dropdown.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        ttk.Label(left_col, text="(Translate is to English)", foreground=self.SUBTLE_TEXT_COLOR).grid(row=3, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(left_col, text="No Speech Threshold:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=(15, 5))
        self.no_speech_threshold_var = tk.StringVar(self.master, value=DEFAULT_NO_SPEECH_THRESHOLD)
        self.no_speech_threshold_entry = ttk.Entry(left_col, textvariable=self.no_speech_threshold_var, width=12)
        self.no_speech_threshold_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=(15, 5))
        ttk.Label(left_col, text="(Lower = More subtitles)", foreground=self.SUBTLE_TEXT_COLOR).grid(row=5, column=1, sticky=tk.W, padx=5)
        
        ttk.Separator(self.options_view, orient='vertical').grid(row=0, column=1, sticky='ns', padx=10)
        
        right_col = ttk.Frame(self.options_view)
        right_col.grid(row=0, column=2, sticky="nsew", padx=(15, 0))
        
        self.use_vad_var = tk.BooleanVar(self.master, value=DEFAULT_USE_VAD)
        self.use_vad_checkbox = ttk.Checkbutton(right_col, text="Use Voice Activity Detection (VAD)", variable=self.use_vad_var, command=self.toggle_vad_options)
        self.use_vad_checkbox.pack(anchor="w", padx=5)
        
        self.vad_options_frame = ttk.Frame(right_col, padding="15 5 5 5")
        self.vad_options_frame.pack(fill="x")
        self.vad_options_frame.columnconfigure(1, weight=1)
        
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
        
        max_cores = os.cpu_count() or 1
        self.num_workers_label = ttk.Label(right_col, text="CPU Workers:")
        self.num_workers_label.pack(anchor="w", padx=5, pady=(10,2))
        workers_frame = ttk.Frame(right_col)
        workers_frame.pack(fill="x", padx=5)
        self.num_workers_var = tk.StringVar(self.master, value=str(min(int(DEFAULT_NUM_WORKERS), max_cores)))
        self.num_workers_spinbox = ttk.Spinbox(workers_frame, from_=0, to=max_cores, textvariable=self.num_workers_var, width=5, state="readonly")
        self.num_workers_spinbox.pack(side="left")
        self.num_workers_tooltip_label = ttk.Label(workers_frame, text=f"(0=auto, max {max_cores})", foreground=self.SUBTLE_TEXT_COLOR)
        self.num_workers_tooltip_label.pack(side="left", padx=5)
        
        self.merge_repetitions_var = tk.BooleanVar(self.master, value=DEFAULT_MERGE_REPETITIONS)
        self.merge_repetitions_checkbox = ttk.Checkbutton(right_col, text="Merge Repetitive Segments", variable=self.merge_repetitions_var)
        self.merge_repetitions_checkbox.pack(anchor="w", padx=5, pady=(15, 0))
        
        output_frame = ttk.Frame(self.options_view)
        output_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10,0))
        output_frame.columnconfigure(1, weight=1)
        ttk.Label(output_frame, text="Output Directory:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.output_dir_var = tk.StringVar(self.master, value=DEFAULT_OUTPUT_DIR)
        self.output_dir_entry = ttk.Entry(output_frame, textvariable=self.output_dir_var, state="readonly")
        self.output_dir_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.output_dir_button = ttk.Button(output_frame, text="Browse...", command=self.select_output_dir)
        self.output_dir_button.grid(row=0, column=2, sticky=tk.EW, padx=5)

    def _create_help_view(self, parent):
        self.help_view = ttk.LabelFrame(parent, text="Parameter Help", padding="15")
        self.help_view.columnconfigure(0, weight=1)
        self.help_view.rowconfigure(0, weight=1)

        back_button = ttk.Button(self.help_view, text="< Back to Options", command=self.hide_help)
        back_button.grid(row=1, column=0, sticky="w", pady=(10, 0))

        text_area = scrolledtext.ScrolledText(
            self.help_view, wrap=tk.WORD, bg=self.FRAME_COLOR, relief=tk.SOLID,
            borderwidth=1, padx=10, pady=10, font=("Segoe UI", 10)
        )
        text_area.grid(row=0, column=0, sticky="nsew", ipady=150)

        title_font = font.Font(family="Segoe UI", size=14, weight="bold")
        heading_font = font.Font(family="Segoe UI", size=10, weight="bold")
        body_font = font.Font(family="Segoe UI", size=10)
        text_area.tag_configure("title", font=title_font, foreground=self.ACCENT_COLOR, spacing3=10)
        text_area.tag_configure("body", font=body_font, foreground=self.TEXT_COLOR, spacing3=15)
        text_area.tag_configure("heading", font=heading_font, foreground=self.TEXT_COLOR, spacing1=10)
        text_area.tag_configure("subtext", font=body_font, foreground=self.TEXT_COLOR, lmargin1=15, lmargin2=15, spacing3=10)
        text_area.tag_configure("separator", font=("Courier New", 8), foreground="#AAAAAA", justify='center', spacing3=15, spacing1=15)

        help_items = [
            ("No Speech Threshold",
             "This is Whisper's internal filter. It controls how confident the AI must be that a segment is *NOT* speech before discarding it. It is a probability from 0.0 to 1.0.",
             "Low Value (e.g., 0.1):", "More Strict. The AI must be very sure a segment is non-speech to discard it. Use this for quiet audio or to capture everything. This results in MORE subtitles, but may include noise or hallucinations.",
             "High Value (e.g., 0.7):", "Less Strict. The AI can easily discard segments it's unsure about. Use this for clean audio or to remove background noise. This results in FEWER, cleaner subtitles, but may miss quiet speech."),
            ("VAD Threshold",
             "Voice Activity Detection (VAD) pre-processes the audio to find speech chunks. This threshold is the confidence level needed to classify a segment as speech.",
             "Low Value (e.g., 0.3):", "More Lenient. Classifies uncertain sounds (like muffled speech or speech over music) as speech. This results in MORE subtitles, potentially including non-speech noise.",
             "High Value (e.g., 0.7):", "More Strict. Only classifies clear, obvious speech. This results in FEWER subtitles, but is better at ignoring background noise."),
            ("Min Speech (ms)",
             "The minimum duration (in milliseconds) an audio chunk must have to be considered a valid speech segment. Any detected speech shorter than this is ignored.",
             "Low Value (e.g., 50ms):", "Captures very short sounds like 'uh', 'ok', or a quick 'yes'. This results in MORE subtitles, but may capture unwanted short noises like coughs or clicks.",
             "High Value (e.g., 500ms):", "Ignores short noises and only processes longer speech segments. This results in FEWER subtitles and a cleaner transcript that ignores brief interjections."),
            ("Min Silence (ms)",
             "The minimum duration of silence between two speech segments to create a new subtitle line. This affects how subtitles are grouped, not the total amount of text.",
             "Low Value (e.g., 100ms):", "Creates a new subtitle line even for very brief pauses. This results in MORE, shorter subtitle blocks.",
             "High Value (e.g., 1000ms):", "Merges sentences spoken closely together into a single, longer subtitle block. This results in FEWER, longer subtitle blocks.")
        ]
        
        for i, (title, desc, low_head, low_text, high_head, high_text) in enumerate(help_items):
            text_area.insert(tk.END, f"{title}\n", "title")
            text_area.insert(tk.END, f"{desc}\n", "body")
            text_area.insert(tk.END, f"{low_head}\n", "heading")
            text_area.insert(tk.END, f"{low_text}\n", "subtext")
            text_area.insert(tk.END, f"{high_head}\n", "heading")
            text_area.insert(tk.END, f"{high_text}\n", "subtext")
            if i < len(help_items) - 1:
                text_area.insert(tk.END, "•" * 40 + "\n", "separator")
        
        text_area.config(state=tk.DISABLED)

    def show_help(self):
        if self.options_view.winfo_ismapped():
            self.options_view.pack_forget()
            self.help_view.pack(fill=tk.X)

    def hide_help(self):
        if self.help_view.winfo_ismapped():
            self.help_view.pack_forget()
            self.options_view.pack(fill=tk.X)

    def _update_ui_progress(self, file_percent, overall_val, overall_max):
        if file_percent is not None:
            self.file_progress['value'] = file_percent
            self.file_progress_label.config(text=f"File Progress: {int(file_percent)}%")
        
        if overall_val is not None and overall_max is not None:
            self.overall_progress['maximum'] = overall_max
            self.overall_progress['value'] = overall_val
            self.overall_progress_label.config(text=f"Overall Progress: {overall_val} / {overall_max}")
        self.master.update_idletasks()
        
    def toggle_vad_options(self):
        state = tk.NORMAL if self.use_vad_var.get() else tk.DISABLED
        for widget in self.vad_options_frame.winfo_children():
            widget.config(state=state)
        self.num_workers_label.config(state=state)
        self.num_workers_spinbox.config(state="readonly" if state == tk.NORMAL else tk.DISABLED)
        self.num_workers_tooltip_label.config(state=state)

    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select SRT Output Directory", initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)

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
                if f_path not in self.video_files: self.video_files.append(f_path)
            self.update_file_listbox()

    def clear_file_list(self):
        self.video_files.clear()
        self.update_file_listbox()

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for f_path in self.video_files:
            self.file_listbox.insert(tk.END, os.path.basename(f_path))

    def set_ui_state(self, state):
        for widget in self.master.winfo_children():
            if widget not in [self.shutdown_checkbox.master, self.log_text.master]:
                 self._set_widget_state_recursively(widget, state)
        
        self.start_button.config(state=state)
        self.shutdown_checkbox.config(state="normal")

    def _set_widget_state_recursively(self, widget, state):
        w_state = state
        try:
            if isinstance(widget, (ttk.Combobox, ttk.Spinbox)):
                w_state = 'readonly' if state == tk.NORMAL else tk.DISABLED
            
            if 'state' in widget.configure():
                widget.configure(state=w_state)
        except tk.TclError:
            pass
        
        for child in widget.winfo_children():
            self._set_widget_state_recursively(child, state)

    def start_processing_thread(self):
        if not self.video_files:
            messagebox.showwarning("No Files", "Please select at least one video file.")
            return
        
        if not self.options_view.winfo_ismapped():
            self.hide_help()

        try:
            float(self.no_speech_threshold_var.get())
            if self.use_vad_var.get(): float(self.vad_threshold_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Threshold values must be valid numbers.")
            return

        self.set_ui_state(tk.DISABLED)
        self.log_message("="*60, self.ACCENT_COLOR)
        self.log_message("Starting video processing...", self.ACCENT_COLOR)
        
        thread = threading.Thread(target=self.process_videos_sequentially, daemon=True)
        thread.start()

    def process_videos_sequentially(self):
        all_successful = True
        num_files = len(self.video_files)
        self.master.after(0, self._update_ui_progress, 0, 0, num_files)
        
        for i, video_file_path in enumerate(self.video_files):
            self.log_message(f"\nProcessing file {i+1}/{num_files}: {os.path.basename(video_file_path)}", self.ACCENT_COLOR)
            print(f"\n{'='*80}\n--> Starting file {i+1}/{num_files}: {os.path.basename(video_file_path)}\n{'='*80}")
            
            self.master.after(0, self._update_ui_progress, 0, None, None)
            is_single_chunk_mode = None
            processed_chunks, total_chunks = 0, 0

            command = [
                PYTHON_EXECUTABLE, "-u", "-m", "auto_subtitle.cli", video_file_path,
                "--task", self.task_var.get().lower(),
                "--model", self.model_var.get(),
                "--language", LANGUAGES_MAP.get(self.language_var.get(), "en"),
                "--output_dir", self.output_dir_var.get(),
                "--srt_only", "True",
                "--output_srt", "True",
                "--verbose", "True",
                "--ffmpeg_executable_path", FFMPEG_EXECUTABLE_PATH,
                "--model_download_root", MODEL_CACHE_ROOT_DIR,
                "--no_speech_threshold", self.no_speech_threshold_var.get(),
                "--merge_repetitive_segments", str(self.merge_repetitions_var.get())
            ]

            if self.use_vad_var.get():
                command.extend(["--use_vad", "True", "--vad_threshold", self.vad_threshold_var.get(),
                                "--min_speech_duration_ms", self.min_speech_duration_ms_var.get(),
                                "--min_silence_duration_ms", self.min_silence_duration_ms_var.get(),
                                "--num_workers", self.num_workers_var.get()])
            else:
                command.extend(["--use_vad", "True", "--vad_threshold", "0.1",
                                "--min_speech_duration_ms", "10", "--min_silence_duration_ms", "60000000",
                                "--num_workers", "1"])

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
                    if not final_part: continue
                    print(final_part, flush=True)

                    if is_single_chunk_mode is None:
                        if (match := re.search(r'VAD found (\d+) speech segments', final_part)):
                            total_chunks = int(match.group(1))
                            if total_chunks > 1:
                                is_single_chunk_mode = False
                                self.log_message(f"INFO: VAD detected {total_chunks} speech segments.")
                                # BUGFIX: The original line incorrectly configured the progress bar's maximum,
                                # causing it to appear stuck. The update logic relies on a percentage-based
                                # system, so the progress bar's maximum should be 100. This part of the
                                # original line is removed. The label update is preserved but written
                                # more safely to avoid potential closure issues.
                                self.master.after(0, lambda i=i, num_files=num_files: self.overall_progress_label.config(text=f"Overall Progress: {i+1} / {num_files}"))
                            else:
                                is_single_chunk_mode = True
                                self.log_message("INFO: Processing as a single segment. Progress will be time-based.")

                    if is_single_chunk_mode:
                        if (match := re.search(r'([\d\.]+)/([\d\.]+)[\s\[]', final_part)):
                            current, total = float(match.group(1)), float(match.group(2))
                            percent = (current / total) * 100 if total > 0 else 0
                            self.master.after(0, self._update_ui_progress, percent, i, num_files)
                    elif total_chunks > 0 and 'Transcription finished for VAD chunk' in final_part:
                        processed_chunks += 1
                        percent = (processed_chunks / total_chunks) * 100
                        self.master.after(0, self._update_ui_progress, percent, i, num_files)
                    
                    if (match := re.search(r'INFO: Detected language: (\w+)', final_part)):
                        self.log_message(f"INFO: Auto-detected language as: {match.group(1).capitalize()}", self.SUCCESS_COLOR)

                process.stdout.close()
                if process.wait() == 0:
                    self.log_message(f"Successfully processed {os.path.basename(video_file_path)}.", self.SUCCESS_COLOR)
                    self.master.after(0, self._update_ui_progress, 100, i + 1, num_files)
                else:
                    self.log_message(f"ERROR processing {os.path.basename(video_file_path)}. See console for details.", self.ERROR_COLOR)
                    all_successful = False
                    self.master.after(0, self._update_ui_progress, None, i + 1, num_files)

            except Exception as e:
                self.log_message(f"A critical error occurred: {e}", self.ERROR_COLOR)
                all_successful = False
                break
        
        self.master.after(0, self._processing_finished, all_successful)

    def _processing_finished(self, success_flag=True):
        self.log_message("="*60, self.ACCENT_COLOR)
        should_shutdown = self.shutdown_var.get()

        if success_flag and self.video_files:
            self.log_message("All processing finished successfully.", self.SUCCESS_COLOR)
            if not should_shutdown: messagebox.showinfo("Complete", "All selected videos have been processed.")
        else:
            self.log_message("Processing finished with errors.", self.ERROR_COLOR)
            if not should_shutdown: messagebox.showerror("Error", "Processing encountered errors. Check logs for details.")

        if should_shutdown:
            self.log_message("SHUTDOWN INITIATED: Computer will shut down in 10 seconds.", self.ERROR_COLOR)
            self.master.after(10000, self.execute_shutdown)
        else:
            self.set_ui_state(tk.NORMAL)
            self.toggle_vad_options()
            
    def execute_shutdown(self):
        if sys.platform == "win32": os.system("shutdown /s /f /t 1")
        elif sys.platform in ["linux", "darwin"]: os.system("shutdown -h now")
        else: self.log_message(f"ERROR: Shutdown not supported on this OS ({sys.platform}).", self.ERROR_COLOR)


if __name__ == "__main__":
    if os.name == 'nt':
        multiprocessing.freeze_support()
    try:
        root = tk.Tk()
        app = SubtitleApp(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"A fatal error occurred on startup:\n{e}")