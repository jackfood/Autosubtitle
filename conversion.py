import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import os
import subprocess
import threading
import ffmpeg # pip install ffmpeg-python
# import json # Not strictly used in this version but often useful with ffprobe
# from concurrent.futures import ProcessPoolExecutor, as_completed # No longer needed for sequential

# --- Configuration ---
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm')
DEFAULT_AUDIO_BITRATE = '128k'
MIN_VIDEO_BITRATE = '500k'
FFMPEG_PRESET = 'medium'

# --- Portable FFmpeg Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_BINARY_SUBDIR = "ffmpeg_binary"
FFMPEG_BIN_DIR = os.path.join(SCRIPT_DIR, FFMPEG_BINARY_SUBDIR, "bin")
FFMPEG_EXECUTABLE_PATH = os.path.join(FFMPEG_BIN_DIR, "ffmpeg.exe")
FFPROBE_EXECUTABLE_PATH = os.path.join(FFMPEG_BIN_DIR, "ffprobe.exe")
# --- End Portable FFmpeg Configuration ---

# --- Helper Functions ---
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

# --- Encoding Function ---
def encode_single_video(video_path, srt_path, output_dir,
                        ffmpeg_executable_path, ffprobe_executable_path):
    base, _ = os.path.splitext(os.path.basename(video_path))
    output_filename = f"{base}_hardsub.mp4"
    output_path = os.path.join(output_dir, output_filename)

    if os.path.exists(output_path):
        return video_path, "skipped", f"Output file already exists: {output_path}"

    try:
        probe_opts = {}
        if not ffprobe_executable_path or not os.path.isfile(ffprobe_executable_path):
            return video_path, "error", f"ffprobe executable not found at {ffprobe_executable_path}"
        probe_opts['cmd'] = ffprobe_executable_path
        probe_data = ffmpeg.probe(video_path, **probe_opts)

        format_info = probe_data.get('format', {})
        video_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video']
        audio_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio']

        target_video_bitrate = MIN_VIDEO_BITRATE
        if format_info.get('bit_rate'):
            target_video_bitrate = format_info['bit_rate']
        elif video_streams and video_streams[0].get('bit_rate'):
            target_video_bitrate = video_streams[0]['bit_rate']

        if isinstance(target_video_bitrate, str) and not target_video_bitrate.lower().endswith(('k', 'm')):
            try:
                val = int(target_video_bitrate)
                min_val_numeric = int(MIN_VIDEO_BITRATE[:-1]) * 1000 if MIN_VIDEO_BITRATE.endswith('k') else int(MIN_VIDEO_BITRATE)
                if val < min_val_numeric:
                    target_video_bitrate = MIN_VIDEO_BITRATE
                else:
                    target_video_bitrate = str(val)
            except ValueError:
                target_video_bitrate = MIN_VIDEO_BITRATE
        elif isinstance(target_video_bitrate, int):
            min_val_numeric = int(MIN_VIDEO_BITRATE[:-1]) * 1000 if MIN_VIDEO_BITRATE.endswith('k') else int(MIN_VIDEO_BITRATE)
            if target_video_bitrate < min_val_numeric:
                target_video_bitrate = MIN_VIDEO_BITRATE
            else:
                target_video_bitrate = str(target_video_bitrate)

        target_audio_bitrate = DEFAULT_AUDIO_BITRATE
        if audio_streams and audio_streams[0].get('bit_rate'):
            probed_ab = audio_streams[0]['bit_rate']
            try:
                target_audio_bitrate = str(int(probed_ab))
            except ValueError:
                target_audio_bitrate = probed_ab

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
            'b:v': target_video_bitrate,
            'b:a': target_audio_bitrate,
            'strict': '-2'
        }
        stream = ffmpeg.output(stream, output_path, **output_params)
        ffmpeg.run(stream, overwrite_output=True, quiet=False, **ffmpeg_run_opts)
        return video_path, "success", f"Successfully encoded: {output_path}"

    except ffmpeg.Error as e:
        stderr_output = e.stderr.decode('utf8', errors='ignore') if e.stderr else "No stderr output"
        error_message = f"FFmpeg error for {os.path.basename(video_path)}: {stderr_output}"
        return video_path, "error", error_message
    except Exception as e:
        error_message = f"General error for {os.path.basename(video_path)}: {str(e)}"
        return video_path, "error", error_message

