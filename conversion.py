# conversion.py v1.1 - added mkv embedded srt selection and conversion. fixed encoding error if srt is not english

import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import os
import subprocess
import threading
import ffmpeg # type: ignore
import queue
import math
import re
import time
import traceback

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

def escape_path_for_ffmpeg_filter_filename(path_str):
    path = str(path_str)
    path = path.replace('\\', '/')
    return path

def parse_ffmpeg_time_to_seconds(time_str):
    if not time_str:
        return 0.0
    parts = time_str.split(':') # parts is a LIST, e.g., ['00', '01', '30.50']
    try:
        if len(parts) == 3: # Ensure we have hours, minutes, and seconds
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds_component = float(parts[2])
            total_seconds = (hours * 3600) + (minutes * 60) + seconds_component
            return total_seconds
        elif len(parts) == 2: # Handle cases like MM:SS.ms (no hours)
            minutes = int(parts[0])
            seconds_component = float(parts[1])
            total_seconds = (minutes * 60) + seconds_component
            return total_seconds
        elif len(parts) == 1: # Handle cases like SS.ms (only seconds)
             seconds_component = float(parts[0])
             return seconds_component
        else:
            print(f"Warning: Could not parse time string '{time_str}' due to unexpected format: {parts}")
            return 0.0
    except (IndexError, ValueError) as e:
        print(f"Warning: Could not parse time string '{time_str}'. Error: {e}. Parts: {parts}")
        return 0.0

class VideoInfo:
    def __init__(self, video_path):
        self.video_path = video_path
        self.display_name = os.path.basename(video_path)
        self.external_srt_path = None
        self.embedded_subtitle_streams = []
        self.selected_subtitle_config = {'type': 'none'}

    def find_external_srt(self):
        base, _ = os.path.splitext(self.video_path)
        srt_path = base + ".srt"
        if os.path.exists(srt_path):
            self.external_srt_path = srt_path
            if self.selected_subtitle_config['type'] == 'none':
                self.set_selected_subtitle({'type': 'external', 'path': self.external_srt_path})

    def probe_embedded_subs(self, ffprobe_path, logger_func):
        if not ffprobe_path or not os.path.exists(ffprobe_path):
            logger_func(f"ffprobe not available, cannot probe embedded subs for {self.display_name}", "orange")
            return
        try:
            probe = ffmpeg.probe(self.video_path, cmd=ffprobe_path)
            self.embedded_subtitle_streams = []
            for stream in probe.get('streams', []):
                if stream.get('codec_type') == 'subtitle':
                    tags = stream.get('tags', {})
                    lang = tags.get('language', 'und')
                    title = tags.get('title', f"Stream {stream['index']} ({stream.get('codec_name', 'N/A')})")
                    self.embedded_subtitle_streams.append({
                        'index': stream['index'],
                        'codec': stream.get('codec_name', 'N/A'),
                        'lang': lang,
                        'title': title,
                        'display': f"Embedded: {title} (lang:{lang}, type:{stream.get('codec_name', 'N/A')}, index:{stream['index']})"
                    })
        except ffmpeg.Error as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            logger_func(f"Error probing subtitles for {self.display_name}: {err_msg}", "red")
        except Exception as e:
            logger_func(f"Unexpected error probing subtitles for {self.display_name}: {str(e)}", "red")

    def get_available_subtitle_options_for_ui(self):
        options = []
        options.append(("No Subtitles", {'type': 'none'}))
        if self.external_srt_path:
            options.append(("External SRT: " + os.path.basename(self.external_srt_path),
                            {'type': 'external', 'path': self.external_srt_path}))
        for sub_stream in self.embedded_subtitle_streams:
            options.append((sub_stream['display'],
                            {'type': 'embedded', 'index': sub_stream['index'], 'video_path': self.video_path}))
        return options

    def set_selected_subtitle(self, config):
        self.selected_subtitle_config = config if config else {'type': 'none'}

    def get_selected_subtitle_config(self):
        return self.selected_subtitle_config

    def get_listbox_display_text(self):
        sub_type = self.selected_subtitle_config.get('type', 'none')
        sub_desc = "No Subtitles"
        if sub_type == 'external':
            sub_desc = "External SRT"
        elif sub_type == 'embedded':
            idx = self.selected_subtitle_config.get('index')
            found_stream = next((s for s in self.embedded_subtitle_streams if s['index'] == idx), None)
            if found_stream:
                sub_desc = f"Embedded: {found_stream['title']} (idx:{idx})"
            else:
                sub_desc = f"Embedded (Index {idx})"
        return f"{self.display_name}  --  [{sub_desc}]"

