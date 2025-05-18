import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import subprocess
import os
import threading
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_DIR = os.path.dirname(SCRIPT_DIR)
VENV_SCRIPTS_DIR = SCRIPT_DIR

FFMPEG_EXECUTABLE_PATH = os.path.join(VENV_SCRIPTS_DIR, "ffmpeg_binary", "bin", "ffmpeg.exe")
MODEL_CACHE_ROOT_DIR = os.path.join(VENV_SCRIPTS_DIR, "models")
PYTHON_EXECUTABLE = os.path.join(VENV_SCRIPTS_DIR, "python.exe")

AVAILABLE_MODELS_FROM_IMAGE = [
    "tiny.en", "tiny", "base.en", "base", "small.en", "small",
    "medium.en", "medium", "large-v1", "large-v2", "large-v3" 
    # "large-v3-turbo" might not be a standard model name for local whisper,
    # usually refers to API. Let's stick to known local model names.
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
DEFAULT_NO_SPEECH_THRESHOLD = "0.6" # Default for the GUI

DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop")


class SubtitleApp:
    def __init__(self, master):
        self.master = master
        master.title("Auto Subtitle GUI (Portable FFmpeg)")
        master.geometry("700x700") # Increased height slightly for the new option

        self.video_files = []

        file_frame = tk.Frame(master)
        file_frame.pack(pady=10, padx=10, fill=tk.X)

        self.select_button = tk.Button(file_frame, text="Select Video File(s)", command=self.select_files)
        self.select_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(file_frame, text="Clear List", command=self.clear_file_list)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        options_frame = tk.LabelFrame(master, text="Processing Options", padx=10, pady=10)
        options_frame.pack(pady=10, padx=10, fill=tk.X)

        model_label = tk.Label(options_frame, text="Model:")
        model_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.model_var = tk.StringVar(master)
        if DEFAULT_MODEL in AVAILABLE_MODELS_FROM_IMAGE:
            self.model_var.set(DEFAULT_MODEL)
        elif AVAILABLE_MODELS_FROM_IMAGE:
            self.model_var.set(AVAILABLE_MODELS_FROM_IMAGE[0])
        else:
            self.model_var.set("small") # Fallback if list is empty for some reason
        self.model_dropdown = ttk.Combobox(options_frame, textvariable=self.model_var,
                                           values=AVAILABLE_MODELS_FROM_IMAGE, state="readonly", width=25)
        self.model_dropdown.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)

        language_label = tk.Label(options_frame, text="Language:")
        language_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.language_var = tk.StringVar(master)
        self.language_var.set(DEFAULT_LANGUAGE_DISPLAY_NAME)
        self.language_dropdown = ttk.Combobox(options_frame, textvariable=self.language_var,
                                              values=list(LANGUAGES_MAP.keys()), state="readonly", width=25)
        self.language_dropdown.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)

        no_speech_label = tk.Label(options_frame, text="No Speech Threshold:")
        no_speech_label.grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.no_speech_threshold_var = tk.StringVar(master)
        self.no_speech_threshold_var.set(DEFAULT_NO_SPEECH_THRESHOLD)
        self.no_speech_threshold_entry = tk.Entry(options_frame, textvariable=self.no_speech_threshold_var, width=10)
        self.no_speech_threshold_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2) # sticky W to align with dropdowns
        no_speech_tooltip = tk.Label(options_frame, text="(0.0-1.0, e.g., 0.6)", fg="grey")
        no_speech_tooltip.grid(row=2, column=1, sticky=tk.W, padx=(self.no_speech_threshold_entry.winfo_reqwidth() + 15, 0), pady=2)


        output_dir_label = tk.Label(options_frame, text="SRT Output Dir:")
        output_dir_label.grid(row=3, column=0, sticky=tk.W, padx=5, pady=2) # Adjusted row
        self.output_dir_var = tk.StringVar(master)
        self.output_dir_var.set(DEFAULT_OUTPUT_DIR)
        self.output_dir_entry = tk.Entry(options_frame, textvariable=self.output_dir_var, state="readonly", width=40)
        self.output_dir_entry.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=2) # Adjusted row
        self.output_dir_button = tk.Button(options_frame, text="Browse...", command=self.select_output_dir)
        self.output_dir_button.grid(row=3, column=2, sticky=tk.EW, padx=5, pady=2) # Adjusted row
        
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

        self.start_button = tk.Button(master, text="Start Processing", command=self.start_processing_thread, bg="lightblue")
        self.start_button.pack(pady=10)

        self.log_label = tk.Label(master, text="Log Output:")
        self.log_label.pack(anchor=tk.W, padx=10)
        self.log_text = scrolledtext.ScrolledText(master, height=10, width=80, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.check_paths()

    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select SRT Output Directory", initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)
            self.log_message(f"SRT output directory set to: {directory}")

    def check_paths(self):
        paths_ok = True
        if not os.path.isdir(VENV_SCRIPTS_DIR):
            self.log_message(f"ERROR: VENV_SCRIPTS_DIR not found: {VENV_SCRIPTS_DIR}", "red")
            paths_ok = False
        if not os.path.isfile(PYTHON_EXECUTABLE):
            self.log_message(f"ERROR: Python executable not found: {PYTHON_EXECUTABLE}", "red")
            paths_ok = False

        if not os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            self.log_message(f"ERROR: Portable FFMPEG executable not found at: {FFMPEG_EXECUTABLE_PATH}", "red")
            self.log_message("Please ensure ffmpeg_binary/bin/ffmpeg.exe exists and includes necessary DLLs.", "red")
            paths_ok = False
        else:
            self.log_message(f"INFO: Using portable FFMPEG executable from: {FFMPEG_EXECUTABLE_PATH}", "green")
            ffmpeg_bin_dir = os.path.dirname(FFMPEG_EXECUTABLE_PATH)
            # Simple DLL check might not be robust, but it's a hint.
            # dll_found = any(f.lower().endswith('.dll') for f in os.listdir(ffmpeg_bin_dir))
            # if not dll_found:
            #      self.log_message(f"WARNING: Portable FFmpeg directory ({ffmpeg_bin_dir}) does not appear to contain DLLs. It might not work as expected.", "orange")

        self.log_message(f"INFO: Whisper model cache root directory set to: {MODEL_CACHE_ROOT_DIR}. Whisper will create a 'whisper' subdirectory here.", "blue")

        auto_subtitle_cli_py = os.path.join(VENV_SCRIPTS_DIR, "auto_subtitle", "cli.py")
        if not os.path.isfile(auto_subtitle_cli_py):
             self.log_message(f"ERROR: auto_subtitle.cli.py not found at: {auto_subtitle_cli_py}", "red")
             self.log_message("Ensure 'auto_subtitle' package is correctly placed in the Scripts directory.", "red")
             paths_ok = False

        if not paths_ok:
            self.start_button.config(state=tk.DISABLED)
            messagebox.showerror("Path Error", "One or more critical files/directories are missing or incorrect. Please check the script configuration and file structure.")
        else:
            self.log_message("Initial script path checks OK.", "green")


    def log_message(self, message, color=None, no_newline=False):
        def _update_log():
            self.log_text.config(state=tk.NORMAL)
            msg_str = str(message)
            if color:
                tag_name = f"color_{color.replace(' ', '_').replace(':', '')}" # Basic tag name generation
                self.log_text.tag_configure(tag_name, foreground=color)
                self.log_text.insert(tk.END, msg_str + ("" if no_newline else "\n"), tag_name)
            else:
                self.log_text.insert(tk.END, msg_str + ("" if no_newline else "\n"))
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
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

    def clear_file_list(self):
        self.video_files.clear()
        self.update_file_listbox()
        self.log_message("Cleared selected files list.")

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for f_path in self.video_files:
            self.file_listbox.insert(tk.END, os.path.basename(f_path))

    def set_ui_state(self, state):
        element_state = tk.NORMAL if state == "normal" else tk.DISABLED
        combobox_state = "readonly" if state == "normal" else tk.DISABLED
        entry_state = tk.NORMAL if state == "normal" else tk.DISABLED # For regular entries like threshold

        self.select_button.config(state=element_state)
        self.clear_button.config(state=element_state)
        self.start_button.config(state=element_state)
        self.output_dir_button.config(state=element_state)
        self.no_speech_threshold_entry.config(state=entry_state)


        self.model_dropdown.config(state=combobox_state)
        self.language_dropdown.config(state=combobox_state)

    def start_processing_thread(self):
        if not self.video_files:
            messagebox.showwarning("No Files", "Please select at least one video file.")
            return

        if not os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            messagebox.showerror("FFmpeg Error", f"Portable FFmpeg executable not found at:\n{FFMPEG_EXECUTABLE_PATH}\nCannot proceed.")
            return
        
        try:
            # Validate no_speech_threshold
            no_speech_val_str = self.no_speech_threshold_var.get()
            no_speech_val_float = float(no_speech_val_str)
            if not (0.0 <= no_speech_val_float <= 1.0):
                messagebox.showerror("Invalid Input", "No Speech Threshold must be a number between 0.0 and 1.0.")
                return
        except ValueError:
            messagebox.showerror("Invalid Input", "No Speech Threshold must be a valid number (e.g., 0.6).")
            return


        self.set_ui_state("disabled")
        self.log_message("Starting sequential video processing...", "blue")
        self.log_message("==================================================", "blue")
        print("Starting sequential video processing...")
        print("==================================================")

        thread = threading.Thread(target=self.process_videos_sequentially, daemon=True)
        thread.start()

    def process_videos_sequentially(self):
        original_cwd = os.getcwd()
        all_successful = True

        try:
            # No need to chdir if PYTHON_EXECUTABLE is absolute and cli.py is called with -m module.submodule
            # os.chdir(VENV_SCRIPTS_DIR)
            self.log_message(f"INFO: Script execution directory (cwd for subprocess): {VENV_SCRIPTS_DIR}", "gray")
            # print(f"Current working directory: {os.getcwd()}")
        except Exception as e:
            self.log_message(f"ERROR: Problem related to working directory '{VENV_SCRIPTS_DIR}': {e}", "red")
            # print(f"ERROR: Could not change directory to '{VENV_SCRIPTS_DIR}': {e}")
            self.master.after(0, self._processing_finished, False)
            return

        selected_model_name = self.model_var.get()
        selected_lang_code = LANGUAGES_MAP.get(self.language_var.get(), "en")
        output_directory = self.output_dir_var.get()
        no_speech_threshold_setting = self.no_speech_threshold_var.get()


        if not os.path.isdir(output_directory):
            try:
                os.makedirs(output_directory, exist_ok=True)
                self.log_message(f"Created output directory: {output_directory}", "green")
                # print(f"Created output directory: {output_directory}")
            except Exception as e:
                self.log_message(f"ERROR: Could not create output directory {output_directory}: {e}", "red")
                # print(f"ERROR: Could not create output directory {output_directory}: {e}")
                all_successful = False

        if all_successful:
            num_files = len(self.video_files)
            for i, video_file_path in enumerate(self.video_files):
                self.log_message(f"\nProcessing file {i+1}/{num_files}: {os.path.basename(video_file_path)}", "blue")
                # print(f"\nProcessing file {i+1}/{num_files}: {os.path.basename(video_file_path)}")

                command = [
                    PYTHON_EXECUTABLE,
                    "-u", # Unbuffered output
                    "-m", "auto_subtitle.cli", # Run as module
                    video_file_path,
                    "--model", selected_model_name,
                    "--language", selected_lang_code,
                    "--output_dir", output_directory,
                    "--srt_only", "True", # Always True for this GUI
                    "--output_srt", "True", # Also True to ensure SRT is in output_dir
                    "--verbose", "True", # Enable verbose CLI output for logging
                    "--ffmpeg_executable_path", FFMPEG_EXECUTABLE_PATH,
                    "--model_download_root", MODEL_CACHE_ROOT_DIR,
                    "--no_speech_threshold", no_speech_threshold_setting
                ]

                command_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
                self.log_message(f"Executing: {command_str}")
                # print(f"Executing: {command_str}")

                try:
                    process_flags = 0
                    if os.name == 'nt': # Windows
                        process_flags = subprocess.CREATE_NO_WINDOW

                    process_env = os.environ.copy()
                    # Ensure ffmpeg's directory is in PATH for the subprocess,
                    # especially if ffmpeg relies on DLLs in its own directory.
                    ffmpeg_bin_dir = os.path.dirname(FFMPEG_EXECUTABLE_PATH)
                    
                    # Add ffmpeg_bin_dir to the beginning of PATH for the subprocess
                    if "PATH" in process_env:
                        process_env["PATH"] = ffmpeg_bin_dir + os.pathsep + process_env["PATH"]
                    else:
                        process_env["PATH"] = ffmpeg_bin_dir
                    
                    self.log_message(f"DEBUG: Subprocess PATH will be prepended with: {ffmpeg_bin_dir}", "gray")


                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, # Redirect stderr to stdout
                        text=True, # Decodes output as text
                        bufsize=1, # Line buffered
                        cwd=VENV_SCRIPTS_DIR, # CWD for the subprocess where python -m auto_subtitle is run
                        creationflags=process_flags,
                        encoding='utf-8', errors='replace', # Ensure proper encoding
                        env=process_env
                    )

                    # Read output line by line
                    for raw_line_from_process in iter(process.stdout.readline, ''):
                        line_content = raw_line_from_process.rstrip('\n') # Remove trailing newline

                        # Handle carriage returns if present (common in progress bars)
                        parts = line_content.split('\r') # Split by carriage return

                        for part_idx, part_content in enumerate(parts):
                            if part_content: # If there's actual content
                                self.log_message(part_content) # Log each part
                                
                                # Optional: print to console as well, trying to mimic `\r` behavior
                                # if '\r' in line_content and part_idx < len(parts) - 1:
                                #     print(part_content, end='\r', flush=True)
                                # else:
                                #     print(part_content, flush=True)


                    process.stdout.close() # Close the stdout stream
                    return_code = process.wait() # Wait for the process to complete

                    if return_code == 0:
                        msg_success = f"Successfully processed {os.path.basename(video_file_path)}."
                        self.log_message(msg_success, "green")
                        # print(msg_success)
                    else:
                        msg_error = f"ERROR processing {os.path.basename(video_file_path)}. CLI script returned code: {return_code}"
                        self.log_message(msg_error, "red")
                        # print(msg_error)
                        all_successful = False
                except FileNotFoundError:
                    msg_fnf = f"ERROR: Command not found. Ensure Python executable ({PYTHON_EXECUTABLE}) is correct and 'auto_subtitle.cli' is accessible via -m."
                    self.log_message(msg_fnf, "red")
                    # print(msg_fnf)
                    all_successful = False
                    break # Stop processing further files if a fundamental command is not found
                except Exception as e:
                    msg_exc = f"An unexpected error occurred while processing {os.path.basename(video_file_path)}: {e}"
                    self.log_message(msg_exc, "red")
                    # print(msg_exc)
                    all_successful = False

                self.log_message("--------------------------------------------------")
                # print("--------------------------------------------------")

        else: # if not all_successful (due to output directory issue initially)
             msg_halt = "Processing halted due to output directory issue."
             self.log_message(msg_halt, "red")
             # print(msg_halt)

        # Restore original CWD if it was changed (though current logic avoids chdir)
        # if os.getcwd() != original_cwd:
        #     try:
        #         os.chdir(original_cwd)
        #         msg_restore_wd = f"Restored working directory to: {os.getcwd()}"
        #         self.log_message(msg_restore_wd)
        #         # print(msg_restore_wd)
        #     except Exception as e:
        #          msg_err_restore = f"Error restoring working directory: {e}"
        #          self.log_message(msg_err_restore, "orange")
                 # print(msg_err_restore)

        self.master.after(0, self._processing_finished, all_successful)

    def _processing_finished(self, success_flag=True):
        self.log_message("==================================================", "blue")
        # print("==================================================")
        if success_flag and self.video_files: # If all files attempted were successful
            self.log_message("Sequential processing finished successfully.", "green")
            # print("Sequential processing finished successfully.")
            messagebox.showinfo("Complete", "All selected videos have been processed.")
        elif not self.video_files: # If no files were selected in the first place
             self.log_message("No files were selected for processing.", "orange")
             # print("No files were selected for processing.")
        else: # If some files failed or processing was halted
            self.log_message("Processing finished with errors or some files were not processed.", "red")
            # print("Processing finished with errors or some files were not processed.")
            messagebox.showerror("Error / Incomplete", "Processing encountered errors or did not complete successfully for all files. Check logs for details.")

        self.set_ui_state("normal")


if __name__ == "__main__":
    # Basic check for VENV_SCRIPTS_DIR, essential for PYTHON_EXECUTABLE and module path
    if not os.path.isdir(VENV_SCRIPTS_DIR):
        error_message = (f"CRITICAL ERROR: The expected script directory does not exist:\n{VENV_SCRIPTS_DIR}\n\n"
                         "This application expects to be run from a specific directory structure, typically within a "
                         "Python virtual environment's 'Scripts' (Windows) or 'bin' (Unix-like) directory, "
                         "or a portable distribution where 'python.exe' and the 'auto_subtitle' package are correctly located relative to this GUI script.\n\n"
                         "Please ensure the application's file structure is correct.")
        print(error_message) # Print to console for non-GUI environments or if Tk fails
        try:
            # Attempt to show a Tkinter error message if Tkinter is available
            root_check = tk.Tk()
            root_check.withdraw() # Hide the main Tk window
            messagebox.showerror("Startup Error", error_message)
            root_check.destroy()
        except tk.TclError:
            # If Tkinter itself fails (e.g., no display), the console message is the fallback
            pass 
        sys.exit(1)


    root = tk.Tk()
    app = SubtitleApp(root)
    root.mainloop()