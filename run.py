import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
import subprocess
import os
import threading
import sys

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_DIR = os.path.dirname(SCRIPT_DIR)
VENV_SCRIPTS_DIR = SCRIPT_DIR # Assuming scripts are in the venv's Scripts directory

# Construct paths relative to the script's location
FFMPEG_EXECUTABLE_PATH = os.path.join(VENV_SCRIPTS_DIR, "ffmpeg_binary", "bin", "ffmpeg.exe")
# MODEL_DIR is primarily for info, Whisper manages its own cache location
MODEL_DIR = os.path.join(VENV_SCRIPTS_DIR, ".cache", "whisper") 
PYTHON_EXECUTABLE = os.path.join(VENV_SCRIPTS_DIR, "python.exe") # Path to python.exe in the venv

# These values are taken from the whisper/available_models().
# Hardcoding them here for the dropdown values.
AVAILABLE_MODELS_FROM_IMAGE = [
    "tiny.en", "tiny", "base.en", "base", "small.en", "small", 
    "medium.en", "medium", "large-v1", "large-v2", "large-v3", "large-v3-turbo"
]
DEFAULT_MODEL = "small" # Default model to pre-select

# Mapping for language dropdown
LANGUAGES_MAP = {
    "Auto Detect": "auto", "English": "en", "Spanish": "es", "French": "fr",
    "German": "de", "Italian": "it", "Japanese": "ja", "Chinese": "zh",
    "Russian": "ru", "Portuguese": "pt", "Afrikaans": "af", "Arabic": "ar",
    "Hindi": "hi", "Korean": "ko", "Turkish": "tr", "Ukrainian": "uk",
    "Czech": "cs", "Dutch": "nl", "Greek": "el", "Hungarian": "hu",
    "Indonesian": "id", "Malay": "ms", "Norwegian": "no", "Polish": "pl",
    "Swedish": "sv", "Thai": "th", "Vietnamese": "vi"
    # Add more languages if needed based on whisper.available_languages()
}
DEFAULT_LANGUAGE_DISPLAY_NAME = "English" # Default language to pre-select

# Default output directory (e.g., user's Desktop)
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
# --- End Configuration ---


