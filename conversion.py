import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import os
import subprocess
import threading
import ffmpeg
import queue
import math
import re
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_BINARY_SUBDIR = "ffmpeg_binary"
FFMPEG_BIN_DIR = os.path.join(SCRIPT_DIR, FFMPEG_BINARY_SUBDIR, "bin")
FFMPEG_EXECUTABLE_PATH = os.path.join(FFMPEG_BIN_DIR, "ffmpeg.exe")
FFPROBE_EXECUTABLE_PATH = os.path.join(FFMPEG_BIN_DIR, "ffprobe.exe")

VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.ts', '.mpg', '.mpeg')
DEFAULT_AUDIO_BITRATE = '128k'
MIN_VIDEO_BITRATE_STR = '500k'
FFMPEG_PRESET = 'medium'

def parse_bitrate_to_int(bitrate_str):
    if not isinstance(bitrate_str, str):
        return int(bitrate_str)
    val_str = bitrate_str.lower()
    multiplier = 1
    if val_str.endswith('k'):
        multiplier = 1000
        val_str = val_str[:-1]
    elif val_str.endswith('m'):
        multiplier = 1000000
        val_str = val_str[:-1]
    try:
        return int(float(val_str) * multiplier)
    except ValueError:
        return 0

def format_bitrate_from_int(bitrate_int):
    if bitrate_int >= 1000000:
        return str(int(round(bitrate_int / 1000000))) + 'M'
    elif bitrate_int >= 1000:
        return str(int(round(bitrate_int / 1000))) + 'k'
    return str(int(bitrate_int))

def escape_srt_path_for_ffmpeg_filter(srt_path):
    path = srt_path.replace('\\', '/')
    if os.name == 'nt':
        if len(path) > 1 and path[1] == ':' and path[0].isalpha():
            path = path[0] + '\\:' + path[2:]
    return path

def parse_ffmpeg_time_to_seconds(time_str):
    if not time_str:
        return 0.0
    parts = time_str.split(':')
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_component = float(parts[2])
        total_seconds = (hours * 3600) + (minutes * 60) + seconds_component
        return total_seconds
    except (IndexError, ValueError):
        print(f"Warning: Could not parse time string '{time_str}'")
        return 0.0

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

