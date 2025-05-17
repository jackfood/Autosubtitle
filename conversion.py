import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import os
import subprocess
import threading
import ffmpeg
import sys

VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm')
FFMPEG_PRESET = 'medium' 

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_BINARY_SUBDIR = "ffmpeg_binary"
FFMPEG_BIN_DIR = os.path.join(SCRIPT_DIR, FFMPEG_BINARY_SUBDIR, "bin")
FFMPEG_EXECUTABLE_PATH = os.path.join(FFMPEG_BIN_DIR, "ffmpeg.exe")
FFPROBE_EXECUTABLE_PATH = os.path.join(FFMPEG_BIN_DIR, "ffprobe.exe")

LIGHT_BLUE_THEME = {
    "bg": "#E1F5FE",
    "fg": "#0D47A1",
    "button_bg": "#B3E5FC",
    "button_fg": "#01579B",
    "entry_bg": "#FFFFFF",
    "entry_fg": "#0D47A1",
    "accent": "#03A9F4",
    "text_area_bg": "#F0F8FF",
    "success_fg": "#00796B",
    "error_fg": "#D32F2F",
    "warning_fg": "#FFA000",
    "info_fg": "#0288D1",
    "listbox_bg": "#FFFFFF",
    "listbox_fg": "#0D47A1",
    "listbox_srt_ok_fg": "#004D40",
    "listbox_srt_missing_fg": "#BF360C",
    "slider_label_fg": "#01579B",
}

def escape_srt_path_for_ffmpeg_filter(srt_path):
    path = srt_path.replace('\\', '/')
    if os.name == 'nt':
        if len(path) > 1 and path[1] == ':' and path[0].isalpha():
            path = path[0] + '\\:' + path[2:]
    return path

def get_video_files_from_paths(paths):
    video_files_to_process = []
    for path_item in paths:
        if os.path.isfile(path_item) and path_item.lower().endswith(VIDEO_EXTENSIONS):
            video_files_to_process.append(path_item)
        elif os.path.isdir(path_item):
            for root, _, files in os.walk(path_item):
                for file in files:
                    if file.lower().endswith(VIDEO_EXTENSIONS):
                        video_files_to_process.append(os.path.join(root, file))
    return list(set(video_files_to_process))

def encode_single_video(video_path, srt_path, output_dir,
                        ffmpeg_executable_path, ffprobe_executable_path,
                        video_bitrate_kbps, audio_bitrate_kbps):
    base, _ = os.path.splitext(os.path.basename(video_path))
    output_filename = f"{base}_hardsub.mp4"
    output_path = os.path.join(output_dir, output_filename)

    if os.path.exists(output_path):
        return video_path, "skipped", f"Output file already exists: {output_path}"

    try:
        ffmpeg_run_opts = {}
        if not ffmpeg_executable_path or not os.path.isfile(ffmpeg_executable_path):
            return video_path, "error", f"ffmpeg executable not found at {ffmpeg_executable_path}"
        ffmpeg_run_opts['cmd'] = ffmpeg_executable_path

        escaped_srt_for_filter = escape_srt_path_for_ffmpeg_filter(srt_path)
        subtitle_filter_value = f"subtitles=filename='{escaped_srt_for_filter}'"

        stream = ffmpeg.input(video_path)
        output_params = {
            'vf': subtitle_filter_value,
            'vcodec': 'libx264',
            'acodec': 'aac',
            'preset': FFMPEG_PRESET,
            'b:v': f"{video_bitrate_kbps}k",
            'b:a': f"{audio_bitrate_kbps}k",
            'strict': '-2'
        }
        stream = ffmpeg.output(stream, output_path, **output_params)
        ffmpeg.run(stream, overwrite_output=True, quiet=False, **ffmpeg_run_opts)
        return video_path, "success", f"Successfully encoded: {output_path}"

    except ffmpeg.Error as e:
        stderr_output = e.stderr.decode(sys.getdefaultencoding(), errors='ignore') if e.stderr else "No stderr output"
        error_message = f"FFmpeg error for {os.path.basename(video_path)}: {stderr_output}"
        return video_path, "error", error_message
    except Exception as e:
        error_message = f"General error for {os.path.basename(video_path)}: {str(e)}"
        return video_path, "error", error_message

