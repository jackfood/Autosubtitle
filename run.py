import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import subprocess
import os
import threading
import sys
import multiprocessing
import time

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
DEFAULT_VAD_THRESHOLD = "0.4"
DEFAULT_MIN_SPEECH_MS = "50"
DEFAULT_MIN_SILENCE_MS = "500"
try:
    _default_cpu_workers_val = os.cpu_count() // 2 if (os.cpu_count() or 0) > 1 else 1
    DEFAULT_NUM_WORKERS = str(_default_cpu_workers_val)
except NotImplementedError:
    DEFAULT_NUM_WORKERS = "1"


DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop")


class SubtitleApp:
    def __init__(self, master):
        self.master = master
        master.title("Auto Subtitle GUI (Portable) V1.0.8")
        master.geometry("700x870")

        self.video_files = []
        self.processing_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set() # Initially not paused (event is set)
        self.current_process = None
        self.current_video_index = 0
        self.is_processing = False # Overall state if a processing session is active

        file_frame = tk.Frame(master)
        file_frame.pack(pady=10, padx=10, fill=tk.X)

        self.select_button = tk.Button(file_frame, text="Select Video File(s)", command=self.select_files)
        self.select_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(file_frame, text="Clear List", command=self.clear_file_list)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        options_frame = tk.LabelFrame(master, text="Processing Options", padx=10, pady=10)
        options_frame.pack(pady=(5,10), padx=10, fill=tk.X)

        model_label = tk.Label(options_frame, text="Model:")
        model_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.model_var = tk.StringVar(master)
        if DEFAULT_MODEL in AVAILABLE_MODELS_FROM_IMAGE:
            self.model_var.set(DEFAULT_MODEL)
        elif AVAILABLE_MODELS_FROM_IMAGE:
            self.model_var.set(AVAILABLE_MODELS_FROM_IMAGE[0])
        else:
            self.model_var.set("small")
        self.model_dropdown = ttk.Combobox(options_frame, textvariable=self.model_var,
                                           values=AVAILABLE_MODELS_FROM_IMAGE, state="readonly", width=25)
        self.model_dropdown.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2, columnspan=2)
        
        language_label = tk.Label(options_frame, text="Language:")
        language_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.language_var = tk.StringVar(master)
        self.language_var.set(DEFAULT_LANGUAGE_DISPLAY_NAME)
        self.language_dropdown = ttk.Combobox(options_frame, textvariable=self.language_var,
                                              values=list(LANGUAGES_MAP.keys()), state="readonly", width=25)
        self.language_dropdown.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2, columnspan=2)

        no_speech_label = tk.Label(options_frame, text="No Speech Threshold (Whisper):")
        no_speech_label.grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.no_speech_threshold_var = tk.StringVar(master)
        self.no_speech_threshold_var.set(DEFAULT_NO_SPEECH_THRESHOLD)
        self.no_speech_threshold_entry = tk.Entry(options_frame, textvariable=self.no_speech_threshold_var, width=10)
        self.no_speech_threshold_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        no_speech_tooltip = tk.Label(options_frame, text="(0.0-1.0, e.g., 0.6)", fg="grey")
        no_speech_tooltip.grid(row=2, column=2, sticky=tk.W, padx=0, pady=2)

        self.merge_repetitions_var = tk.BooleanVar(master)
        self.merge_repetitions_var.set(DEFAULT_MERGE_REPETITIONS)
        self.merge_repetitions_checkbox = tk.Checkbutton(options_frame, text="Merge Repetitive Segments", variable=self.merge_repetitions_var)
        self.merge_repetitions_checkbox.grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=5, pady=2)

        self.use_vad_var = tk.BooleanVar(master)
        self.use_vad_var.set(DEFAULT_USE_VAD)
        self.use_vad_checkbox = tk.Checkbutton(options_frame, text="Use Voice Activity Detection (VAD)", variable=self.use_vad_var, command=self.toggle_vad_options)
        self.use_vad_checkbox.grid(row=4, column=0, columnspan=3, sticky=tk.W, padx=5, pady=2)

        self.vad_options_frame = tk.Frame(options_frame)
        
        vad_threshold_label = tk.Label(self.vad_options_frame, text="VAD Threshold:")
        vad_threshold_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=1)
        self.vad_threshold_var = tk.StringVar(master, value=DEFAULT_VAD_THRESHOLD)
        self.vad_threshold_entry = tk.Entry(self.vad_options_frame, textvariable=self.vad_threshold_var, width=7)
        self.vad_threshold_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=1)
        vad_thresh_tooltip = tk.Label(self.vad_options_frame, text="(0-1, e.g. 0.5)", fg="grey")
        vad_thresh_tooltip.grid(row=0, column=2, sticky=tk.W, padx=0, pady=1)

        min_speech_label = tk.Label(self.vad_options_frame, text="Min Speech (ms):")
        min_speech_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=1)
        self.min_speech_duration_ms_var = tk.StringVar(master, value=DEFAULT_MIN_SPEECH_MS)
        self.min_speech_duration_ms_entry = tk.Entry(self.vad_options_frame, textvariable=self.min_speech_duration_ms_var, width=7)
        self.min_speech_duration_ms_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=1)

        min_silence_label = tk.Label(self.vad_options_frame, text="Min Silence (ms):")
        min_silence_label.grid(row=2, column=0, sticky=tk.W, padx=5, pady=1)
        self.min_silence_duration_ms_var = tk.StringVar(master, value=DEFAULT_MIN_SILENCE_MS)
        self.min_silence_duration_ms_entry = tk.Entry(self.vad_options_frame, textvariable=self.min_silence_duration_ms_var, width=7)
        self.min_silence_duration_ms_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=1)

        max_cores = os.cpu_count() or 1
        self.calculated_max_workers_for_spinbox = max_cores
        self.num_workers_label = tk.Label(options_frame, text="CPU Workers (VAD Chunks):")
        self.num_workers_label.grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
        initial_num_workers_val_str = DEFAULT_NUM_WORKERS
        initial_num_workers_val_int = int(initial_num_workers_val_str)
        final_default_num_workers = initial_num_workers_val_str
        if initial_num_workers_val_int != 0:
             final_default_num_workers = str(min(initial_num_workers_val_int, self.calculated_max_workers_for_spinbox))
        self.num_workers_var = tk.StringVar(master, value=final_default_num_workers)
        self.num_workers_spinbox = tk.Spinbox(options_frame, from_=0, to=self.calculated_max_workers_for_spinbox,
                                              textvariable=self.num_workers_var, width=5, state="readonly")
        self.num_workers_spinbox.grid(row=6, column=1, sticky=tk.W, padx=5, pady=2)
        self.num_workers_tooltip_label = tk.Label(options_frame, text=f"(0=auto, 1-core serial, max {max_cores} based on CPU)", fg="grey")
        self.num_workers_tooltip_label.grid(row=6, column=2, sticky=tk.W, padx=0, pady=2)

        output_dir_label = tk.Label(options_frame, text="SRT Output Dir:")
        output_dir_label.grid(row=7, column=0, sticky=tk.W, padx=5, pady=(10,2))
        self.output_dir_var = tk.StringVar(master)
        self.output_dir_var.set(DEFAULT_OUTPUT_DIR)
        self.output_dir_entry = tk.Entry(options_frame, textvariable=self.output_dir_var, state="readonly", width=40)
        self.output_dir_entry.grid(row=7, column=1, sticky=tk.EW, padx=5, pady=(10,2))
        self.output_dir_button = tk.Button(options_frame, text="Browse...", command=self.select_output_dir)
        self.output_dir_button.grid(row=7, column=2, sticky=tk.EW, padx=5, pady=(10,2))
        options_frame.columnconfigure(1, weight=1)

        self.file_listbox_label = tk.Label(master, text="Selected Files:")
        self.file_listbox_label.pack(anchor=tk.W, padx=10)
        self.file_listbox_frame = tk.Frame(master)
        self.file_listbox_frame.pack(pady=5, padx=10, fill=tk.X)
        self.file_listbox_scrollbar = tk.Scrollbar(self.file_listbox_frame, orient=tk.VERTICAL)
        self.file_listbox = tk.Listbox(self.file_listbox_frame, selectmode=tk.EXTENDED, height=5, yscrollcommand=self.file_listbox_scrollbar.set)
        self.file_listbox_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        control_button_frame = tk.Frame(master)
        control_button_frame.pack(pady=10)
        self.start_pause_resume_button = tk.Button(control_button_frame, text="Start Processing", command=self._handle_start_pause_resume, bg="lightblue", width=15)
        self.start_pause_resume_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = tk.Button(control_button_frame, text="Stop Processing", command=self._handle_stop, bg="salmon", width=15, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.log_label = tk.Label(master, text="Log Output:")
        self.log_label.pack(anchor=tk.W, padx=10)
        self.log_text = scrolledtext.ScrolledText(master, height=10, width=80, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.toggle_vad_options()
        self.check_paths()
        
    def _get_num_workers_tooltip_text(self):
        max_cores = os.cpu_count() or 1
        return f"(0=auto, 1-core serial, max {max_cores} based on CPU)"
        
    def _calculate_max_workers(self, selected_model_name):
        return os.cpu_count() or 1
        
    def on_model_changed(self, event=None):
        pass

    def toggle_vad_options(self):
        is_enabled = self.use_vad_var.get()
        vad_controls_state = tk.NORMAL if not self.is_processing else tk.DISABLED
        vad_spinbox_state = "readonly" if not self.is_processing else tk.DISABLED
        vad_tooltip_fg = "grey" if not self.is_processing else "lightgrey"

        if is_enabled:
            self.vad_options_frame.grid(row=5, column=0, columnspan=3, sticky=tk.EW, padx=(20,5))
            self.num_workers_label.grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
            self.num_workers_spinbox.grid(row=6, column=1, sticky=tk.W, padx=5, pady=2)
            self.num_workers_tooltip_label.grid(row=6, column=2, sticky=tk.W, padx=0, pady=2)
            
            for widget in self.vad_options_frame.winfo_children():
                if isinstance(widget, (tk.Entry, tk.Checkbutton, tk.Button)):
                    widget.config(state=vad_controls_state)
                elif isinstance(widget, tk.Label) and widget not in [self.num_workers_label, self.num_workers_tooltip_label]: # VAD specific labels
                     pass # Keep labels enabled
            self.num_workers_spinbox.config(state=vad_spinbox_state)
            self.num_workers_tooltip_label.config(fg=vad_tooltip_fg)
        else:
            self.vad_options_frame.grid_forget()
            self.num_workers_label.grid_forget()
            self.num_workers_spinbox.grid_forget()
            self.num_workers_tooltip_label.grid_forget()


    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select SRT Output Directory", initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)
            self.log_message(f"SRT output directory set to: {directory}")

    def check_paths(self):
        paths_ok = True
        if not os.path.isdir(VENV_SCRIPTS_DIR):
            self.log_message(f"ERROR: VENV_SCRIPTS_DIR not found: {VENV_SCRIPTS_DIR}", "red"); paths_ok = False
        if not os.path.isfile(PYTHON_EXECUTABLE):
            self.log_message(f"ERROR: Python executable not found: {PYTHON_EXECUTABLE}", "red"); paths_ok = False
        if not os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            self.log_message(f"ERROR: Portable FFMPEG executable not found at: {FFMPEG_EXECUTABLE_PATH}", "red")
            self.log_message("Please ensure ffmpeg_binary/bin/ffmpeg.exe exists and includes necessary DLLs.", "red"); paths_ok = False
        else:
            self.log_message(f"INFO: Using portable FFMPEG executable from: {FFMPEG_EXECUTABLE_PATH}", "green")
        self.log_message(f"INFO: Whisper model cache root directory set to: {MODEL_CACHE_ROOT_DIR}. Whisper will create a 'whisper' subdirectory here.", "blue")
        auto_subtitle_cli_py_module_path = os.path.join(VENV_SCRIPTS_DIR, "auto_subtitle", "cli.py")
        if not os.path.isfile(auto_subtitle_cli_py_module_path):
             self.log_message(f"ERROR: auto_subtitle/cli.py not found at: {auto_subtitle_cli_py_module_path}", "red")
             self.log_message("Ensure 'auto_subtitle' package (folder) containing 'cli.py' is correctly placed in the Scripts directory.", "red"); paths_ok = False
        
        if not paths_ok:
            self.start_pause_resume_button.config(state=tk.DISABLED)
            messagebox.showerror("Path Error", "One or more critical files/directories are missing. Check logs.")
        else:
            self.log_message("Initial script path checks OK.", "green")
            self.start_pause_resume_button.config(state=tk.NORMAL)


    def log_message(self, message, color=None, no_newline=False):
        def _update_log():
            self.log_text.config(state=tk.NORMAL)
            msg_str = str(message)
            if color:
                tag_name = f"color_{color.replace(' ', '_').replace(':', '')}"
                self.log_text.tag_configure(tag_name, foreground=color)
                self.log_text.insert(tk.END, msg_str + ("" if no_newline else "\n"), tag_name)
            else:
                self.log_text.insert(tk.END, msg_str + ("" if no_newline else "\n"))
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        if self.master.winfo_exists(): # Avoid error if master is destroyed
            self.master.after(0, _update_log)

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=(("Video files", "*.avi *.mp4 *.mkv *.mov *.webm *.mpg *.flv *.wmv"), ("All files", "*.*"))
        )
        if files:
            for f_path in files:
                if f_path not in self.video_files:
                    self.video_files.append(f_path)
            self.update_file_listbox()
            if not self.is_processing and self.current_video_index >= len(self.video_files) and len(self.video_files) > 0:
                 self.current_video_index = 0 
                 self.start_pause_resume_button.config(text="Start Processing")


    def clear_file_list(self):
        if self.is_processing:
            messagebox.showwarning("Processing Active", "Cannot clear file list while processing is active. Please stop processing first.")
            return
        self.video_files.clear()
        self.update_file_listbox()
        self.current_video_index = 0
        self.start_pause_resume_button.config(text="Start Processing") # Reset button
        self.log_message("Cleared selected files list.")

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for f_path in self.video_files:
            self.file_listbox.insert(tk.END, os.path.basename(f_path))

    def set_parameter_controls_state(self, state_str):
        tk_state = tk.NORMAL if state_str == "normal" else tk.DISABLED
        combo_state = "readonly" if state_str == "normal" else tk.DISABLED
        entry_state = tk.NORMAL if state_str == "normal" else tk.DISABLED
        
        self.select_button.config(state=tk_state)
        self.clear_button.config(state=tk_state)
        self.output_dir_button.config(state=tk_state)
        self.no_speech_threshold_entry.config(state=entry_state)
        self.merge_repetitions_checkbox.config(state=tk_state)
        self.use_vad_checkbox.config(state=tk_state)
        
        self.model_dropdown.config(state=combo_state)
        self.language_dropdown.config(state=combo_state)
        
        self.toggle_vad_options()


    def _validate_inputs(self):
        if not self.video_files:
            messagebox.showwarning("No Files", "Please select at least one video file.")
            return False
        
        # Check if trying to start when all files are already processed from a previous run
        if self.current_video_index >= len(self.video_files) and self.start_pause_resume_button.cget('text') == "Start Processing":
             messagebox.showinfo("All Processed", "All files in the current list have been processed. Add more files or clear the list to start over.")
             return False

        if not os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            messagebox.showerror("FFmpeg Error", f"Portable FFmpeg executable not found at:\n{FFMPEG_EXECUTABLE_PATH}\nCannot proceed.")
            return False
        try:
            no_speech_val_str = self.no_speech_threshold_var.get()
            no_speech_val_float = float(no_speech_val_str)
            if not (0.0 <= no_speech_val_float <= 1.0):
                messagebox.showerror("Invalid Input", "No Speech Threshold must be a number between 0.0 and 1.0.")
                return False
            if self.use_vad_var.get():
                vad_thresh_str = self.vad_threshold_var.get()
                vad_thresh_float = float(vad_thresh_str)
                if not (0.0 <= vad_thresh_float <= 1.0):
                    messagebox.showerror("Invalid Input", "VAD Threshold must be a number between 0.0 and 1.0.")
                    return False
                int(self.min_speech_duration_ms_var.get())
                int(self.min_silence_duration_ms_var.get())
                num_workers = int(self.num_workers_var.get())
                max_cpu = os.cpu_count() or 1
                if not (0 <= num_workers <= max_cpu):
                     messagebox.showerror("Invalid Input", f"CPU Workers must be between 0 and {max_cpu}.")
                     return False
        except ValueError:
            messagebox.showerror("Invalid Input", "One of the numeric threshold/duration/worker inputs is not a valid number.")
            return False
        return True

    def _handle_start_pause_resume(self):
        current_text = self.start_pause_resume_button.cget('text')

        if current_text == "Start Processing":
            if not self._validate_inputs():
                return
            
            if self.current_video_index >= len(self.video_files) and len(self.video_files) > 0: # If all files processed, reset index to start over
                self.current_video_index = 0

            self.is_processing = True
            self.stop_event.clear()
            self.pause_event.set() 

            self.set_parameter_controls_state("disabled")
            self.start_pause_resume_button.config(text="Pause Processing")
            self.stop_button.config(state=tk.NORMAL)
            
            self.log_message("Starting sequential video processing...", "blue")
            self.log_message("==================================================", "blue")
            self.processing_thread = threading.Thread(target=self.process_videos_sequentially, daemon=True)
            self.processing_thread.start()

        elif current_text == "Pause Processing":
            self.pause_event.clear() 
            self.start_pause_resume_button.config(text="Resume Processing")
            self.log_message("Pause requested. Processing will pause after the current file finishes or before the next.", "orange")

        elif current_text == "Resume Processing":
            if not self.video_files or self.current_video_index >= len(self.video_files):
                 messagebox.showinfo("Nothing to Resume", "No files remaining or list is empty. Click 'Start Processing' to begin anew if desired.")
                 self._processing_finished(True, "No files to resume or list empty.") 
                 return

            self.pause_event.set() 
            self.start_pause_resume_button.config(text="Pause Processing")
            self.log_message("Resuming processing...", "blue")
            
            if self.processing_thread and not self.processing_thread.is_alive() and self.is_processing:
                self.log_message("Restarting processing thread for resume.", "gray")
                self.processing_thread = threading.Thread(target=self.process_videos_sequentially, daemon=True)
                self.processing_thread.start()


    def _handle_stop(self):
        if not self.is_processing: # Should not happen if button is disabled, but a safeguard
            return

        self.log_message("Stop requested. Attempting to terminate current task...", "red")
        self.stop_event.set()
        self.pause_event.set() # Unblock pause_event.wait(), so thread can see stop_event

        if self.current_process and self.current_process.poll() is None:
            try:
                self.log_message(f"Terminating subprocess PID: {self.current_process.pid}", "gray")
                self.current_process.terminate()
                self.current_process.wait(timeout=3) 
            except subprocess.TimeoutExpired:
                self.log_message("Subprocess did not terminate gracefully, killing.", "red")
                self.current_process.kill()
                self.current_process.wait(timeout=2) # Wait for kill
            except Exception as e:
                self.log_message(f"Error during subprocess termination: {e}", "red")
            self.current_process = None
        
        # The processing thread will eventually call _processing_finished to update UI fully.
        # For immediate feedback, disable stop button, though _processing_finished will do it too.
        self.stop_button.config(state=tk.DISABLED)


    def process_videos_sequentially(self):
        all_successful_session = True 

        while self.current_video_index < len(self.video_files):
            self.pause_event.wait() 

            if self.stop_event.is_set():
                self.log_message("Stop signal detected. Exiting processing loop.", "orange")
                all_successful_session = False
                break
            
            video_file_path = self.video_files[self.current_video_index]
            self.log_message(f"\nProcessing file {self.current_video_index + 1}/{len(self.video_files)}: {os.path.basename(video_file_path)}", "blue")
            
            selected_model_name = self.model_var.get()
            selected_lang_code = LANGUAGES_MAP.get(self.language_var.get(), "en")
            output_directory = self.output_dir_var.get()
            no_speech_threshold_setting = self.no_speech_threshold_var.get()
            merge_repetitions_setting = self.merge_repetitions_var.get()
            use_vad_setting = self.use_vad_var.get()
            vad_threshold_setting = self.vad_threshold_var.get()
            min_speech_ms_setting = self.min_speech_duration_ms_var.get()
            min_silence_ms_setting = self.min_silence_duration_ms_var.get()
            num_workers_setting = self.num_workers_var.get()

            if not os.path.isdir(output_directory):
                try:
                    os.makedirs(output_directory, exist_ok=True)
                    self.log_message(f"Created output directory: {output_directory}", "green")
                except Exception as e:
                    self.log_message(f"ERROR: Could not create output directory {output_directory}: {e}", "red")
                    all_successful_session = False; break 

            command = [
                PYTHON_EXECUTABLE, "-u", "-m", "auto_subtitle.cli", video_file_path,
                "--model", selected_model_name, "--language", selected_lang_code,
                "--output_dir", output_directory, "--srt_only", "True", "--output_srt", "True",
                "--verbose", "True", "--ffmpeg_executable_path", FFMPEG_EXECUTABLE_PATH,
                "--model_download_root", MODEL_CACHE_ROOT_DIR,
                "--no_speech_threshold", no_speech_threshold_setting,
                "--merge_repetitive_segments", str(merge_repetitions_setting),
                "--use_vad", str(use_vad_setting), "--vad_threshold", vad_threshold_setting,
                "--min_speech_duration_ms", min_speech_ms_setting,
                "--min_silence_duration_ms", min_silence_ms_setting,
                "--num_workers", num_workers_setting
            ]
            command_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
            self.log_message(f"Executing: {command_str}")

            try:
                process_flags = 0
                if os.name == 'nt': process_flags = subprocess.CREATE_NO_WINDOW
                process_env = os.environ.copy()
                ffmpeg_bin_dir = os.path.dirname(FFMPEG_EXECUTABLE_PATH)
                process_env["PATH"] = ffmpeg_bin_dir + os.pathsep + process_env.get("PATH", "")
                process_env["PYTHONUTF8"] = "1"
                
                self.current_process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    bufsize=1, cwd=VENV_SCRIPTS_DIR, creationflags=process_flags,
                    encoding='utf-8', errors='replace', env=process_env
                )

                for raw_line_from_process in iter(self.current_process.stdout.readline, ''):
                    if self.stop_event.is_set(): 
                        if self.current_process and self.current_process.poll() is None: 
                             self.log_message("Stop detected during subprocess output. Terminating.", "orange")
                             self.current_process.terminate() 
                        break 
                    line_content = raw_line_from_process.rstrip('\n')
                    parts = line_content.split('\r')
                    for part_content in parts:
                        if part_content: self.log_message(part_content)
                
                if self.current_process: 
                    self.current_process.stdout.close()
                    return_code = self.current_process.wait()
                else: # Process was likely terminated by stop_event logic
                    return_code = -99 # Indicate it was interrupted
                
                self.current_process = None # Clear after it's done or terminated

                if self.stop_event.is_set(): 
                    self.log_message(f"Processing of {os.path.basename(video_file_path)} was stopped.", "orange")
                    all_successful_session = False; break

                if return_code == 0:
                    self.log_message(f"Successfully processed {os.path.basename(video_file_path)}.", "green")
                    self.current_video_index += 1
                else:
                    self.log_message(f"ERROR processing {os.path.basename(video_file_path)}. CLI script returned code: {return_code}", "red")
                    all_successful_session = False
                    self.current_video_index += 1 
                
            except FileNotFoundError:
                self.log_message(f"ERROR: Command not found. Ensure Python executable ({PYTHON_EXECUTABLE}) is correct.", "red")
                all_successful_session = False; break
            except Exception as e:
                if self.current_process: 
                    try: self.current_process.kill(); self.current_process.wait(timeout=1)
                    except: pass # Best effort
                    self.current_process = None
                
                if self.stop_event.is_set():
                    self.log_message(f"Processing of {os.path.basename(video_file_path)} forcefully stopped during exception.", "orange")
                else:
                    self.log_message(f"An unexpected error occurred while processing {os.path.basename(video_file_path)}: {e}", "red")
                all_successful_session = False
                
                if not self.stop_event.is_set():
                    self.current_video_index += 1 
                else:
                    break 
            
            self.log_message("--------------------------------------------------")
            if self.stop_event.is_set(): break

        status_message = ""
        if self.stop_event.is_set():
            status_message = "Processing stopped by user."
        elif not self.pause_event.is_set() and self.current_video_index < len(self.video_files) and len(self.video_files) > 0 :
             status_message = f"Processing paused. {self.current_video_index} of {len(self.video_files)} files processed."
             all_successful_session = True # Pausing is not an error state for the session
        elif self.current_video_index >= len(self.video_files) and len(self.video_files) > 0:
            status_message = "All files in the list have been processed." if all_successful_session else "Processing finished; some files may have had errors."
        elif not self.video_files:
            status_message = "No files were selected for processing."
        else: 
            status_message = "Processing finished."
            if not all_successful_session: status_message += " Some errors occurred."


        self.master.after(0, self._processing_finished, all_successful_session, status_message)

    def _processing_finished(self, session_success, status_message=""):
        self.is_processing = False 
        self.current_process = None 

        self.log_message("==================================================", "blue")
        
        final_log_color = "green"
        if self.stop_event.is_set():
            final_log_color = "red"
        elif not self.pause_event.is_set() and self.current_video_index < len(self.video_files) and len(self.video_files) > 0:
             final_log_color = "orange" # Paused
        elif not session_success:
             final_log_color = "red" # Errors occurred

        self.log_message(status_message, final_log_color)

        if self.master.winfo_exists():
            self.set_parameter_controls_state("normal")
            self.stop_button.config(state=tk.DISABLED)

            if self.stop_event.is_set() or (self.current_video_index >= len(self.video_files) and len(self.video_files) > 0):
                self.start_pause_resume_button.config(text="Start Processing")
                if self.current_video_index >= len(self.video_files) and not self.stop_event.is_set() and session_success:
                    messagebox.showinfo("Complete", status_message)
                elif self.stop_event.is_set():
                     messagebox.showwarning("Stopped", status_message)
                elif not session_success and self.current_video_index >= len(self.video_files):
                     messagebox.showerror("Error / Incomplete", status_message)

            elif not self.pause_event.is_set() and self.current_video_index < len(self.video_files) and len(self.video_files) > 0 : # Paused mid-list
                self.start_pause_resume_button.config(text="Resume Processing")
                messagebox.showinfo("Paused", status_message)
            else: # Default to Start, e.g. if list is empty after processing
                 self.start_pause_resume_button.config(text="Start Processing")
                 if not self.video_files and not self.stop_event.is_set(): # If list became empty
                      pass # No specific message needed if list is empty now.
                 elif not session_success and not self.stop_event.is_set(): # General error case not covered above
                      messagebox.showerror("Error / Incomplete", status_message)