class HardcodeApp:
    def __init__(self, master):
        self.master = master
        master.title("Advanced Video Converter (Portable FFmpeg) v1.07")
        master.geometry("900x850")

        self.selected_files_map = {}
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        self.is_processing = False
        self.ffmpeg_ready = False
        self.ffprobe_ready = False
        self.current_ffmpeg_process = None
        self.log_text_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.is_paused = False
        self.output_formats = {"MP4": ".mp4", "MKV": ".mkv", "MOV": ".mov", "WEBM": ".webm"}
        self.output_format_var = tk.StringVar(value="MP4")
        self.target_size_gb_var = tk.StringVar(value="")
        self.current_video_progress_label_var = tk.StringVar(value="0.0%")
        self.overall_progress_label_var = tk.StringVar(value="0.0%")
        self.total_duration_all_files = 0.0
        self.processed_duration_all_files = 0.0
        self.current_selected_video_path_for_subs = None
        self.subtitle_option_map_for_ui = {}

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
            self.style.configure('Accent.TButton', background=accent_bg_color, foreground=accent_fg_color)
        self.log_color_tags = {"green": "log_green", "red": "log_red", "orange": "log_orange", "blue": "log_blue", "purple": "log_purple", "gray": "log_gray", "ffmpeg_output": "ffmpeg_output"}

    def setup_ui(self):
        main_content_frame = ttk.Frame(self.master, padding="15 15 15 15"); main_content_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = ttk.LabelFrame(main_content_frame, text="1. Select Input Files"); input_frame.pack(padx=0, pady=(0,10), fill=tk.X)
        input_buttons_frame = ttk.Frame(input_frame); input_buttons_frame.pack(padx=5, pady=5, fill=tk.X)
        btn_select_files = ttk.Button(input_buttons_frame, text="Select Video File(s)", command=self.select_video_files); btn_select_files.pack(side=tk.LEFT, padx=(0,5), pady=5)
        btn_select_folder = ttk.Button(input_buttons_frame, text="Select Video Folder", command=self.select_video_folder); btn_select_folder.pack(side=tk.LEFT, padx=5, pady=5)
        btn_clear_list = ttk.Button(input_buttons_frame, text="Clear List", command=self.clear_file_list); btn_clear_list.pack(side=tk.RIGHT, padx=(5,0), pady=5)
        btn_remove_selected = ttk.Button(input_buttons_frame, text="Remove Selected", command=self.remove_selected_files); btn_remove_selected.pack(side=tk.RIGHT, padx=(5,0), pady=5)
        
        list_frame = ttk.LabelFrame(main_content_frame, text="2. Files to Process"); list_frame.pack(padx=0, pady=5, fill=tk.BOTH, expand=True)
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, exportselection=False, font=(self.base_font_family, self.base_font_size), bg="white", fg="#333333", selectbackground="#0078d4", selectforeground="white", relief=tk.FLAT, borderwidth=0, highlightthickness=1, highlightbackground="#cccccc")
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1) 
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview); scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0,1), pady=1)
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_list_select)

        self.subtitle_config_frame = ttk.LabelFrame(main_content_frame, text="Subtitle Configuration (for selected video)")
        self.subtitle_config_frame.pack(padx=0, pady=(5,5), fill=tk.X)
        self.subtitle_config_frame.grid_columnconfigure(1, weight=1)
        self.selected_video_for_sub_label = ttk.Label(self.subtitle_config_frame, text="No video selected.")
        self.selected_video_for_sub_label.grid(row=0, column=0, columnspan=2, padx=5, pady=2, sticky=tk.W)
        ttk.Label(self.subtitle_config_frame, text="Choose Subtitle:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.subtitle_options_combo = ttk.Combobox(self.subtitle_config_frame, state="disabled", width=60)
        self.subtitle_options_combo.grid(row=1, column=1, padx=5, pady=2, sticky=tk.EW)
        self.subtitle_options_combo.bind('<<ComboboxSelected>>', self.on_subtitle_option_selected_ui)

        output_settings_frame = ttk.LabelFrame(main_content_frame, text="3. Output Configuration"); output_settings_frame.pack(padx=0, pady=(5,10), fill=tk.X)
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
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, wrap=tk.WORD, state=tk.DISABLED, font=('Consolas', self.base_font_size -1), relief=tk.FLAT, borderwidth=0, highlightthickness=1, highlightbackground="#cccccc", bg="white", fg="#333333", padx=5, pady=5)
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
                video_info = VideoInfo(video_path)
                video_info.find_external_srt()
                if self.ffprobe_ready:
                    video_info.probe_embedded_subs(FFPROBE_EXECUTABLE_PATH, self.log_message)
                
                if video_info.external_srt_path and video_info.selected_subtitle_config.get('type') == 'none':
                     video_info.set_selected_subtitle({'type': 'external', 'path': video_info.external_srt_path})
                elif not video_info.external_srt_path and video_info.embedded_subtitle_streams and video_info.selected_subtitle_config.get('type') == 'none':
                    pass 
                
                self.selected_files_map[video_path] = video_info
                self.log_message(f"Added: {video_info.display_name}. External SRT: {'Yes' if video_info.external_srt_path else 'No'}. Embedded Subs: {len(video_info.embedded_subtitle_streams)}", "green")
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

    def clear_file_list(self):
        self.selected_files_map.clear()
        self.update_file_listbox()
        self.on_file_list_select(None)
        self.log_message("File list cleared.")

    def remove_selected_files(self):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            self.log_message("No files selected to remove.", "orange"); return
        current_paths_in_listbox_order = list(self.selected_files_map.keys())
        paths_to_remove = [current_paths_in_listbox_order[index] for index in selected_indices if 0 <= index < len(current_paths_in_listbox_order)]
        if not paths_to_remove: return
        removed_count = 0
        for path in paths_to_remove:
            if path in self.selected_files_map:
                del self.selected_files_map[path]; removed_count += 1
        if removed_count > 0:
            self.update_file_listbox()
            self.on_file_list_select(None) 
            self.log_message(f"Removed {removed_count} file(s) from the list.", "blue")

    def update_file_listbox(self):
        selected_idx_before_update = self.file_listbox.curselection()
        self.file_listbox.delete(0, tk.END)
        paths_in_order = [] 
        for video_path_idx, (video_path, video_info) in enumerate(self.selected_files_map.items()):
            display_text = video_info.get_listbox_display_text()
            self.file_listbox.insert(tk.END, display_text)
            paths_in_order.append(video_path)
            sub_type = video_info.get_selected_subtitle_config().get('type', 'none')
            color = "#333333" 
            if sub_type == 'external' or sub_type == 'embedded': color = "#006400" 
            elif video_info.external_srt_path or video_info.embedded_subtitle_streams: color = "#CC5500" 
            self.file_listbox.itemconfig(video_path_idx, {'fg': color})

        if selected_idx_before_update and self.current_selected_video_path_for_subs:
            try:
                new_idx = paths_in_order.index(self.current_selected_video_path_for_subs)
                self.file_listbox.selection_set(new_idx); self.file_listbox.activate(new_idx); self.file_listbox.see(new_idx)
            except ValueError: self.on_file_list_select(None) 
        elif not self.selected_files_map: self.on_file_list_select(None)

    def on_file_list_select(self, event):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            self.selected_video_for_sub_label.config(text="No video selected.")
            self.subtitle_options_combo.set(''); self.subtitle_options_combo.config(values=[], state="disabled")
            self.current_selected_video_path_for_subs = None; return

        selected_idx = selected_indices[0]
        paths_in_order = list(self.selected_files_map.keys())
        if selected_idx >= len(paths_in_order): self.current_selected_video_path_for_subs = None; self.on_file_list_select(None); return 
            
        self.current_selected_video_path_for_subs = paths_in_order[selected_idx]
        video_info = self.selected_files_map.get(self.current_selected_video_path_for_subs)
        if not video_info: self.current_selected_video_path_for_subs = None; self.on_file_list_select(None); return

        self.selected_video_for_sub_label.config(text=f"Video: {video_info.display_name}")
        ui_options = video_info.get_available_subtitle_options_for_ui()
        self.subtitle_option_map_for_ui = {disp: cfg for disp, cfg in ui_options}
        self.subtitle_options_combo.config(values=[disp for disp, cfg in ui_options], state="readonly")
        current_config = video_info.get_selected_subtitle_config()
        current_display_text = "No Subtitles" 
        for disp, cfg in ui_options:
            if cfg['type'] == current_config.get('type'):
                if cfg['type'] == 'none': current_display_text = disp; break
                elif cfg['type'] == 'external' and cfg.get('path') == current_config.get('path'): current_display_text = disp; break
                elif cfg['type'] == 'embedded' and cfg.get('index') == current_config.get('index'): current_display_text = disp; break
        self.subtitle_options_combo.set(current_display_text)

    def on_subtitle_option_selected_ui(self, event):
        if not self.current_selected_video_path_for_subs: return
        video_info = self.selected_files_map.get(self.current_selected_video_path_for_subs)
        if not video_info: return
        selected_display_text = self.subtitle_options_combo.get()
        new_config = self.subtitle_option_map_for_ui.get(selected_display_text)
        if new_config:
            video_info.set_selected_subtitle(new_config)
            self.update_file_listbox() 
            self.log_message(f"Subtitle for {video_info.display_name} set to: {selected_display_text}", "blue")
        else: self.log_message(f"Error: Could not map UI subtitle choice '{selected_display_text}' to config.", "red")

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
            else: self.overall_progress_bar['value'] = 0; self.overall_progress_label_var.set("0.0%")

    def get_video_duration(self, video_path):
        try:
            probe_data = ffmpeg.probe(video_path, cmd=FFPROBE_EXECUTABLE_PATH)
            duration_str = probe_data.get('format', {}).get('duration')
            if duration_str: return float(duration_str)
        except Exception as e: self.log_message(f"Error probing duration for {os.path.basename(video_path)}: {e}", "red")
        return 0.0

    def precalculate_total_duration(self, files_to_encode_map):
        self.total_duration_all_files = 0.0
        self.log_message("Calculating total video duration for overall progress...", "blue")
        for video_path in files_to_encode_map.keys():
            duration = self.get_video_duration(video_path)
            self.total_duration_all_files += duration
            if self.stop_event.is_set(): self.log_message("Pre-calculation stopped by user.", "orange"); return False
        self.log_message(f"Total estimated duration for all files: {self.total_duration_all_files:.2f} seconds.", "blue")
        return True

    def encode_single_video(self, video_info, output_dir, output_extension, target_size_gb_str):
        video_path = video_info.video_path
        base, _ = os.path.splitext(os.path.basename(video_path))

        original_selected_subtitle_config = video_info.get_selected_subtitle_config()
        current_subtitle_config = dict(original_selected_subtitle_config) if isinstance(original_selected_subtitle_config, dict) else {'type': 'none'}

        if not isinstance(current_subtitle_config, dict):
            self.log_message(f"Warning ({base}): current_subtitle_config invalid ({type(current_subtitle_config)}). Assuming no subs.", "orange")
            current_subtitle_config = {'type': 'none'}

        has_subs_to_burn_initially = current_subtitle_config.get('type') not in [None, 'none']
        extracted_srt_path_for_this_file = None

        if video_path.lower().endswith('.mkv') and has_subs_to_burn_initially and current_subtitle_config.get('type') == 'embedded':
            self.log_message(f"Info ({base}): MKV with embedded subtitle selected. Attempting extraction to SRT.", "blue")
            embedded_sub_stream_index = current_subtitle_config.get('index')
            
            if embedded_sub_stream_index is None:
                self.log_message(f"ERROR ({base}): Embedded subtitle selected, but no stream index found in config.", "red")
                return video_path, "error", f"Invalid embedded subtitle configuration for {base} (missing index)."

            target_srt_filename = base + ".srt" 
            output_srt_path = os.path.join(os.path.dirname(video_path), target_srt_filename) 

            extract_args = [
                FFMPEG_EXECUTABLE_PATH, 
                '-y',
                '-i', video_path,
                '-map', f'0:{embedded_sub_stream_index}',
                '-c:s', 'srt',
                output_srt_path
            ]
            self.log_message(f"DEBUG: FFmpeg SRT extraction command for {base}: {' '.join(extract_args)}", "gray")
            extraction_creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            try:
                extract_process = subprocess.run(extract_args, capture_output=True, text=True, check=False, creationflags=extraction_creationflags, errors='ignore')
                
                if extract_process.returncode == 0:
                    self.log_message(f"Success ({base}): Extracted subtitle to {output_srt_path}", "green")
                    current_subtitle_config['type'] = 'external'
                    current_subtitle_config['path'] = output_srt_path
                    extracted_srt_path_for_this_file = output_srt_path 
                else:
                    self.log_message(f"ERROR ({base}): Failed to extract subtitle. FFmpeg exit code: {extract_process.returncode}", "red")
                    self.log_message(f"Extraction stderr for {base}:\n{extract_process.stderr}", "red")
                    return video_path, "error", f"Failed to extract selected embedded subtitle for {base}."
            except Exception as extraction_exc:
                self.log_message(f"ERROR ({base}): Exception during subtitle extraction: {extraction_exc}", "red")
                return video_path, "error", f"Exception during subtitle extraction for {base}: {extraction_exc}\n{traceback.format_exc()}"
        
        has_subs_to_burn = current_subtitle_config.get('type') not in [None, 'none']
        suffix = "_hardsub" if has_subs_to_burn else "_converted"
        output_filename = f"{base}{suffix}{output_extension}"
        output_path = os.path.join(output_dir, output_filename)

        if self.master.winfo_exists():
            self.master.after(0, self.update_current_video_progress, 0, "0.0%")
        if os.path.exists(output_path):
            return video_path, "skipped", f"Output file already exists: {output_path}"
        
        default_srt_encoding = 'UTF-8'
        
        try:
            probe_opts = {'cmd': FFPROBE_EXECUTABLE_PATH}
            probe_data = ffmpeg.probe(video_path, **probe_opts)
            format_info = probe_data.get('format', {})
            video_streams_probe = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video']
            audio_streams_probe = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio']
            
            current_video_bitrate_str = MIN_VIDEO_BITRATE_STR
            if format_info.get('bit_rate'): 
                current_video_bitrate_str = format_info['bit_rate']
            elif video_streams_probe and video_streams_probe[0].get('bit_rate'): # Correctly access first element
                current_video_bitrate_str = video_streams_probe[0]['bit_rate']
            current_video_bitrate_int = parse_bitrate_to_int(current_video_bitrate_str)
            min_video_bitrate_int = parse_bitrate_to_int(MIN_VIDEO_BITRATE_STR)
            
            target_v_bitrate_str = MIN_VIDEO_BITRATE_STR
            if current_video_bitrate_int == 0: 
                self.log_message(f"Warning ({base}): Could not determine source video bitrate, using minimum: {MIN_VIDEO_BITRATE_STR}.", "orange")
            elif current_video_bitrate_int < min_video_bitrate_int:
                self.log_message(f"Info ({base}): Source video bitrate ({format_bitrate_from_int(current_video_bitrate_int)}) is lower than minimum: {MIN_VIDEO_BITRATE_STR}.", "blue")
            else: 
                target_v_bitrate_str = format_bitrate_from_int(current_video_bitrate_int)
            
            target_a_bitrate_str = DEFAULT_AUDIO_BITRATE
            original_audio_bitrate_probed = None
            if audio_streams_probe: # Check if list is not empty
                first_audio_stream = audio_streams_probe[0] # Get the first audio stream dictionary
                if first_audio_stream.get('bit_rate'): # Call .get() on the dictionary
                    probed_ab_int = parse_bitrate_to_int(first_audio_stream['bit_rate'])
                    if probed_ab_int > 0: 
                        target_a_bitrate_str = format_bitrate_from_int(probed_ab_int)
                        original_audio_bitrate_probed = target_a_bitrate_str
                    
            log_audio_bitrate = original_audio_bitrate_probed if original_audio_bitrate_probed else DEFAULT_AUDIO_BITRATE
            self.log_message(f"Info for {base}: Initial video bitrate: {target_v_bitrate_str}, audio bitrate: {log_audio_bitrate}", "blue")

            duration_str = format_info.get('duration')
            total_duration_s = 0.0
            if duration_str:
                try: total_duration_s = float(duration_str)
                except ValueError: self.log_message(f"Warning ({base}): Could not parse duration '{duration_str}' for progress.", "orange")
            
            if target_size_gb_str and duration_str and total_duration_s > 0:
                try:
                    target_size_gb = float(target_size_gb_str)
                    if target_size_gb > 0:
                        target_filesize_bytes = target_size_gb * 1024 * 1024 * 1024
                        required_total_bitrate_bps = (target_filesize_bytes * 8) / total_duration_s
                        audio_bitrate_bps_for_calc = parse_bitrate_to_int(target_a_bitrate_str)
                        audio_bitrate_bps_for_calc = audio_bitrate_bps_for_calc if audio_bitrate_bps_for_calc > 0 else parse_bitrate_to_int(DEFAULT_AUDIO_BITRATE)
                        calculated_video_bitrate_bps = required_total_bitrate_bps - audio_bitrate_bps_for_calc
                        if calculated_video_bitrate_bps < min_video_bitrate_int:
                            self.log_message(f"Warning for {base}: Target size results in video bitrate ({format_bitrate_from_int(calculated_video_bitrate_bps)}) < min ({MIN_VIDEO_BITRATE_STR}). Using min video bitrate. Output may be larger.", "orange")
                            target_v_bitrate_str_temp = MIN_VIDEO_BITRATE_STR
                        else: target_v_bitrate_str_temp = format_bitrate_from_int(calculated_video_bitrate_bps)
                        self.log_message(f"Info for {base}: Calculated target video bitrate: {target_v_bitrate_str_temp} for size {target_size_gb}GB (audio: {target_a_bitrate_str})", "blue")
                        target_v_bitrate_str = target_v_bitrate_str_temp
                    else: self.log_message(f"Warning for {base}: Invalid target size '{target_size_gb_str}'. Using probed/default bitrate logic.", "orange")
                except ValueError: self.log_message(f"Warning for {base}: Invalid target size value '{target_size_gb_str}'. Using probed/default bitrate logic.", "orange")
            elif target_size_gb_str and (not duration_str or total_duration_s <= 0):
                self.log_message(f"Warning for {base}: Could not get valid duration. Target size ignored. Using probed/default bitrate logic.", "orange")

            stream_input = ffmpeg.input(video_path)
            video_output_streams = stream_input.video
            audio_output_streams = stream_input.audio

            output_params = {
                'vcodec': 'libx264', 'acodec': 'aac', 'preset': FFMPEG_PRESET,
                'b:v': target_v_bitrate_str, 'b:a': target_a_bitrate_str, 'strict': '-2'
            }

            if has_subs_to_burn:
                sub_type = current_subtitle_config['type']
                if sub_type == 'external':
                    sub_path_for_filter = escape_path_for_ffmpeg_filter_filename(current_subtitle_config['path'])
                    subtitle_options = {'filename': sub_path_for_filter}
                    final_srt_charenc = default_srt_encoding
                    if current_subtitle_config['path'] != extracted_srt_path_for_this_file: # Only apply special charenc if not the one we just extracted
                        if 'path' in current_subtitle_config and current_subtitle_config['path'].endswith("2017 - China Salesman.srt"): # Example specific charenc
                             final_srt_charenc = 'CP1252'
                    if final_srt_charenc.upper() != 'UTF-8':
                        subtitle_options['charenc'] = final_srt_charenc
                    video_output_streams = video_output_streams.filter('subtitles', **subtitle_options)
                    self.log_message(f"Applying external subtitle filter: {current_subtitle_config.get('path', 'N/A')} with options: {subtitle_options}", "blue")
                elif sub_type == 'embedded': 
                    # This path should now only be taken if it's not an MKV or if MKV extraction was skipped/failed AND user still wants to try vidsub
                    sub_index = current_subtitle_config['index']
                    self.log_message(f"Applying embedded subtitle filter (index {sub_index}) using 'vidsub' (non-MKV or extraction failed/skipped)", "blue")
                    video_output_streams = video_output_streams.filter('subtitles', filename='vidsub', si=sub_index)

            final_stream_obj = ffmpeg.output(video_output_streams, audio_output_streams, output_path, **output_params)
            args = final_stream_obj.compile(cmd=FFMPEG_EXECUTABLE_PATH, overwrite_output=True)
            self.log_message(f"DEBUG: FFmpeg command for {base}: {' '.join(args)}", "gray")

            current_process_creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            self.current_ffmpeg_process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=current_process_creationflags, universal_newlines=True, errors='ignore', text=True)
            log_queue = queue.Queue()
            ffmpeg_stderr_output_list = []

            def pipe_reader_thread(pipe, pipe_name, local_stderr_list_ref):
                try:
                    with pipe:
                        for line in iter(pipe.readline, ''):
                            log_queue.put((pipe_name, line.strip()))
                            if pipe_name == "stderr": local_stderr_list_ref.append(line.strip())
                finally: log_queue.put((pipe_name, None))

            stdout_thread = threading.Thread(target=pipe_reader_thread, args=[self.current_ffmpeg_process.stdout, "stdout", ffmpeg_stderr_output_list])
            stderr_thread = threading.Thread(target=pipe_reader_thread, args=[self.current_ffmpeg_process.stderr, "stderr", ffmpeg_stderr_output_list])
            stdout_thread.start(); stderr_thread.start()

            time_regex = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2,3})")
            if total_duration_s <= 0: self.log_message(f"Warning ({base}): Progress percentage unavailable due to invalid/missing duration.", "orange")
            last_overall_update_time_s = 0
            active_threads = 2
            while active_threads > 0:
                try:
                    pipe_name, line = log_queue.get(timeout=0.1)
                    if line is None:
                        active_threads -= 1
                        if pipe_name == "stdout": stdout_thread.join(timeout=0.1)
                        elif pipe_name == "stderr": stderr_thread.join(timeout=0.1)
                        continue
                    self.log_ffmpeg_output(line)
                    if pipe_name == "stderr" and total_duration_s > 0:
                        match = time_regex.search(line)
                        if match:
                            current_time_str = match.group(1); current_time_s = parse_ffmpeg_time_to_seconds(current_time_str)
                            if current_time_s >= 0:
                                percentage = min(100.0, (current_time_s / total_duration_s) * 100) if total_duration_s > 0 else 0
                                if self.master.winfo_exists(): self.master.after(0, self.update_current_video_progress, percentage)
                                time_delta_for_overall = current_time_s - last_overall_update_time_s
                                if time_delta_for_overall > 0:
                                    self.processed_duration_all_files += time_delta_for_overall; last_overall_update_time_s = current_time_s
                                    if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)
                except queue.Empty:
                    if self.current_ffmpeg_process and self.current_ffmpeg_process.poll() is not None and active_threads == 0: break
                    elif self.current_ffmpeg_process and self.current_ffmpeg_process.poll() is not None: pass
            
            stdout_thread.join(timeout=0.5); stderr_thread.join(timeout=0.5)
            return_code = -1 
            if self.current_ffmpeg_process:
                try: return_code = self.current_ffmpeg_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.log_message(f"Warning ({base}): FFmpeg process did not terminate gracefully after wait timeout. Killing.", "orange")
                    self.current_ffmpeg_process.kill(); return_code = self.current_ffmpeg_process.wait()
            else: self.log_message(f"ERROR: ({base}): current_ffmpeg_process was None before final wait!", "red")

            if total_duration_s > 0 and last_overall_update_time_s < total_duration_s and return_code == 0 :
                 time_delta_for_overall = total_duration_s - last_overall_update_time_s
                 self.processed_duration_all_files += time_delta_for_overall
                 if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)

            if return_code == 0:
                if total_duration_s > 0 and self.master.winfo_exists(): self.master.after(0, self.update_current_video_progress, 100, "100.0%")
                return video_path, "success", f"Successfully encoded: {output_path}"
            else:
                full_stderr_for_log = "\n".join(ffmpeg_stderr_output_list)
                print(f"\n--- FFmpeg Process Error Details for {os.path.basename(video_path)} ---")
                print(f"FFmpeg Command: {' '.join(args)}"); print(f"Return Code: {return_code}")
                print("FFmpeg Standard Error Output (captured by thread):")
                print(full_stderr_for_log if ffmpeg_stderr_output_list else "No stderr captured by thread.")
                print("--- End FFmpeg Error Details ---\n")
                ui_error_message_lines = []
                pattern_file_not_found = re.compile(r'.*No such file or directory.*', re.IGNORECASE)
                pattern_invalid_argument = re.compile(r'.*Invalid argument.*', re.IGNORECASE)
                pattern_unable_to_open_vidsub = re.compile(r'.*Unable to open vidsub.*', re.IGNORECASE)
                pattern_srt_utf8_error = re.compile(r'.*Invalid UTF-8.*decoded subtitles text.*', re.IGNORECASE)
                pattern_charenc_not_found = re.compile(r".*Option charenc not found.*", re.IGNORECASE)
                found_specific_error = False
                for err_line in reversed(ffmpeg_stderr_output_list):
                    if pattern_file_not_found.search(err_line): ui_error_message_lines.append(f"Error hint: File not found? - {err_line}"); found_specific_error = True; break
                    if pattern_invalid_argument.search(err_line): ui_error_message_lines.append(f"Error hint: Invalid argument? - {err_line}"); found_specific_error = True; break
                    if pattern_unable_to_open_vidsub.search(err_line): ui_error_message_lines.append(f"Error hint: Could not use embedded subtitle with vidsub - {err_line}"); found_specific_error = True; break
                    if pattern_srt_utf8_error.search(err_line): ui_error_message_lines.append(f"Error hint: SRT file encoding issue (not UTF-8 or corrupt) - {err_line}"); found_specific_error = True; break
                    if pattern_charenc_not_found.search(err_line): ui_error_message_lines.append(f"Error hint: 'charenc' option not recognized by FFmpeg. Check FFmpeg build (libiconv). - {err_line}"); found_specific_error = True; break
                if not found_specific_error: ui_error_message_lines.append(f"FFmpeg error for {os.path.basename(video_path)} (code {return_code}).")
                ui_error_message_lines.append("Last few lines from FFmpeg (if any captured):")
                ui_error_message_lines.extend(ffmpeg_stderr_output_list[-5:])
                ui_error_message = "\n".join(ui_error_message_lines)
                if self.stop_event.is_set(): return video_path, "stopped", f"Encoding stopped by user for: {output_path} (ffmpeg exit code {return_code})"
                return video_path, "error", ui_error_message
        except ffmpeg.Error as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            error_message = f"python-ffmpeg library error for {os.path.basename(video_path)}: {err_msg}"
            self.log_message(error_message + f"\nTraceback: {traceback.format_exc()}", "red")
            return video_path, "error", error_message
        except Exception as e:
            error_message = f"General error during encoding for {os.path.basename(video_path)}: {str(e)}"
            self.log_message(error_message + f"\nTraceback: {traceback.format_exc()}", "red")
            return video_path, "error", f"{error_message}\nTraceback:\n{traceback.format_exc()}"
        finally:
            if extracted_srt_path_for_this_file and os.path.exists(extracted_srt_path_for_this_file):
                try:
                    os.remove(extracted_srt_path_for_this_file)
                    self.log_message(f"Info ({base}): Cleaned up temporary SRT: {extracted_srt_path_for_this_file}", "gray")
                except Exception as cleanup_exc:
                    self.log_message(f"Warning ({base}): Failed to clean up temporary SRT {extracted_srt_path_for_this_file}: {cleanup_exc}", "orange")
            
            if self.current_ffmpeg_process and self.current_ffmpeg_process.poll() is None:
                try: self.current_ffmpeg_process.kill()
                except Exception: pass
            self.current_ffmpeg_process = None

    def start_encoding_thread(self):
        if self.is_processing: self.log_message("Processing already in progress.", "orange"); return
        if not (self.ffmpeg_ready and self.ffprobe_ready):
            self.log_message("FFmpeg/ffprobe not ready. Cannot start encoding.", "red")
            messagebox.showerror("FFmpeg/ffprobe Error", "Portable FFmpeg/ffprobe not configured. Check setup."); return
        files_to_encode_map = self.selected_files_map.copy() 
        if not files_to_encode_map:
            self.log_message("No videos selected for processing.", "red")
            messagebox.showerror("No Files", "Please select video files to process."); return
        output_path_str = self.output_dir.get()
        if not output_path_str or not os.path.isdir(output_path_str): 
            self.log_message(f"Output directory '{output_path_str}' invalid.", "red")
            messagebox.showerror("Invalid Output Path", f"Output directory '{output_path_str}' does not exist or is invalid."); return
        
        self.is_processing = True; self.stop_event.clear(); self.pause_event.clear(); self.is_paused = False
        self.start_button.config(state=tk.DISABLED); self.pause_resume_button.config(text="Pause", state=tk.NORMAL); self.stop_button.config(state=tk.NORMAL)
        self.update_current_video_progress(0, "0.0%"); self.update_overall_progress(0, 1)
        self.processed_duration_all_files = 0.0 
        output_ext = self.output_formats[self.output_format_var.get()]; target_size_str = self.target_size_gb_var.get().strip()
        thread = threading.Thread(target=self.process_videos_sequentially, args=(files_to_encode_map, output_path_str, output_ext, target_size_str), daemon=True)
        thread.start()

    def process_videos_sequentially(self, files_to_encode_map, output_path_str, output_ext, target_size_str):
        if not self.precalculate_total_duration(files_to_encode_map): 
            self.log_message("Failed to precalculate total duration or was stopped. Aborting encoding.", "red")
            if self.master.winfo_exists(): self.master.after(0, self.on_processing_finished); return
        if self.total_duration_all_files <= 0:
             self.log_message("Warning: Total duration of files is zero. Overall progress may not be accurate.", "orange")
             if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, 0, 0)
        else:
            if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, 0, self.total_duration_all_files)

        self.log_message(f"Starting encoding for {len(files_to_encode_map)} files...", "blue")
        success_count = 0; error_count = 0; skipped_count = 0; stopped_for_file_count = 0

        for video_path_key, video_info_obj in files_to_encode_map.items():
            if self.pause_event.is_set():
                self.log_message("Processing paused. Click Resume to continue.", "blue")
                while self.pause_event.is_set(): 
                    if self.stop_event.is_set(): break
                    time.sleep(0.2) 
            if self.stop_event.is_set(): self.log_message("Stop signal received. Halting further processing.", "orange"); break 
            self.log_message(f"Processing: {video_info_obj.display_name}...", "blue")
            duration_of_current_file_for_overall = self.get_video_duration(video_info_obj.video_path)
            try:
                _, status, message = self.encode_single_video(video_info_obj, output_path_str, output_ext, target_size_str)
                color_key = "gray"
                if status == "error": error_count += 1; color_key = "red"
                elif status == "skipped": skipped_count += 1; color_key = "orange"
                elif status == "stopped": stopped_for_file_count += 1; color_key = "purple"
                elif status == "success": success_count += 1; color_key = "green"
                self.log_message(f"[{status.upper()}] {video_info_obj.display_name}: {message}", color_key)
                if status in ["skipped", "error"] and duration_of_current_file_for_overall > 0:
                     self.processed_duration_all_files += duration_of_current_file_for_overall
                     if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)
                if status == "stopped": self.log_message("Halting further processing due to user stop during a file.", "orange"); self.stop_event.set(); break
            except Exception as exc:
                self.log_message(f"[FATAL ERROR] {video_info_obj.display_name}: Encoding task failed unexpectedly - {exc}\n{traceback.format_exc()}", "red"); error_count += 1
                if duration_of_current_file_for_overall > 0: 
                     self.processed_duration_all_files += duration_of_current_file_for_overall
                     if self.master.winfo_exists(): self.master.after(0, self.update_overall_progress, self.processed_duration_all_files, self.total_duration_all_files)
        
        self.log_message(f"--- Encoding Finished ---", "blue")
        self.log_message(f"Successfully encoded: {success_count}", "green")
        self.log_message(f"Errors: {error_count}", "red" if error_count > 0 else "gray")
        self.log_message(f"Skipped (already exists): {skipped_count}", "orange" if skipped_count > 0 else "gray")
        processed_files = success_count + error_count + skipped_count + stopped_for_file_count
        general_stopped_count = len(files_to_encode_map) - processed_files
        if stopped_for_file_count > 0: self.log_message(f"Stopped by user during processing: {stopped_for_file_count} file(s)", "purple")
        if general_stopped_count > 0 : self.log_message(f"Files not started due to stop: {general_stopped_count}", "purple")
        elif self.stop_event.is_set() and stopped_for_file_count == 0 and general_stopped_count == 0 : self.log_message(f"Processing was signaled to stop, but all tasks completed or handled.", "purple")
        if self.master.winfo_exists(): self.master.after(0, self.on_processing_finished)

    def on_processing_finished(self):
        if self.master.winfo_exists():
            self.is_processing = False
            self.start_button.config(state=tk.NORMAL); self.pause_resume_button.config(text="Pause", state=tk.DISABLED); self.stop_button.config(state=tk.DISABLED)
            self.current_ffmpeg_process = None; self.is_paused = False
            self.update_current_video_progress(0, "0.0%") 
            if not self.stop_event.is_set():
                if self.total_duration_all_files > 0 : self.update_overall_progress(self.total_duration_all_files, self.total_duration_all_files)
                else: self.update_overall_progress(1,1)
            self.stop_event.clear(); self.pause_event.clear()
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
                try: 
                    if self.current_ffmpeg_process.stdin and not self.current_ffmpeg_process.stdin.closed and self.current_ffmpeg_process.stdin.writable():
                        self.current_ffmpeg_process.stdin.write('q\n'); self.current_ffmpeg_process.stdin.flush()
                    else: self.log_message("FFmpeg stdin not writable or closed. Cannot send 'q'.", "red")
                except (OSError, ValueError, BrokenPipeError, AttributeError) as e: self.log_message(f"Could not send 'q' to FFmpeg: {e}. FFmpeg might terminate abruptly.", "red")
            if self.is_paused: self.pause_event.clear(); self.is_paused = False
            self.stop_button.config(state=tk.DISABLED); self.pause_resume_button.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = HardcodeApp(root)
    root.mainloop()