class HardcodeApp:
    def __init__(self, master):
        self.master = master
        master.title("Video Subtitle Hardcoder Pro")
        master.geometry("900x800") 
        master.configure(bg=LIGHT_BLUE_THEME["bg"])

        self.selected_files_map = {}
        self.output_dir = tk.StringVar(value=os.getcwd())
        self.is_processing = False
        self.ffmpeg_ready = False
        self.ffprobe_ready = False
        self.log_entries_for_file = []
        self.has_errors_in_batch = False
        self.force_shutdown_var = tk.BooleanVar(value=False)

        self.video_bitrate_var = tk.IntVar(value=1500) 
        self.audio_bitrate_var = tk.IntVar(value=128)  
        self.video_bitrate_display_str = tk.StringVar()
        self.audio_bitrate_display_str = tk.StringVar()
        self.estimated_size_str = tk.StringVar(value="Estimated Size: N/A MB")
        self.selected_video_duration_sec = 0.0
        self.selected_video_path_for_estimation = None
        self._update_bitrate_display_labels() 

        self.file_list_paths_ordered = [] 

        self.setup_styles()
        self.create_widgets()
        self.check_portable_ffmpeg_ffprobe()
        self.update_estimated_size() 

    def _update_bitrate_display_labels(self):
        self.video_bitrate_display_str.set(f"{self.video_bitrate_var.get()} kbps")
        self.audio_bitrate_display_str.set(f"{self.audio_bitrate_var.get()} kbps")

    def setup_styles(self):
        style = ttk.Style(self.master)
        style.theme_use('clam')

        style.configure("TFrame", background=LIGHT_BLUE_THEME["bg"])
        style.configure("TLabel", background=LIGHT_BLUE_THEME["bg"], foreground=LIGHT_BLUE_THEME["fg"], font=('Segoe UI', 10))
        style.configure("Accent.TLabel", background=LIGHT_BLUE_THEME["bg"], foreground=LIGHT_BLUE_THEME["slider_label_fg"], font=('Segoe UI', 10, 'bold'))
        style.configure("TButton", background=LIGHT_BLUE_THEME["button_bg"], foreground=LIGHT_BLUE_THEME["button_fg"], font=('Segoe UI', 10, 'bold'), padding=5)
        style.map("TButton", background=[('active', LIGHT_BLUE_THEME["accent"])])
        style.configure("TEntry", fieldbackground=LIGHT_BLUE_THEME["entry_bg"], foreground=LIGHT_BLUE_THEME["entry_fg"], font=('Segoe UI', 10))
        style.configure("TLabelFrame", background=LIGHT_BLUE_THEME["bg"], foreground=LIGHT_BLUE_THEME["fg"], font=('Segoe UI', 11, 'bold'))
        style.configure("TLabelFrame.Label", background=LIGHT_BLUE_THEME["bg"], foreground=LIGHT_BLUE_THEME["fg"], font=('Segoe UI', 11, 'bold'))
        style.configure("TProgressbar", troughcolor=LIGHT_BLUE_THEME["button_bg"], background=LIGHT_BLUE_THEME["accent"], thickness=25)
        style.configure("TCheckbutton", background=LIGHT_BLUE_THEME["bg"], foreground=LIGHT_BLUE_THEME["fg"], font=('Segoe UI', 10))
        style.map("TCheckbutton", indicatorcolor=[('selected', LIGHT_BLUE_THEME["accent"])])
        style.configure("Horizontal.TScale", background=LIGHT_BLUE_THEME["bg"], troughcolor=LIGHT_BLUE_THEME["button_bg"])

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.LabelFrame(main_frame, text="Input Selection")
        input_frame.pack(padx=10, pady=(10,5), fill=tk.X)
        btn_select_files = ttk.Button(input_frame, text="Select Video File(s)", command=self.select_video_files)
        btn_select_files.pack(side=tk.LEFT, padx=5, pady=5)
        btn_select_folder = ttk.Button(input_frame, text="Select Video Folder", command=self.select_video_folder)
        btn_select_folder.pack(side=tk.LEFT, padx=5, pady=5)
        btn_clear_list = ttk.Button(input_frame, text="Clear List", command=self.clear_file_list)
        btn_clear_list.pack(side=tk.LEFT, padx=5, pady=5)

        list_frame = ttk.LabelFrame(main_frame, text="Files to Process")
        list_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, 
                                       bg=LIGHT_BLUE_THEME["listbox_bg"], fg=LIGHT_BLUE_THEME["listbox_fg"],
                                       font=('Segoe UI', 10), relief=tk.SOLID, borderwidth=1, exportselection=False)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=list_scrollbar.set)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_list_select)

        quality_frame = ttk.LabelFrame(main_frame, text="Quality & Estimation")
        quality_frame.pack(padx=10, pady=5, fill=tk.X)
        
        q_grid = ttk.Frame(quality_frame)
        q_grid.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(q_grid, text="Video Bitrate:").grid(row=0, column=0, sticky=tk.W, padx=2, pady=2)
        self.video_bitrate_slider = ttk.Scale(q_grid, from_=250, to=10000, orient=tk.HORIZONTAL, length=200,
                                              variable=self.video_bitrate_var, command=self._slider_changed, style="Horizontal.TScale")
        self.video_bitrate_slider.grid(row=0, column=1, sticky=tk.EW, padx=2, pady=2)
        self.video_bitrate_label = ttk.Label(q_grid, textvariable=self.video_bitrate_display_str, style="Accent.TLabel", width=10, anchor=tk.W)
        self.video_bitrate_label.grid(row=0, column=2, sticky=tk.W, padx=2, pady=2)

        ttk.Label(q_grid, text="Audio Bitrate:").grid(row=1, column=0, sticky=tk.W, padx=2, pady=2)
        self.audio_bitrate_slider = ttk.Scale(q_grid, from_=32, to=320, orient=tk.HORIZONTAL, length=200,
                                              variable=self.audio_bitrate_var, command=self._slider_changed, style="Horizontal.TScale")
        self.audio_bitrate_slider.grid(row=1, column=1, sticky=tk.EW, padx=2, pady=2)
        self.audio_bitrate_label = ttk.Label(q_grid, textvariable=self.audio_bitrate_display_str, style="Accent.TLabel", width=10, anchor=tk.W)
        self.audio_bitrate_label.grid(row=1, column=2, sticky=tk.W, padx=2, pady=2)
        
        q_grid.columnconfigure(1, weight=1) 

        self.estimated_size_label = ttk.Label(quality_frame, textvariable=self.estimated_size_str, font=('Segoe UI', 10, 'italic'))
        self.estimated_size_label.pack(padx=5, pady=(0,5), anchor=tk.W)

        output_frame = ttk.LabelFrame(main_frame, text="Output Settings")
        output_frame.pack(padx=10, pady=5, fill=tk.X)
        ttk.Label(output_frame, text="Output Directory:").pack(side=tk.LEFT, padx=(5,0), pady=5)
        self.output_dir_entry = ttk.Entry(output_frame, textvariable=self.output_dir, width=60)
        self.output_dir_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        btn_browse_output = ttk.Button(output_frame, text="Browse...", command=self.select_output_dir)
        btn_browse_output.pack(side=tk.LEFT, padx=5, pady=5)

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(padx=10, pady=5, fill=tk.X)
        self.progress_bar = ttk.Progressbar(control_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=(0,5), pady=5, fill=tk.X, expand=True)
        self.progress_label = ttk.Label(control_frame, text="0%", font=('Segoe UI', 10, 'bold'))
        self.progress_label.pack(side=tk.LEFT, padx=5, pady=5)
        self.start_button = ttk.Button(control_frame, text="Start Encoding", command=self.start_encoding_thread)
        self.start_button.pack(side=tk.RIGHT, padx=5, pady=5)

        shutdown_frame = ttk.Frame(main_frame)
        shutdown_frame.pack(padx=10, pady=(0,5), fill=tk.X)
        self.shutdown_checkbox = ttk.Checkbutton(shutdown_frame, text="Force shutdown computer 20 secs after completion/error", variable=self.force_shutdown_var)
        self.shutdown_checkbox.pack(side=tk.LEFT, padx=5, pady=5)

        log_frame = ttk.LabelFrame(main_frame, text="Log")
        log_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD, state=tk.DISABLED,
                                                  bg=LIGHT_BLUE_THEME["text_area_bg"], fg=LIGHT_BLUE_THEME["fg"],
                                                  font=('Segoe UI', 9), relief=tk.SOLID, borderwidth=1)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.tag_configure("success", foreground=LIGHT_BLUE_THEME["success_fg"])
        self.log_text.tag_configure("error", foreground=LIGHT_BLUE_THEME["error_fg"])
        self.log_text.tag_configure("warning", foreground=LIGHT_BLUE_THEME["warning_fg"])
        self.log_text.tag_configure("info", foreground=LIGHT_BLUE_THEME["info_fg"])

    def check_portable_ffmpeg_ffprobe(self):
        self.ffmpeg_ready = False
        self.ffprobe_ready = False
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        if os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            try:
                subprocess.run([FFMPEG_EXECUTABLE_PATH, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
                self.log_message(f"INFO: Portable ffmpeg found: {FFMPEG_EXECUTABLE_PATH}", "info")
                self.ffmpeg_ready = True
            except Exception as e:
                self.log_message(f"ERROR: Portable ffmpeg at {FFMPEG_EXECUTABLE_PATH} failed: {e}", "error", is_error=True)
        else:
            self.log_message(f"ERROR: Portable ffmpeg.exe not found: {FFMPEG_EXECUTABLE_PATH}", "error", is_error=True)

        if os.path.isfile(FFPROBE_EXECUTABLE_PATH):
            try:
                subprocess.run([FFPROBE_EXECUTABLE_PATH, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
                self.log_message(f"INFO: Portable ffprobe found: {FFPROBE_EXECUTABLE_PATH}", "info")
                self.ffprobe_ready = True
            except Exception as e:
                self.log_message(f"ERROR: Portable ffprobe at {FFPROBE_EXECUTABLE_PATH} failed: {e}", "error", is_error=True)
        else:
            self.log_message(f"ERROR: Portable ffprobe.exe not found: {FFPROBE_EXECUTABLE_PATH}", "error", is_error=True)

        if not (self.ffmpeg_ready and self.ffprobe_ready):
            self.start_button.config(state=tk.DISABLED)
            self.log_message("CRITICAL: FFmpeg/ffprobe not ready. Encoding & Estimation disabled.", "error", is_error=True)
            if self.master.winfo_exists(): # Check if GUI is up before showing messagebox
                messagebox.showerror("FFmpeg/ffprobe Critical Error", f"FFmpeg/ffprobe not found or not working. Please ensure they are in '{os.path.join(FFMPEG_BINARY_SUBDIR, 'bin')}' and are functional.")
        else:
            self.start_button.config(state=tk.NORMAL)
        self.update_estimated_size() 

    def log_message(self, message, tag_name=None, is_error=False):
        if not hasattr(self, 'log_text_lock'):
            self.log_text_lock = threading.Lock()
        self.log_entries_for_file.append(message)
        if is_error:
            self.has_errors_in_batch = True
        def _log():
            with self.log_text_lock:
                self.log_text.config(state=tk.NORMAL)
                if tag_name:
                    self.log_text.insert(tk.END, message + "\n", tag_name)
                else:
                    self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        if self.master.winfo_exists():
             self.master.after(0, _log)

    def _add_videos_to_map(self, video_paths):
        new_files_added = 0
        for video_path in video_paths:
            if video_path not in self.selected_files_map:
                base, _ = os.path.splitext(video_path)
                srt_path = base + ".srt"
                if os.path.exists(srt_path):
                    self.selected_files_map[video_path] = srt_path
                    self.log_message(f"Found: {os.path.basename(video_path)} with SRT: {os.path.basename(srt_path)}", "success")
                else:
                    self.selected_files_map[video_path] = None
                    self.log_message(f"Found: {os.path.basename(video_path)} - MISSING SRT ({os.path.basename(srt_path)})", "warning")
                new_files_added +=1
        if new_files_added > 0:
            self.update_file_listbox()

    def select_video_files(self):
        files = filedialog.askopenfilenames(title="Select Video File(s)", filetypes=[("Video Files", " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)), ("All Files", "*.*")])
        if files: self._add_videos_to_map(list(files))

    def select_video_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing Videos (Recursive)")
        if folder:
            found_videos = get_video_files_from_paths([folder])
            self._add_videos_to_map(found_videos)
            if not found_videos: self.log_message(f"No videos found in {folder} or subdirectories.", "warning")

    def clear_file_list(self):
        self.selected_files_map.clear()
        self.file_list_paths_ordered.clear()
        self.selected_video_path_for_estimation = None
        self.selected_video_duration_sec = 0.0
        self.update_file_listbox()
        self.update_estimated_size()
        self.log_message("File list cleared.", "info")

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        self.file_list_paths_ordered.clear()
        current_selection = None
        if self.selected_video_path_for_estimation in self.selected_files_map:
             current_selection = self.selected_video_path_for_estimation

        idx_to_select = -1
        current_idx = 0

        for video_path, srt_path in self.selected_files_map.items():
            self.file_list_paths_ordered.append(video_path) 
            srt_status = "SRT OK" if srt_path else "SRT MISSING"
            display_text = f"{os.path.basename(video_path)}  --  [{srt_status}]"
            self.file_listbox.insert(tk.END, display_text)
            self.file_listbox.itemconfig(tk.END, {'fg': LIGHT_BLUE_THEME["listbox_srt_ok_fg"] if srt_path else LIGHT_BLUE_THEME["listbox_srt_missing_fg"]})
            if video_path == current_selection:
                idx_to_select = current_idx
            current_idx += 1
        
        if idx_to_select != -1:
            self.file_listbox.selection_set(idx_to_select)
            self.file_listbox.activate(idx_to_select)
            self.file_listbox.see(idx_to_select)
        elif self.file_listbox.size() > 0: # If previous selection gone, select first if list not empty
            self.file_listbox.selection_set(0)
            self.on_file_list_select() # Trigger update based on new first selection
        else: # List is empty
             self.on_file_list_select() # Trigger update (will clear estimation)


    def on_file_list_select(self, event=None):
        if not self.file_listbox.curselection():
            self.selected_video_path_for_estimation = None
            self.selected_video_duration_sec = 0.0
            self.update_estimated_size()
            return

        selected_index = self.file_listbox.curselection()[0]
        if 0 <= selected_index < len(self.file_list_paths_ordered):
            new_selected_path = self.file_list_paths_ordered[selected_index]
            if new_selected_path != self.selected_video_path_for_estimation: # Only probe if selection changed
                self.selected_video_path_for_estimation = new_selected_path
                self._fetch_selected_video_duration() # This updates self.selected_video_duration_sec
        else:
            self.selected_video_path_for_estimation = None
            self.selected_video_duration_sec = 0.0
        self.update_estimated_size()

    def _fetch_selected_video_duration(self):
        self.selected_video_duration_sec = 0.0 
        if self.selected_video_path_for_estimation and self.ffprobe_ready:
            try:
                probe_opts = {'cmd': FFPROBE_EXECUTABLE_PATH}
                probe_data = ffmpeg.probe(self.selected_video_path_for_estimation, **probe_opts)
                duration_str = probe_data.get('format', {}).get('duration')
                if duration_str:
                    self.selected_video_duration_sec = float(duration_str)
                    self.log_message(f"Probed duration for {os.path.basename(self.selected_video_path_for_estimation)}: {self.selected_video_duration_sec:.2f}s", "info")
                else:
                    self.log_message(f"Could not probe duration for {os.path.basename(self.selected_video_path_for_estimation)}.", "warning")
            except Exception as e:
                self.log_message(f"Error probing video duration for {os.path.basename(self.selected_video_path_for_estimation)}: {e}", "error", is_error=True)
        elif not self.ffprobe_ready and self.selected_video_path_for_estimation:
            self.log_message("ffprobe not ready, cannot get video duration for estimation.", "warning")

    def _slider_changed(self, event=None):
        self._update_bitrate_display_labels()
        self.update_estimated_size()

    def update_estimated_size(self):
        if self.selected_video_path_for_estimation and self.selected_video_duration_sec > 0 and self.ffprobe_ready:
            v_bitrate_kbps = self.video_bitrate_var.get()
            a_bitrate_kbps = self.audio_bitrate_var.get()
            total_bitrate_kbps = v_bitrate_kbps + a_bitrate_kbps
            estimated_size_bytes = (total_bitrate_kbps * 1000 / 8) * self.selected_video_duration_sec 
            estimated_size_mb = estimated_size_bytes / (1024 * 1024)
            self.estimated_size_str.set(f"Estimated Size: {estimated_size_mb:.2f} MB (for selected video)")
        elif not self.ffprobe_ready and self.selected_video_path_for_estimation:
             self.estimated_size_str.set("Estimated Size: N/A MB (ffprobe not ready)")
        elif not self.selected_video_path_for_estimation:
            self.estimated_size_str.set("Estimated Size: N/A MB (No video selected)")
        else: 
            self.estimated_size_str.set("Estimated Size: N/A MB (Could not get duration)")

    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir.set(directory)
            self.log_message(f"Output directory set: {directory}", "info")

    def start_encoding_thread(self):
        if self.is_processing:
            self.log_message("Processing is already in progress.", "warning")
            return
        if not self.ffmpeg_ready : 
            self.log_message("FFmpeg not ready. Cannot start encoding.", "error", is_error=True)
            messagebox.showerror("FFmpeg Error", "Portable FFmpeg not configured correctly. Please check setup and logs.")
            return

        files_to_encode = {vp: sp for vp, sp in self.selected_files_map.items() if sp is not None}
        if not files_to_encode:
            self.log_message("No videos with corresponding SRT files selected for encoding.", "warning")
            messagebox.showerror("No Files", "Please select video files that have associated .srt subtitle files.")
            return

        output_path_str = self.output_dir.get()
        if not os.path.isdir(output_path_str):
            self.log_message(f"Output directory '{output_path_str}' is invalid or does not exist.", "error", is_error=True)
            messagebox.showerror("Invalid Output Path", f"The specified output directory '{output_path_str}' does not exist. Please select a valid directory.")
            return
        
        self.is_processing = True
        self.start_button.config(state=tk.DISABLED)
        self.log_entries_for_file.clear()
        self.has_errors_in_batch = False
        
        num_files_to_encode = len(files_to_encode)
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = num_files_to_encode
        self.update_progress_display(0, num_files_to_encode)
        
        user_video_bitrate = self.video_bitrate_var.get()
        user_audio_bitrate = self.audio_bitrate_var.get()

        thread = threading.Thread(target=self.process_videos_sequentially,
                                  args=(files_to_encode, output_path_str, user_video_bitrate, user_audio_bitrate),
                                  daemon=True)
        thread.start()

    def process_videos_sequentially(self, files_to_encode, output_path_str, video_bitrate, audio_bitrate):
        self.log_message(f"Starting encoding for {len(files_to_encode)} files with V:{video_bitrate}k|A:{audio_bitrate}k...", "info")
        
        completed_count = 0
        success_count = 0
        error_count = 0
        skipped_count = 0
        total_files_to_process = len(files_to_encode)

        for video_path, srt_path in files_to_encode.items():
            self.log_message(f"Processing: {os.path.basename(video_path)}...", "info")
            try:
                _, status, message = encode_single_video(
                    video_path, srt_path, output_path_str,
                    FFMPEG_EXECUTABLE_PATH, FFPROBE_EXECUTABLE_PATH,
                    video_bitrate, audio_bitrate
                )
                log_tag = "info"; is_item_error = False
                if status == "success": success_count += 1; log_tag = "success"
                elif status == "error": error_count += 1; log_tag = "error"; is_item_error = True
                elif status == "skipped": skipped_count +=1; log_tag = "warning"
                self.log_message(f"[{status.upper()}] {os.path.basename(video_path)}: {message}", log_tag, is_error=is_item_error)
            except Exception as exc:
                self.log_message(f"[FATAL ERROR] {os.path.basename(video_path)}: Encoding task failed - {exc}", "error", is_error=True)
                error_count += 1
            
            completed_count += 1
            self.master.after(0, self.update_progress_display, completed_count, total_files_to_process)
        self.master.after(0, self.finalize_processing, success_count, error_count, skipped_count)

    def update_progress_display(self, current_value, max_value):
        if self.master.winfo_exists():
            self.progress_bar['value'] = current_value
            percentage = int((current_value / max_value) * 100) if max_value > 0 else 0
            self.progress_label.config(text=f"{percentage}%")

    def finalize_processing(self, success_count, error_count, skipped_count):
        if not self.master.winfo_exists(): return
        self.is_processing = False
        self.start_button.config(state=tk.NORMAL)
        summary_message = f"--- Encoding Finished ---\nSuccessfully encoded: {success_count}\nErrors: {error_count}\nSkipped: {skipped_count}"
        self.log_message("--- Encoding Finished ---", "info")
        self.log_message(f"Successfully encoded: {success_count}", "success")
        if error_count > 0: self.log_message(f"Errors: {error_count}", "error", is_error=True)
        if skipped_count > 0: self.log_message(f"Skipped (already exists): {skipped_count}", "warning")
        if self.has_errors_in_batch and error_count > 0: self.save_log_to_desktop()
        messagebox.showinfo("Processing Complete", f"Processing finished.\n\n{summary_message}\n\nCheck logs for details.")
        if self.force_shutdown_var.get(): self.initiate_shutdown()

    def save_log_to_desktop(self):
        try:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.isdir(desktop_path): desktop_path = os.path.expanduser("~") 
            log_file_path = os.path.join(desktop_path, "Video_Conversion_log.txt")
            with open(log_file_path, "w", encoding="utf-8") as f:
                for entry in self.log_entries_for_file: f.write(entry + "\n")
            self.log_message(f"Error log saved to: {log_file_path}", "success")
        except Exception as e:
            self.log_message(f"Failed to save error log to desktop: {e}", "error", is_error=True)

    def initiate_shutdown(self):
        self.log_message("INFO: Computer will attempt to shut down in 20 seconds.", "info")
        try:
            if os.name == 'nt': os.system("shutdown /s /f /t 20")
            elif os.name == 'posix':
                os.system("shutdown -h +\"20 seconds\"") 
                self.log_message("INFO: On Linux/macOS, shutdown may require sudo privileges.", "warning")
            else:
                self.log_message("WARNING: Shutdown command not implemented for this OS.", "warning")
        except Exception as e:
             self.log_message(f"ERROR: Failed to initiate shutdown: {e}", "error", is_error=True)

if __name__ == "__main__":
    if os.name == 'nt':
        from ctypes import windll
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception: 
            pass
    root = tk.Tk()
    app = HardcodeApp(root)
    root.mainloop()