if __name__ == "__main__":
    if os.name == 'nt':
        multiprocessing.freeze_support()

    if not os.path.isdir(VENV_SCRIPTS_DIR):
        error_message = (f"CRITICAL ERROR: The expected script directory does not exist:\n{VENV_SCRIPTS_DIR}\n\n"
                         "This application expects to be run from a specific directory structure, typically within a "
                         "Python virtual environment's 'Scripts' (Windows) or 'bin' (Unix-like) directory, "
                         "or a portable distribution where 'python.exe' and the 'auto_subtitle' package are correctly located relative to this GUI script.\n\n"
                         "Please ensure the application's file structure is correct.")
        print(error_message)
        try:
            root_check = tk.Tk()
            root_check.withdraw()
            messagebox.showerror("Startup Error", error_message)
            root_check.destroy()
        except tk.TclError: pass
        sys.exit(1)
    
    root = tk.Tk()
    app = SubtitleApp(root)
    
    def on_closing():
        if app.is_processing:
            if messagebox.askyesno("Exit", "Processing is currently active. Do you want to stop processing and exit?"):
                app._handle_stop() 
                if app.processing_thread and app.processing_thread.is_alive():
                    app.log_message("Waiting for processing thread to terminate before closing...", "orange")
                    app.processing_thread.join(timeout=5) # Wait up to 5 seconds
                root.destroy()
            else:
                return 
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