# --- GUI Application ---
class HardcodeApp:
    def __init__(self, master):
        self.master = master
        master.title("Hardcode Subtitles GUI (Portable FFmpeg - Sequential)")
        master.geometry("800x600")

        self.selected_files_map = {}
        self.output_dir = tk.StringVar(value=os.getcwd())
        self.is_processing = False
        self.ffmpeg_ready = False
        self.ffprobe_ready = False

        # UI Elements (same as before)
        input_frame = ttk.LabelFrame(master, text="Input Videos & SRTs")
        input_frame.pack(padx=10, pady=10, fill=tk.X)
        btn_select_files = ttk.Button(input_frame, text="Select Video File(s)", command=self.select_video_files)
        btn_select_files.pack(side=tk.LEFT, padx=5, pady=5)
        btn_select_folder = ttk.Button(input_frame, text="Select Video Folder (Recursive)", command=self.select_video_folder)
        btn_select_folder.pack(side=tk.LEFT, padx=5, pady=5)
        btn_clear_list = ttk.Button(input_frame, text="Clear List", command=self.clear_file_list)
        btn_clear_list.pack(side=tk.LEFT, padx=5, pady=5)

        list_frame = ttk.LabelFrame(master, text="Files to Process (Video - SRT status)")
        list_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        output_frame = ttk.LabelFrame(master, text="Output Settings")
        output_frame.pack(padx=10, pady=5, fill=tk.X)
        ttk.Label(output_frame, text="Output Directory:").pack(side=tk.LEFT, padx=5, pady=5)
        self.output_dir_entry = ttk.Entry(output_frame, textvariable=self.output_dir, width=60)
        self.output_dir_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        btn_browse_output = ttk.Button(output_frame, text="Browse...", command=self.select_output_dir)
        btn_browse_output.pack(side=tk.LEFT, padx=5, pady=5)

        control_frame = ttk.Frame(master)
        control_frame.pack(padx=10, pady=10, fill=tk.X)
        self.start_button = ttk.Button(control_frame, text="Start Encoding", command=self.start_encoding_thread)
        self.start_button.pack(side=tk.RIGHT, padx=5)
        self.progress_bar = ttk.Progressbar(control_frame, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        log_frame = ttk.LabelFrame(master, text="Log")
        log_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.check_portable_ffmpeg_ffprobe()

    def check_portable_ffmpeg_ffprobe(self):
        self.ffmpeg_ready = False
        self.ffprobe_ready = False
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        if os.path.isfile(FFMPEG_EXECUTABLE_PATH):
            try:
                subprocess.run([FFMPEG_EXECUTABLE_PATH, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
                self.log_message(f"INFO: Portable ffmpeg found: {FFMPEG_EXECUTABLE_PATH}", "green")
                self.ffmpeg_ready = True
            except Exception as e:
                self.log_message(f"ERROR: Portable ffmpeg at {FFMPEG_EXECUTABLE_PATH} failed: {e}", "red")
                messagebox.showerror("FFmpeg Error", f"Portable ffmpeg.exe at:\n{FFMPEG_EXECUTABLE_PATH}\nfailed. Ensure valid executable & DLLs.")
        else:
            self.log_message(f"ERROR: Portable ffmpeg.exe not found: {FFMPEG_EXECUTABLE_PATH}", "red")
            messagebox.showerror("FFmpeg Missing", f"Portable ffmpeg.exe not found:\n{FFMPEG_EXECUTABLE_PATH}\nPlace in '{FFMPEG_BINARY_SUBDIR}/bin/'.")

        if os.path.isfile(FFPROBE_EXECUTABLE_PATH):
            try:
                subprocess.run([FFPROBE_EXECUTABLE_PATH, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
                self.log_message(f"INFO: Portable ffprobe found: {FFPROBE_EXECUTABLE_PATH}", "green")
                self.ffprobe_ready = True
            except Exception as e:
                self.log_message(f"ERROR: Portable ffprobe at {FFPROBE_EXECUTABLE_PATH} failed: {e}", "red")
                messagebox.showerror("ffprobe Error", f"Portable ffprobe.exe at:\n{FFPROBE_EXECUTABLE_PATH}\nfailed.")
        else:
            self.log_message(f"ERROR: Portable ffprobe.exe not found: {FFPROBE_EXECUTABLE_PATH}", "red")
            messagebox.showerror("ffprobe Missing", f"Portable ffprobe.exe not found:\n{FFPROBE_EXECUTABLE_PATH}\nPlace in '{FFMPEG_BINARY_SUBDIR}/bin/'.")

        if not (self.ffmpeg_ready and self.ffprobe_ready):
            self.start_button.config(state=tk.DISABLED)
            self.log_message("CRITICAL: FFmpeg/ffprobe not ready. Encoding disabled.", "red")
        else:
            self.start_button.config(state=tk.NORMAL)

    def log_message(self, message, color=None):
        if not hasattr(self, 'log_text_lock'):
            self.log_text_lock = threading.Lock()
        def _log():
            with self.log_text_lock:
                self.log_text.config(state=tk.NORMAL)
                if color:
                    tag_name = f"tag_{color.replace(' ', '_').replace(':', '')}"
                    if not hasattr(self, tag_name):
                        self.log_text.tag_configure(tag_name, foreground=color)
                        setattr(self, tag_name, True)
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
                    self.log_message(f"Found: {os.path.basename(video_path)} with SRT: {os.path.basename(srt_path)}", "green")
                else:
                    self.selected_files_map[video_path] = None
                    self.log_message(f"Found: {os.path.basename(video_path)} - MISSING SRT ({os.path.basename(srt_path)})", "orange")
                new_files_added +=1 # Count even if SRT is missing, to update listbox
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
            if not found_videos: self.log_message(f"No videos found in {folder} or subdirectories.", "orange")

    def clear_file_list(self):
        self.selected_files_map.clear()
        self.update_file_listbox()
        self.log_message("File list cleared.")

    def update_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for video_path, srt_path in self.selected_files_map.items():
            srt_status = "SRT OK" if srt_path else "SRT MISSING"
            display_text = f"{os.path.basename(video_path)}  --  [{srt_status}]"
            self.file_listbox.insert(tk.END, display_text)
            self.file_listbox.itemconfig(tk.END, {'fg': 'darkgreen' if srt_path else 'red'})

    def select_output_dir(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir.set(directory)
            self.log_message(f"Output directory set: {directory}")

    def start_encoding_thread(self):
        if self.is_processing:
            self.log_message("Processing in progress.", "orange")
            return
        if not (self.ffmpeg_ready and self.ffprobe_ready):
            self.log_message("FFmpeg/ffprobe not ready.", "red")
            messagebox.showerror("FFmpeg/ffprobe Error", "Portable FFmpeg/ffprobe not configured. Check setup.")
            return

        files_to_encode = {vp: sp for vp, sp in self.selected_files_map.items() if sp is not None}
        if not files_to_encode:
            self.log_message("No videos with SRTs selected.", "red")
            messagebox.showerror("No Files", "Select videos with corresponding .srt files.")
            return

        output_path_str = self.output_dir.get()
        if not os.path.isdir(output_path_str):
            self.log_message(f"Output directory '{output_path_str}' invalid.", "red")
            messagebox.showerror("Invalid Output Path", f"Output directory '{output_path_str}' does not exist.")
            return

        self.is_processing = True
        self.start_button.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(files_to_encode)
        
        thread = threading.Thread(target=self.process_videos_sequentially, args=(files_to_encode, output_path_str), daemon=True)
        thread.start()

    def process_videos_sequentially(self, files_to_encode, output_path_str):
        self.log_message(f"Starting sequential encoding for {len(files_to_encode)} files...", "blue")
        
        completed_count = 0
        success_count = 0
        error_count = 0
        skipped_count = 0

        for video_path, srt_path in files_to_encode.items():
            self.log_message(f"Processing: {os.path.basename(video_path)}...", "blue")
            try:
                # Call encode_single_video directly
                _, status, message = encode_single_video(
                    video_path,
                    srt_path,
                    output_path_str,
                    ffmpeg_executable_path=FFMPEG_EXECUTABLE_PATH,
                    ffprobe_executable_path=FFPROBE_EXECUTABLE_PATH
                )
                
                self.log_message(f"[{status.upper()}] {os.path.basename(video_path)}: {message}",
                                 "green" if status == "success" else ("orange" if status == "skipped" else "red"))
                if status == "success":
                    success_count += 1
                elif status == "error":
                    error_count += 1
                elif status == "skipped":
                    skipped_count +=1
            except Exception as exc:
                self.log_message(f"[ERROR] {os.path.basename(video_path)}: Encoding task failed - {exc}", "red")
                error_count += 1
            
            completed_count += 1
            self.master.after(0, self.update_progress, completed_count)

        self.log_message(f"--- Encoding Finished ---", "blue")
        self.log_message(f"Successfully encoded: {success_count}", "green")
        self.log_message(f"Errors: {error_count}", "red")
        self.log_message(f"Skipped (already exists): {skipped_count}", "orange")
        
        self.master.after(0, self.on_processing_finished)

    def update_progress(self, value):
        if self.master.winfo_exists():
            self.progress_bar['value'] = value

    def on_processing_finished(self):
        if self.master.winfo_exists():
            self.is_processing = False
            self.start_button.config(state=tk.NORMAL)
            # self.progress_bar['value'] = 0 # Keep progress bar full at the end or reset
            messagebox.showinfo("Processing Complete", "All selected videos have been processed. Check logs for details.")

if __name__ == "__main__":
    root = tk.Tk()
    app = HardcodeApp(root)
    root.mainloop()