class HardcodeApp:
    def __init__(self, master):
        self.master = master
        master.title("Advanced Video Converter (Portable FFmpeg) v1.04")
        master.geometry("900x800")

        self.selected_files_map = {}
        self.output_dir = tk.StringVar(value="D:\\")
        self.is_processing = False
        self.ffmpeg_ready = False
        self.ffprobe_ready = False
        self.current_ffmpeg_process = None
        self.log_text_lock = threading.Lock()

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.is_paused = False

        self.output_formats = {
            "MP4": ".mp4", "MKV": ".mkv", "MOV": ".mov", "WEBM": ".webm"
        }
        self.output_format_var = tk.StringVar(value="MP4")
        self.target_size_gb_var = tk.StringVar(value="")
        
        self.current_video_progress_label_var = tk.StringVar(value="0.0%")
        self.overall_progress_label_var = tk.StringVar(value="0.0%")

        self.total_duration_all_files = 0.0
        self.processed_duration_all_files = 0.0


        self.setup_styles()
        self.setup_ui()
        self.check_portable_ffmpeg_ffprobe()

    def setup_styles(self):
        self.style = ttk.Style()
        available_themes = self.style.theme_names()
        
        if 'clam' in available_themes: self.style.theme_use('clam')
        elif 'vista' in available_themes and os.name == 'nt': self.style.theme_use('vista')
        elif 'aqua' in available_themes and os.name == 'posix': self.style.theme_use('aqua')
        else: self.style.theme_use('default')

        self.base_font_size = 10
        self.base_font_family = 'Segoe UI' if os.name == 'nt' else 'Helvetica'

        self.style.configure('.', font=(self.base_font_family, self.base_font_size))
        self.style.configure('TFrame', background='#ECECEC')
        self.master.configure(background='#ECECEC')
        self.style.configure('TLabel', background='#ECECEC', padding=(5, 3))
        self.style.configure('TLabelframe', background='#ECECEC', padding=10)
        self.style.configure('TLabelframe.Label', font=(self.base_font_family, self.base_font_size + 1, 'bold'), background='#ECECEC', foreground='#003366')
        self.style.configure('TButton', font=(self.base_font_family, self.base_font_size), padding=(10, 5))
        self.style.configure('Small.TButton', font=(self.base_font_family, self.base_font_size-1), padding=(6,3))
        self.style.configure('TEntry', font=(self.base_font_family, self.base_font_size), padding=(5,4))
        self.style.configure('TCombobox', font=(self.base_font_family, self.base_font_size), padding=(5,4))
        self.style.map('TCombobox', fieldbackground=[('readonly', 'white')], selectbackground=[('readonly', 'white')], selectforeground=[('readonly', 'black')])
        self.style.configure('Accent.TButton', font=(self.base_font_family, self.base_font_size, 'bold'))
        accent_bg_color = '#0078D4'; accent_fg_color = 'white'
        try:
            self.style.map('Accent.TButton', background=[('active', '#005a9e'),('!disabled', accent_bg_color)], foreground=[('!disabled', accent_fg_color)])
        except tk.TclError:
            print("Note: Accent.TButton style theming might be limited by the current theme.")
            self.style.configure('Accent.TButton', background=accent_bg_color, foreground=accent_fg_color)
        self.log_color_tags = {"green": "log_green", "red": "log_red", "orange": "log_orange", "blue": "log_blue", "purple": "log_purple", "gray": "log_gray", "ffmpeg_output": "ffmpeg_output"} # Removed progress_update here

    def setup_ui(self):
        main_content_frame = ttk.Frame(self.master, padding="15 15 15 15"); main_content_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = ttk.LabelFrame(main_content_frame, text="1. Select Input Files"); input_frame.pack(padx=0, pady=(0,10), fill=tk.X)
        input_buttons_frame = ttk.Frame(input_frame); input_buttons_frame.pack(padx=5, pady=5, fill=tk.X)
        btn_select_files = ttk.Button(input_buttons_frame, text="Select Video File(s)", command=self.select_video_files); btn_select_files.pack(side=tk.LEFT, padx=(0,5), pady=5)
        btn_select_folder = ttk.Button(input_buttons_frame, text="Select Video Folder", command=self.select_video_folder); btn_select_folder.pack(side=tk.LEFT, padx=5, pady=5)
        btn_clear_list = ttk.Button(input_buttons_frame, text="Clear List", command=self.clear_file_list); btn_clear_list.pack(side=tk.RIGHT, padx=(5,0), pady=5)
        list_frame = ttk.LabelFrame(main_content_frame, text="2. Files to Process"); list_frame.pack(padx=0, pady=5, fill=tk.BOTH, expand=True)
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, font=(self.base_font_family, self.base_font_size), bg="white", fg="#333333", selectbackground="#0078d4", selectforeground="white", relief=tk.FLAT, borderwidth=0, highlightthickness=1, highlightbackground="#cccccc")
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1) 
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview); scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0,1), pady=1)
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        output_settings_frame = ttk.LabelFrame(main_content_frame, text="3. Output Configuration"); output_settings_frame.pack(padx=0, pady=10, fill=tk.X)
        output_settings_frame.columnconfigure(1, weight=1) 
        ttk.Label(output_settings_frame, text="Output Directory:").grid(row=0, column=0, padx=5, pady=(5,3), sticky=tk.W)
        self.output_dir_entry = ttk.Entry(output_settings_frame, textvariable=self.output_dir); self.output_dir_entry.grid(row=0, column=1, padx=5, pady=(5,3), sticky=tk.EW)
        btn_browse_output = ttk.Button(output_settings_frame, text="Browse...", command=self.select_output_dir, style='Small.TButton'); btn_browse_output.grid(row=0, column=2, padx=5, pady=(5,3), sticky=tk.E)
        format_size_subframe = ttk.Frame(output_settings_frame); format_size_subframe.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=(3,5))
        ttk.Label(format_size_subframe, text="Output Format:").pack(side=tk.LEFT, padx=(5,2))
        self.output_format_menu = ttk.Combobox(format_size_subframe, textvariable=self.output_format_var, values=list(self.output_formats.keys()), state="readonly", width=7); self.output_format_menu.pack(side=tk.LEFT, padx=(0,20)) 
        ttk.Label(format_size_subframe, text="Target Size (GB, optional):").pack(side=tk.LEFT, padx=(0,2))
        self.target_size_entry = ttk.Entry(format_size_subframe, textvariable=self.target_size_gb_var, width=10); self.target_size_entry.pack(side=tk.LEFT, padx=0)
        control_frame_outer = ttk.LabelFrame(main_content_frame, text="4. Execution & Progress"); control_frame_outer.pack(padx=0, pady=5, fill=tk.X)
        buttons_frame = ttk.Frame(control_frame_outer, padding=(5,5)); buttons_frame.pack(fill=tk.X, expand=True)
        self.start_button = ttk.Button(buttons_frame, text="Start Encoding", command=self.start_encoding_thread, style='Accent.TButton'); self.start_button.pack(side=tk.LEFT, padx=(0,5))
        self.pause_resume_button = ttk.Button(buttons_frame, text="Pause", command=self.toggle_pause_resume, state=tk.DISABLED); self.pause_resume_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(buttons_frame, text="Stop", command=self.stop_processing_command, state=tk.DISABLED); self.stop_button.pack(side=tk.LEFT, padx=5)
        current_video_progress_frame = ttk.Frame(control_frame_outer, padding=(5,2)); current_video_progress_frame.pack(fill=tk.X, expand=True, pady=(3,0))
        ttk.Label(current_video_progress_frame, text="Current Video:", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=(0,5))
        self.current_video_progress_bar = ttk.Progressbar(current_video_progress_frame, orient="horizontal", length=200, mode="determinate", maximum=100); self.current_video_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        current_video_text_label = ttk.Label(current_video_progress_frame, textvariable=self.current_video_progress_label_var, width=7, anchor=tk.E); current_video_text_label.pack(side=tk.LEFT, padx=(5,0))
        overall_progress_frame = ttk.Frame(control_frame_outer, padding=(5,2)); overall_progress_frame.pack(fill=tk.X, expand=True, pady=(0,3))
        ttk.Label(overall_progress_frame, text="Overall Progress:", width=15, anchor=tk.W).pack(side=tk.LEFT, padx=(0,5))
        self.overall_progress_bar = ttk.Progressbar(overall_progress_frame, orient="horizontal", length=200, mode="determinate", maximum=100); self.overall_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        overall_text_label = ttk.Label(overall_progress_frame, textvariable=self.overall_progress_label_var, width=7, anchor=tk.E); overall_text_label.pack(side=tk.LEFT, padx=(5,0))
        log_frame = ttk.LabelFrame(main_content_frame, text="Process Log"); log_frame.pack(padx=0, pady=(10,0), fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, font=('Consolas', self.base_font_size -1), relief=tk.FLAT, borderwidth=0, highlightthickness=1, highlightbackground="#cccccc", bg="white", fg="#333333", padx=5, pady=5)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.log_text.tag_configure(self.log_color_tags["ffmpeg_output"], foreground="#777777")
        self.log_text.tag_configure(self.log_color_tags["green"], foreground="#008000")
        self.log_text.tag_configure(self.log_color_tags["red"], foreground="#CC0000")
        self.log_text.tag_configure(self.log_color_tags["orange"], foreground="#FF8C00")
        self.log_text.tag_configure(self.log_color_tags["blue"], foreground="#0033CC")
        self.log_text.tag_configure(self.log_color_tags["purple"], foreground="#800080")
        self.log_text.tag_configure(self.log_color_tags["gray"], foreground="#505050")

    def check_portable_ffmpeg_ffprobe(self):
        self.ffmpeg_ready = False; self.ffprobe_ready = False
        current_creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        if os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            try:
                subprocess.run([FFMPEG_EXECUTABLE_PATH, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=current_creationflags)
                self.log_message(f"INFO: Portable ffmpeg found: {FFMPEG_EXECUTABLE_PATH}", "green"); self.ffmpeg_ready = True
            except Exception as e: self.log_message(f"ERROR: Portable ffmpeg at {FFMPEG_EXECUTABLE_PATH} failed: {e}", "red")
        else: self.log_message(f"ERROR: Portable ffmpeg.exe not found: {FFMPEG_EXECUTABLE_PATH}", "red")
        if os.path.isfile(FFPROBE_EXECUTABLE_PATH):
            try:
                subprocess.run([FFPROBE_EXECUTABLE_PATH, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=current_creationflags)
                self.log_message(f"INFO: Portable ffprobe found: {FFPROBE_EXECUTABLE_PATH}", "green"); self.ffprobe_ready = True
            except Exception as e: self.log_message(f"ERROR: Portable ffprobe at {FFPROBE_EXECUTABLE_PATH} failed: {e}", "red")
        else: self.log_message(f"ERROR: Portable ffprobe.exe not found: {FFPROBE_EXECUTABLE_PATH}", "red")
        if not (self.ffmpeg_ready and self.ffprobe_ready):
            if hasattr(self, 'start_button'): self.start_button.config(state=tk.DISABLED)
            self.log_message("CRITICAL: FFmpeg/ffprobe not ready. Encoding disabled.", "red")
            messagebox.showerror("FFmpeg/ffprobe Error", "Portable FFmpeg/ffprobe not found or failed. Check paths and executables in the 'ffmpeg_binary/bin' subfolder. Encoding is disabled.")
        else:
            if hasattr(self, 'start_button'): self.start_button.config(state=tk.NORMAL)

    def log_message(self, message, color=None, tag=None):
        def _log():
            with self.log_text_lock:
                self.log_text.config(state=tk.NORMAL)
                final_tag_name = tag if tag else self.log_color_tags.get(color.lower()) if color else None
                if not final_tag_name and color:
                    try: self.log_text.tag_configure(color, foreground=color); final_tag_name = color
                    except tk.TclError: pass
                self.log_text.insert(tk.END, message + "\n", final_tag_name) if final_tag_name else self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END); self.log_text.config(state=tk.DISABLED)
        if hasattr(self, 'master') and self.master.winfo_exists(): self.master.after(0, _log)
        else: print(f"LOG ({color or 'default'}): {message}")
    
    def log_ffmpeg_output(self, line): self.log_message(line, tag=self.log_color_tags["ffmpeg_output"])

    def _add_videos_to_map(self, video_paths):
        new_files_added = 0
        for video_path in video_paths:
            if video_path not in self.selected_files_map:
                base, _ = os.path.splitext(video_path)
                srt_path = base + ".srt"
                if os.path.exists(srt_path): self.selected_files_map[video_path] = srt_path; self.log_message(f"Found: {os.path.basename(video_path)} with SRT: {os.path.basename(srt_path)}", "green")
                else: self.selected_files_map[video_path] = None; self.log_message(f"Found: {os.path.basename(video_path)} - No corresponding SRT found.", "orange")
                new_files_added +=1
        if new_files_added > 0: self.update_file_listbox()

    def select_video_files(self):
        files = filedialog.askopenfilenames(title="Select Video File(s)", filetypes=[("Video Files", " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)), ("All Files", "*.*")])
        if files: self._add_videos_to_map(list(files))

    def select_video_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing Videos (Recursive)")
        if folder:
            found_videos = get_video_files_from_paths([folder])
            if found_videos: self._add_videos_to_map(found_videos)
            else: self.log_message(f"No videos found in {folder} or subdirectories.", "orange")

    def clear_file_list(self): self.selected_files_map.clear(); self.update_file_listbox(); self.log_message("File list cleared.")

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for video_path, srt_path in self.selected_files_map.items():
            display_text = f"{os.path.basename(video_path)}  --  [{'SRT Found' if srt_path else 'No SRT'}]"
            self.file_listbox.insert(tk.END, display_text); self.file_listbox.itemconfig(tk.END, {'fg': "#006400" if srt_path else "#CC5500"})

    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory: self.output_dir.set(directory); self.log_message(f"Output directory set: {directory}")

    def update_current_video_progress(self, value, text_value=""):
        if self.master.winfo_exists() and hasattr(self, 'current_video_progress_bar'):
            self.current_video_progress_bar['value'] = value
            self.current_video_progress_label_var.set(text_value if text_value else f"{value:.1f}%")

    def update_overall_progress(self, processed_duration, total_duration):
        if self.master.winfo_exists() and hasattr(self, 'overall_progress_bar'):
            if total_duration > 0:
                percentage = min(100.0, (processed_duration / total_duration) * 100)
                self.overall_progress_bar['value'] = percentage
                self.overall_progress_label_var.set(f"{percentage:.1f}%")
            else:
                self.overall_progress_bar['value'] = 0
                self.overall_progress_label_var.set("0.0%")

    def get_video_duration(self, video_path):
        try:
            probe_data = ffmpeg.probe(video_path, cmd=FFPROBE_EXECUTABLE_PATH)
            duration_str = probe_data.get('format', {}).get('duration')
            if duration_str: return float(duration_str)
        except Exception as e: self.log_message(f"Error probing duration for {os.path.basename(video_path)}: {e}", "red")
        return 0.0

    def precalculate_total_duration(self, files_to_encode):
        self.total_duration_all_files = 0.0
        self.log_message("Calculating total video duration for overall progress...", "blue")
        for video_path in files_to_encode.keys():
            duration = self.get_video_duration(video_path)
            self.total_duration_all_files += duration
            if self.stop_event.is_set(): # Allow stopping during pre-calculation
                self.log_message("Pre-calculation stopped by user.", "orange")
                return False
        self.log_message(f"Total estimated duration for all files: {self.total_duration_all_files:.2f} seconds.", "blue")
        return True


    def encode_single_video(self, video_path, srt_path, output_dir, output_extension, target_size_gb_str):
        base, _ = os.path.splitext(os.path.basename(video_path))
        suffix = "_hardsub" if srt_path else "_converted"
        output_filename = f"{base}{suffix}{output_extension}"
        output_path = os.path.join(output_dir, output_filename)
        if self.master.winfo_exists(): self.master.after(0, self.update_current_video_progress, 0, "0.0%")
        if os.path.exists(output_path): return video_path, "skipped", f"Output file already exists: {output_path}"

        try:
            probe_opts = {'cmd': FFPROBE_EXECUTABLE_PATH}
            probe_data = ffmpeg.probe(video_path, **probe_opts)
            format_info = probe_data.get('format', {}); video_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video']; audio_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio']
            current_video_bitrate_str = MIN_VIDEO_BITRATE_STR
            if format_info.get('bit_rate'): current_video_bitrate_str = format_info['bit_rate']
            elif video_streams and video_streams[0].get('bit_rate'): current_video_bitrate_str = video_streams[0]['bit_rate']
            current_video_bitrate_int = parse_bitrate_to_int(current_video_bitrate_str); min_video_bitrate_int = parse_bitrate_to_int(MIN_VIDEO_BITRATE_STR)
            if current_video_bitrate_int == 0: self.log_message(f"Warning ({base}): Could not determine source video bitrate, using minimum: {MIN_VIDEO_BITRATE_STR}.", "orange"); target_v_bitrate_str = MIN_VIDEO_BITRATE_STR
            elif current_video_bitrate_int < min_video_bitrate_int: target_v_bitrate_str = MIN_VIDEO_BITRATE_STR; self.log_message(f"Info ({base}): Source video bitrate ({format_bitrate_from_int(current_video_bitrate_int)}) is lower than minimum, using minimum: {MIN_VIDEO_BITRATE_STR}.", "blue")
            else: target_v_bitrate_str = format_bitrate_from_int(current_video_bitrate_int)
            target_a_bitrate_str = DEFAULT_AUDIO_BITRATE
            if audio_streams and audio_streams[0].get('bit_rate'):
                probed_ab_int = parse_bitrate_to_int(audio_streams[0]['bit_rate'])
                if probed_ab_int > 0: target_a_bitrate_str = format_bitrate_from_int(probed_ab_int)
            duration_str = format_info.get('duration'); total_duration_s = 0.0 
            if duration_str:
                try: total_duration_s = float(duration_str)
                except ValueError: self.log_message(f"Warning ({base}): Could not parse duration '{duration_str}' for progress.", "orange")
            if target_size_gb_str and duration_str and total_duration_s > 0: 
                try:
                    target_size_gb = float(target_size_gb_str)
                    if target_size_gb > 0: 
                        target_filesize_bytes = target_size_gb * 1024 * 1024 * 1024; required_total_bitrate_bps = (target_filesize_bytes * 8) / total_duration_s
                        audio_bitrate_bps = parse_bitrate_to_int(target_a_bitrate_str); audio_bitrate_bps = audio_bitrate_bps if audio_bitrate_bps > 0 else parse_bitrate_to_int(DEFAULT_AUDIO_BITRATE)
                        calculated_video_bitrate_bps = required_total_bitrate_bps - audio_bitrate_bps
                        if calculated_video_bitrate_bps < min_video_bitrate_int: self.log_message(f"Warning for {base}: Target size is too small for min video quality. Using min video bitrate {MIN_VIDEO_BITRATE_STR}. Output may be larger.", "orange"); target_v_bitrate_str = MIN_VIDEO_BITRATE_STR
                        else: target_v_bitrate_str = format_bitrate_from_int(calculated_video_bitrate_bps); self.log_message(f"Info for {base}: Calculated target video bitrate: {target_v_bitrate_str} for size {target_size_gb}GB", "blue")
                    else: self.log_message(f"Warning for {base}: Invalid target size '{target_size_gb_str}'. Using default bitrate logic.", "orange")
                except ValueError: self.log_message(f"Warning for {base}: Invalid target size '{target_size_gb_str}'. Using default bitrate logic.", "orange")
            elif target_size_gb_str and (not duration_str or total_duration_s <=0): self.log_message(f"Warning for {base}: Could not get valid duration. Target size ignored.", "orange")
            stream = ffmpeg.input(video_path)
            output_params = {'vcodec': 'libx264', 'acodec': 'aac', 'preset': FFMPEG_PRESET, 'b:v': target_v_bitrate_str, 'b:a': target_a_bitrate_str, 'strict': '-2'}
            if srt_path: output_params['vf'] = f"subtitles=filename='{escape_srt_path_for_ffmpeg_filter(srt_path)}'"
            stream = ffmpeg.output(stream, output_path, **output_params); args = stream.compile(cmd=FFMPEG_EXECUTABLE_PATH, overwrite_output=True)
            current_process_creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            self.current_ffmpeg_process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=current_process_creationflags, universal_newlines=True, errors='ignore')
            log_queue = queue.Queue()
            def pipe_reader_thread(pipe, pipe_name):
                try:
                    with pipe:
                        for line in iter(pipe.readline, ''): log_queue.put((pipe_name, line.strip()))
                finally: log_queue.put((pipe_name, None))
            stdout_thread = threading.Thread(target=pipe_reader_thread, args=[self.current_ffmpeg_process.stdout, "stdout"]); stderr_thread = threading.Thread(target=pipe_reader_thread, args=[self.current_ffmpeg_process.stderr, "stderr"])
            stdout_thread.start(); stderr_thread.start()
            ffmpeg_stderr_output = []; time_regex = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")
            if total_duration_s <= 0: self.log_message(f"Warning ({base}): Progress percentage unavailable due to invalid/missing duration.", "orange")
            last_overall_update_time_s = 0

            while stdout_thread.is_alive() or stderr_thread.is_alive():
                try:
                    pipe_name, line = log_queue.get(timeout=0.1)
                    if line is None: 
                        if pipe_name == "stdout": stdout_thread.join(timeout=0.1)
                        elif pipe_name == "stderr": stderr_thread.join(timeout=0.1)
                        continue
                    self.log_ffmpeg_output(line)
                    if pipe_name == "stderr":
                        ffmpeg_stderr_output.append(line)
                        if total_duration_s > 0: 
                            match = time_regex.search(line)
                            if match:
                                current_time_str = match.group(1); current_time_s = parse_ffmpeg_time_to_seconds(current_time_str)
                                if current_time_s > 0:
                                    percentage = min(100.0, (current_time_s / total_duration_s) * 100)
                                    if self.master.winfo_exists(): self.master.after(0, self.update_current_video_progress, percentage)
                                    
                                    # Update overall progress based on this file's contribution
                                    time_delta_for_overall = current_time_s - last_overall_update_time_s
                                    if time_delta_for_overall > 0 : # only update if time has advanced
                                        self.processed_duration_all_files += time_delta_for_overall
                                        last_overall_update_time_s = current_time_s
                                        if self.master.winfo_exists():
                                            self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)
                except queue.Empty:
                    if self.current_ffmpeg_process.poll() is not None: break 
            stdout_thread.join(timeout=1); stderr_thread.join(timeout=1)
            return_code = self.current_ffmpeg_process.wait(); self.current_ffmpeg_process = None
            
            # Final update for overall progress based on this file's actual processed duration
            if total_duration_s > 0 and last_overall_update_time_s < total_duration_s : # if it didn't reach 100%
                time_delta_for_overall = total_duration_s - last_overall_update_time_s
                self.processed_duration_all_files += time_delta_for_overall
                if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)


            if return_code == 0:
                if total_duration_s > 0 and self.master.winfo_exists(): self.master.after(0, self.update_current_video_progress, 100, "100.0%")
                return video_path, "success", f"Successfully encoded: {output_path}"
            else:
                if self.stop_event.is_set(): return video_path, "stopped", f"Encoding stopped by user for: {output_path} (ffmpeg exit code {return_code})"
                error_message = f"FFmpeg error for {os.path.basename(video_path)} (code {return_code}):\n" + "\n".join(ffmpeg_stderr_output[-15:])
                return video_path, "error", error_message
        except Exception as e:
            error_message = f"General error for {os.path.basename(video_path)}: {str(e)}"
            return video_path, "error", error_message
        finally: self.current_ffmpeg_process = None

    def start_encoding_thread(self):
        if self.is_processing: self.log_message("Processing already in progress.", "orange"); return
        if not (self.ffmpeg_ready and self.ffprobe_ready):
            self.log_message("FFmpeg/ffprobe not ready. Cannot start encoding.", "red")
            messagebox.showerror("FFmpeg/ffprobe Error", "Portable FFmpeg/ffprobe not configured. Check setup."); return
        files_to_encode = self.selected_files_map.copy()
        if not files_to_encode:
            self.log_message("No videos selected for processing.", "red")
            messagebox.showerror("No Files", "Please select video files to process."); return
        output_path_str = self.output_dir.get()
        if not os.path.isdir(output_path_str):
            self.log_message(f"Output directory '{output_path_str}' invalid.", "red")
            messagebox.showerror("Invalid Output Path", f"Output directory '{output_path_str}' does not exist."); return
        
        self.is_processing = True; self.stop_event.clear(); self.pause_event.clear(); self.is_paused = False
        self.start_button.config(state=tk.DISABLED); self.pause_resume_button.config(text="Pause", state=tk.NORMAL); self.stop_button.config(state=tk.NORMAL)
        self.update_current_video_progress(0, "0.0%"); self.update_overall_progress(0, 100) # Initial overall to 0% of 100
        self.processed_duration_all_files = 0.0 # Reset cumulative duration

        output_ext = self.output_formats[self.output_format_var.get()]; target_size_str = self.target_size_gb_var.get().strip()
        thread = threading.Thread(target=self.process_videos_sequentially, args=(files_to_encode, output_path_str, output_ext, target_size_str), daemon=True)
        thread.start()

    def process_videos_sequentially(self, files_to_encode, output_path_str, output_ext, target_size_str):
        if not self.precalculate_total_duration(files_to_encode):
            self.log_message("Failed to precalculate total duration or was stopped. Aborting encoding.", "red")
            if self.master.winfo_exists(): self.master.after(0, self.on_processing_finished)
            return

        if self.total_duration_all_files <= 0:
             self.log_message("Warning: Total duration of files is zero. Overall progress may not be accurate.", "orange")
             # Set overall progress bar maximum to number of files if duration is not available
             # self.overall_progress_bar['maximum'] = len(files_to_encode) # Fallback, but we're sticking to time-based for now

        self.log_message(f"Starting encoding for {len(files_to_encode)} files...", "blue")
        completed_count = 0; success_count = 0; error_count = 0; skipped_count = 0; stopped_for_file_count = 0

        for video_path, srt_path in files_to_encode.items():
            if self.pause_event.is_set():
                self.log_message("Processing paused. Click Resume to continue.", "blue")
                while self.pause_event.is_set(): 
                    if self.stop_event.is_set(): break
                    time.sleep(0.2) 
            if self.stop_event.is_set(): self.log_message("Stop signal received. Halting further processing.", "orange"); break 
            self.log_message(f"Processing: {os.path.basename(video_path)}...", "blue")
            
            # Before encoding, if a previous file was skipped or errored, its duration wasn't added to processed_duration_all_files by encode_single_video
            # So, we must add its full duration here to keep overall progress correct for skipped/errored files
            duration_of_current_file_for_overall = self.get_video_duration(video_path)

            try:
                _, status, message = self.encode_single_video(video_path, srt_path, output_path_str, output_ext, target_size_str)
                color_key = status
                if status == "error": error_count += 1
                elif status == "skipped": skipped_count += 1
                elif status == "stopped": stopped_for_file_count += 1
                elif status == "success": success_count += 1
                self.log_message(f"[{status.upper()}] {os.path.basename(video_path)}: {message}", color_key)
                
                if status in ["skipped", "error"] and duration_of_current_file_for_overall > 0:
                     # Add this file's full duration to processed since encode_single_video didn't run its time loop for these
                     self.processed_duration_all_files += duration_of_current_file_for_overall
                     if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)

                if status == "stopped": self.log_message("Halting further processing due to user stop during a file.", "orange"); self.stop_event.set(); break
            except Exception as exc:
                self.log_message(f"[FATAL ERROR] {os.path.basename(video_path)}: Encoding task failed unexpectedly - {exc}", "red"); error_count += 1
                if duration_of_current_file_for_overall > 0: # Also count for fatal error
                     self.processed_duration_all_files += duration_of_current_file_for_overall
                     if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)
            completed_count += 1
        
        self.log_message(f"--- Encoding Finished ---", "blue")
        self.log_message(f"Successfully encoded: {success_count}", "green")
        self.log_message(f"Errors: {error_count}", "red" if error_count > 0 else "gray")
        self.log_message(f"Skipped (already exists): {skipped_count}", "orange" if skipped_count > 0 else "gray")
        processed_files = success_count + error_count + skipped_count + stopped_for_file_count
        general_stopped_count = len(files_to_encode) - processed_files
        if stopped_for_file_count > 0: self.log_message(f"Stopped by user during processing: {stopped_for_file_count} file(s)", "purple")
        if general_stopped_count > 0 : self.log_message(f"Files not started due to stop: {general_stopped_count}", "purple")
        elif self.stop_event.is_set() and stopped_for_file_count == 0 and general_stopped_count == 0 : self.log_message(f"Processing was signaled to stop, but all tasks completed or handled.", "purple")
        if self.master.winfo_exists(): self.master.after(0, self.on_processing_finished)

    def on_processing_finished(self):
        if self.master.winfo_exists():
            self.is_processing = False
            self.start_button.config(state=tk.NORMAL); self.pause_resume_button.config(text="Pause", state=tk.DISABLED); self.stop_button.config(state=tk.DISABLED)
            self.current_ffmpeg_process = None; self.stop_event.clear(); self.pause_event.clear(); self.is_paused = False
            self.update_current_video_progress(0, "0.0%") 
            # Final overall progress update to ensure it's 100% if all went well, or reflects stoppage.
            if not self.stop_event.is_set() and self.total_duration_all_files > 0:
                self.update_overall_progress(self.total_duration_all_files, self.total_duration_all_files) # Should be 100%
            elif self.total_duration_all_files == 0: # If no duration, maybe set to 100% based on file count if all done.
                 self.update_overall_progress(100,100) if not self.stop_event.is_set() else None

            messagebox.showinfo("Processing Complete", "All selected videos have been processed. Check logs for details.")

    def toggle_pause_resume(self):
        if not self.is_processing: return
        if self.is_paused: self.pause_event.clear(); self.is_paused = False; self.pause_resume_button.config(text="Pause"); self.log_message("Resuming processing...", "blue")
        else: self.pause_event.set(); self.is_paused = True; self.pause_resume_button.config(text="Resume"); self.log_message("Pausing processing. Current file will complete if not stoppable.", "blue")
            
    def stop_processing_command(self):
        if not self.is_processing: return
        if messagebox.askyesno("Stop Processing", "Are you sure you want to stop? The current file (if any) will attempt a graceful shutdown. Further files will be skipped."):
            self.log_message("Stop command received. Attempting to stop gracefully...", "orange"); self.stop_event.set()
            if self.current_ffmpeg_process and self.current_ffmpeg_process.poll() is None:
                self.log_message("Sending 'q' to current FFmpeg process...", "orange")
                try: self.current_ffmpeg_process.stdin.write('q\n'); self.current_ffmpeg_process.stdin.flush()
                except (OSError, ValueError, BrokenPipeError, AttributeError) as e: self.log_message(f"Could not send 'q' to FFmpeg: {e}. FFmpeg might terminate abruptly.", "red")
            if self.is_paused: self.pause_event.clear(); self.is_paused = False
            self.stop_button.config(state=tk.DISABLED); self.pause_resume_button.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = HardcodeApp(root)
    root.mainloop()