class SubtitleApp:
    def __init__(self, master):
        self.master = master
        master.title("Auto Subtitle GUI (Portable FFmpeg)")
        master.geometry("700x650") # Initial window size

        self.video_files = [] # List to store full paths of selected video files

        # Frame for file selection buttons
        file_frame = tk.Frame(master)
        file_frame.pack(pady=10, padx=10, fill=tk.X)

        self.select_button = tk.Button(file_frame, text="Select Video File(s)", command=self.select_files)
        self.select_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(file_frame, text="Clear List", command=self.clear_file_list)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        # Frame for processing options (Model, Language, Output Dir)
        options_frame = tk.LabelFrame(master, text="Processing Options", padx=10, pady=10)
        options_frame.pack(pady=10, padx=10, fill=tk.X)

        # Model Selection
        model_label = tk.Label(options_frame, text="Model:")
        model_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.model_var = tk.StringVar(master)
        # Set default model if available, otherwise set to the first in the list
        if DEFAULT_MODEL in AVAILABLE_MODELS_FROM_IMAGE:
            self.model_var.set(DEFAULT_MODEL)
        elif AVAILABLE_MODELS_FROM_IMAGE:
            self.model_var.set(AVAILABLE_MODELS_FROM_IMAGE[0])
        else:
            self.model_var.set("small") # Fallback
        self.model_dropdown = ttk.Combobox(options_frame, textvariable=self.model_var,
                                           values=AVAILABLE_MODELS_FROM_IMAGE, state="readonly", width=25)
        self.model_dropdown.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)

        # Language Selection
        language_label = tk.Label(options_frame, text="Language:")
        language_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.language_var = tk.StringVar(master)
        self.language_var.set(DEFAULT_LANGUAGE_DISPLAY_NAME)
        self.language_dropdown = ttk.Combobox(options_frame, textvariable=self.language_var,
                                              values=list(LANGUAGES_MAP.keys()), state="readonly", width=25)
        self.language_dropdown.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)

        # Output Directory Selection
        output_dir_label = tk.Label(options_frame, text="SRT Output Dir:")
        output_dir_label.grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.output_dir_var = tk.StringVar(master)
        self.output_dir_var.set(DEFAULT_OUTPUT_DIR)
        self.output_dir_entry = tk.Entry(options_frame, textvariable=self.output_dir_var, state="readonly", width=40)
        self.output_dir_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=2)
        self.output_dir_button = tk.Button(options_frame, text="Browse...", command=self.select_output_dir)
        self.output_dir_button.grid(row=2, column=2, sticky=tk.EW, padx=5, pady=2)
        options_frame.columnconfigure(1, weight=1) # Make the output directory entry expandable

        # Frame and Listbox to display selected files
        self.file_listbox_label = tk.Label(master, text="Selected Files:")
        self.file_listbox_label.pack(anchor=tk.W, padx=10)
        self.file_listbox_frame = tk.Frame(master)
        self.file_listbox_frame.pack(pady=5, padx=10, fill=tk.X)
        self.file_listbox_scrollbar = tk.Scrollbar(self.file_listbox_frame, orient=tk.VERTICAL)
        self.file_listbox = tk.Listbox(self.file_listbox_frame, selectmode=tk.EXTENDED, height=5, yscrollcommand=self.file_listbox_scrollbar.set)
        self.file_listbox_scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # Make listbox expandable

        # Start Processing Button
        self.start_button = tk.Button(master, text="Start Processing", command=self.start_processing_thread, bg="lightblue")
        self.start_button.pack(pady=10)

        # Log Output Area
        self.log_label = tk.Label(master, text="Log Output:")
        self.log_label.pack(anchor=tk.W, padx=10)
        # Use ScrolledText for automatic scrolling and handling large output
        self.log_text = scrolledtext.ScrolledText(master, height=10, width=80, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True) # Make log area expandable

        # Initial checks for required paths
        self.check_paths()

    # Opens a directory selection dialog for the output directory
    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select SRT Output Directory", initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)
            self.log_message(f"SRT output directory set to: {directory}")

    # Performs initial checks for required files/directories
    def check_paths(self):
        paths_ok = True
        # Check if the venv Scripts directory exists (should be where this script is)
        if not os.path.isdir(VENV_SCRIPTS_DIR):
            self.log_message(f"ERROR: VENV_SCRIPTS_DIR not found: {VENV_SCRIPTS_DIR}", "red")
            paths_ok = False
        # Check if the python executable in the venv exists
        if not os.path.isfile(PYTHON_EXECUTABLE):
            self.log_message(f"ERROR: Python executable not found: {PYTHON_EXECUTABLE}", "red")
            paths_ok = False
        
        # Check if the portable FFmpeg executable exists
        if not os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            self.log_message(f"ERROR: Portable FFMPEG executable not found at: {FFMPEG_EXECUTABLE_PATH}", "red")
            self.log_message("Please ensure ffmpeg_binary/bin/ffmpeg.exe exists and includes necessary DLLs.", "red")
            paths_ok = False
        else:
            self.log_message(f"INFO: Using portable FFMPEG executable from: {FFMPEG_EXECUTABLE_PATH}", "green")
            # Check if the ffmpeg_binary/bin directory contains DLLs (heuristic)
            ffmpeg_bin_dir = os.path.dirname(FFMPEG_EXECUTABLE_PATH)
            dll_found = any(f.lower().endswith('.dll') for f in os.listdir(ffmpeg_bin_dir))
            if not dll_found:
                 self.log_message(f"WARNING: Portable FFmpeg directory ({ffmpeg_bin_dir}) does not appear to contain DLLs. It might not work.", "orange")


        # Info message about the model cache directory (Whisper manages this internally)
        if not os.path.isdir(MODEL_DIR):
             self.log_message(f"INFO: Local MODEL_DIR ({MODEL_DIR}) not found. Whisper will use its default cache and may download models.", "blue")
        else:
             self.log_message(f"INFO: Local MODEL_DIR is set to ({MODEL_DIR}). Whisper usually manages its own cache.", "blue")

        # Check if the auto_subtitle cli script exists
        auto_subtitle_cli_py = os.path.join(VENV_SCRIPTS_DIR, "auto_subtitle", "cli.py")
        if not os.path.isfile(auto_subtitle_cli_py):
             self.log_message(f"ERROR: auto_subtitle.cli.py not found at: {auto_subtitle_cli_py}", "red")
             self.log_message("Ensure 'auto_subtitle' package is correctly placed in the Scripts directory.", "red")
             paths_ok = False

        # If any critical path is missing, disable the start button and show an error
        if not paths_ok:
            self.start_button.config(state=tk.DISABLED)
            messagebox.showerror("Path Error", "One or more critical files/directories are missing or incorrect. Please check the script configuration and file structure.")
        else:
            self.log_message("Initial script path checks OK.", "green")


    # Adds messages to the GUI log area. Uses threading-safe method via after()
    def log_message(self, message, color=None, no_newline=False):
        def _update_log():
            self.log_text.config(state=tk.NORMAL)
            msg_str = str(message)
            if color:
                tag_name = f"color_{color.replace(' ', '_').replace(':', '')}" # Create a unique tag name
                self.log_text.tag_configure(tag_name, foreground=color) # Configure the tag color
                self.log_text.insert(tk.END, msg_str + ("" if no_newline else "\n"), tag_name) # Insert with tag
            else:
                self.log_text.insert(tk.END, msg_str + ("" if no_newline else "\n")) # Insert without tag
            self.log_text.see(tk.END) # Scroll to the end
            self.log_text.config(state=tk.DISABLED) # Disable editing
        self.master.after(0, _update_log) # Use after() for thread-safe GUI update

    # Opens a file dialog to select video files
    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=(("Video files", "*.avi *.mp4 *.mkv *.mov *.webm"), ("All files", "*.*"))
        )
        if files:
            for f_path in files:
                if f_path not in self.video_files: # Avoid adding duplicates
                    self.video_files.append(f_path)
            self.update_file_listbox()

    # Clears the list of selected files
    def clear_file_list(self):
        self.video_files.clear()
        self.update_file_listbox()
        self.log_message("Cleared selected files list.")

    # Updates the Listbox widget with the basenames of selected files
    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END) # Clear current listbox contents
        for f_path in self.video_files:
            self.file_listbox.insert(tk.END, os.path.basename(f_path)) # Add basename to listbox

    # Sets the state of various UI elements (buttons, dropdowns)
    def set_ui_state(self, state):
        element_state = tk.NORMAL if state == "normal" else tk.DISABLED
        combobox_state = "readonly" if state == "normal" else tk.DISABLED # Combobox uses "readonly" when enabled

        self.select_button.config(state=element_state)
        self.clear_button.config(state=element_state)
        self.start_button.config(state=element_state)
        self.output_dir_button.config(state=element_state)
        
        self.model_dropdown.config(state=combobox_state)
        self.language_dropdown.config(state=combobox_state)

    # Starts the processing thread when the Start button is clicked
    def start_processing_thread(self):
        if not self.video_files:
            messagebox.showwarning("No Files", "Please select at least one video file.")
            return
        
        if not os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            messagebox.showerror("FFmpeg Error", f"Portable FFmpeg executable not found at:\n{FFMPEG_EXECUTABLE_PATH}\nCannot proceed.")
            return
            
        self.set_ui_state("disabled") # Disable UI while processing
        self.log_message("Starting sequential video processing...", "blue")
        self.log_message("==================================================", "blue")
        # Print start messages to console as well
        print("Starting sequential video processing...")
        print("==================================================")

        # Start processing in a separate thread to keep the GUI responsive
        thread = threading.Thread(target=self.process_videos_sequentially, daemon=True)
        thread.start()

    # Main processing logic - runs in a separate thread
    def process_videos_sequentially(self):
        original_cwd = os.getcwd() # Store original current working directory
        all_successful = True # Flag to track if all files were processed successfully

        # Change working directory to the scripts directory (important for python -m)
        try:
            self.log_message(f"Changing working directory to: {VENV_SCRIPTS_DIR}")
            print(f"Changing working directory to: {VENV_SCRIPTS_DIR}")
            os.chdir(VENV_SCRIPTS_DIR)
            self.log_message(f"Current working directory: {os.getcwd()}")
            print(f"Current working directory: {os.getcwd()}")
        except Exception as e:
            self.log_message(f"ERROR: Could not change directory to '{VENV_SCRIPTS_DIR}': {e}", "red")
            print(f"ERROR: Could not change directory to '{VENV_SCRIPTS_DIR}': {e}")
            # Use after() to call _processing_finished on the main thread
            self.master.after(0, self._processing_finished, False) 
            return # Stop processing if directory change fails

        # Get selected options
        selected_model_name = self.model_var.get()
        selected_lang_code = LANGUAGES_MAP.get(self.language_var.get(), "en") # Get language code
        output_directory = self.output_dir_var.get()

        # Create output directory if it doesn't exist
        if not os.path.isdir(output_directory):
            try:
                os.makedirs(output_directory, exist_ok=True)
                self.log_message(f"Created output directory: {output_directory}", "green")
                print(f"Created output directory: {output_directory}")
            except Exception as e:
                self.log_message(f"ERROR: Could not create output directory {output_directory}: {e}", "red")
                print(f"ERROR: Could not create output directory {output_directory}: {e}")
                all_successful = False # Mark as unsuccessful

        # Process each video file sequentially
        if all_successful: # Only proceed if output directory is okay
            num_files = len(self.video_files)
            for i, video_file_path in enumerate(self.video_files):
                self.log_message(f"\nProcessing file {i+1}/{num_files}: {os.path.basename(video_file_path)}", "blue")
                print(f"\nProcessing file {i+1}/{num_files}: {os.path.basename(video_file_path)}")

                # Construct the command to run auto_subtitle.cli
                command = [
                    PYTHON_EXECUTABLE, # Use the specific python.exe from the venv
                    "-u", # Unbuffered stdout/stderr (important for live output)
                    "-m", "auto_subtitle.cli", # Run cli.py as a module
                    video_file_path,
                    "--model", selected_model_name,
                    "--language", selected_lang_code,
                    "--output_dir", output_directory,
                    "--srt_only", "True", # Only generate SRT
                    "--output_srt", "True", # Output the SRT file
                    "--verbose", "True", # Enable verbose output from cli.py/Whisper
                    "--ffmpeg_executable_path", FFMPEG_EXECUTABLE_PATH # Pass portable FFmpeg path
                ]

                command_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command) # Format command for display
                self.log_message(f"Executing: {command_str}")
                print(f"Executing: {command_str}")

                try:
                    # Use CREATE_NO_WINDOW on Windows to prevent a separate console window
                    process_flags = 0
                    if os.name == 'nt':
                        process_flags = subprocess.CREATE_NO_WINDOW
                    
                    # Copy current environment and modify PATH to include portable FFmpeg bin directory
                    # This is essential for the 'whisper' library to find 'ffmpeg' when called by name
                    process_env = os.environ.copy()
                    ffmpeg_bin_dir = os.path.dirname(FFMPEG_EXECUTABLE_PATH) 
                    
                    if "PATH" in process_env:
                        # Prepend the ffmpeg bin directory to the PATH
                        process_env["PATH"] = ffmpeg_bin_dir + os.pathsep + process_env["PATH"]
                    else:
                        # If PATH doesn't exist, just set it
                        process_env["PATH"] = ffmpeg_bin_dir
                    
                    self.log_message(f"DEBUG: Subprocess PATH will be prepended with: {ffmpeg_bin_dir}.", "gray")
                    # Optional: print the actual modified PATH start
                    # print(f"DEBUG: Subprocess PATH starts with: {process_env.get('PATH', '')[:150]}...") 

                    # Start the subprocess
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE, # Capture standard output
                        stderr=subprocess.STDOUT, # Redirect standard error to standard output
                        text=True, # Decode output as text (using specified encoding)
                        bufsize=1, # Line buffered output
                        cwd=VENV_SCRIPTS_DIR, # Run the subprocess from the scripts directory
                        creationflags=process_flags,
                        encoding='utf-8', errors='replace', # Handle potential encoding issues
                        env=process_env # Pass the modified environment with updated PATH
                    )

                    # Read and process output line by line in real-time
                    for raw_line_from_process in iter(process.stdout.readline, ''):
                        line_content = raw_line_from_process.rstrip('\n') # Remove trailing newline

                        # Split lines by carriage return to handle in-place updates (like Whisper progress bars)
                        parts = line_content.split('\r')

                        for part_idx, part_content in enumerate(parts):
                            if part_content: # Avoid processing empty strings
                                # Log to GUI
                                self.log_message(part_content)

                                # Print to console (handling carriage returns)
                                if '\r' in line_content and part_idx < len(parts) - 1:
                                    # If it's an in-place update part (not the last part of a line with \r)
                                    print(part_content, end='\r', flush=True)
                                else:
                                    # Otherwise (normal line or last part of a \r line), print with a newline
                                    print(part_content, flush=True)
                    
                    # Close stdout pipe and wait for the subprocess to finish
                    process.stdout.close()
                    return_code = process.wait()

                    # Check return code and log status
                    if return_code == 0:
                        msg_success = f"Successfully processed {os.path.basename(video_file_path)}."
                        self.log_message(msg_success, "green")
                        print(msg_success)
                    else:
                        msg_error = f"ERROR processing {os.path.basename(video_file_path)}. Return code: {return_code}"
                        self.log_message(msg_error, "red")
                        print(msg_error)
                        all_successful = False # Mark process as failed
                except FileNotFoundError:
                    msg_fnf = f"ERROR: Command not found. Ensure Python executable ({PYTHON_EXECUTABLE}) is correct and 'auto_subtitle.cli' is accessible."
                    self.log_message(msg_fnf, "red")
                    print(msg_fnf)
                    all_successful = False # Mark process as failed
                    break # Stop processing subsequent files if the executable isn't found
                except Exception as e:
                    msg_exc = f"An unexpected error occurred with {os.path.basename(video_file_path)}: {e}"
                    self.log_message(msg_exc, "red")
                    print(msg_exc)
                    all_successful = False # Mark process as failed
                
                # Separator in logs and console
                self.log_message("--------------------------------------------------")
                print("--------------------------------------------------")

        else: # If output directory creation failed
             msg_halt = "Processing halted due to output directory issue."
             self.log_message(msg_halt, "red")
             print(msg_halt)

        # Restore original working directory
        try:
            os.chdir(original_cwd)
            msg_restore_wd = f"Restored working directory to: {os.getcwd()}"
            self.log_message(msg_restore_wd)
            print(msg_restore_wd)
        except Exception as e:
             msg_err_restore = f"Error restoring working directory: {e}"
             self.log_message(msg_err_restore, "orange")
             print(msg_err_restore)

        # Call the finished method on the main thread
        self.master.after(0, self._processing_finished, all_successful)

    # Called on the main thread when processing is finished
    def _processing_finished(self, success_flag=True):
        self.log_message("==================================================", "blue")
        print("==================================================")
        if success_flag and self.video_files:
            self.log_message("Sequential processing finished.", "green")
            print("Sequential processing finished.")
            messagebox.showinfo("Complete", "All selected videos have been processed.")
        elif not self.video_files:
             self.log_message("No files were selected for processing.", "orange")
             print("No files were selected for processing.")
        else:
            self.log_message("Processing finished with errors or some files were not processed.", "red")
            print("Processing finished with errors or some files were not processed.")
            messagebox.showerror("Error / Incomplete", "Processing encountered errors or did not complete successfully for all files. Check logs.")
        
        self.set_ui_state("normal") # Re-enable UI elements

# Entry point of the script
if __name__ == "__main__":
    # Basic check to see if the scripts directory exists
    if not os.path.isdir(VENV_SCRIPTS_DIR):
        print(f"CRITICAL ERROR: VENV_SCRIPTS_DIR does not exist: {VENV_SCRIPTS_DIR}")
        print("The application cannot start. Please ensure the script is in your venv's Scripts directory.")
        # Try to show a Tkinter error message if possible
        try:
            root_check = tk.Tk()
            root_check.withdraw() # Hide the main window
            messagebox.showerror("Startup Error", f"CRITICAL ERROR: VENV_SCRIPTS_DIR does not exist:\n{VENV_SCRIPTS_DIR}\n\nPlease ensure this script is located in the 'Scripts' directory of your Python virtual environment.")
            root_check.destroy() # Destroy the temporary root window
        except tk.TclError:
            # If Tkinter fails, just print to console
            pass
        exit(1) # Exit the application

    # Create and run the Tkinter application
    root = tk.Tk()
    app = SubtitleApp(root)
    root.mainloop()