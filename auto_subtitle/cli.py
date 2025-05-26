import os
import sys
import ffmpeg
import whisper
import argparse
import warnings
import tempfile
from .utils import filename, str2bool, write_srt
from typing import Optional, List, Dict, Any, Callable, Tuple
import re
import string
import numpy as np
import torch
import multiprocessing
import gc

try:
    import soundfile as sf
except ImportError:
    sf = None
try:
    import torchaudio
except ImportError:
    torchaudio = None

VAD_MODEL = None
VAD_UTILS = None
WHISPER_MODEL_WORKER = None

def sanitize_for_print(text_to_print: str) -> str:
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() not in ['utf-8', 'utf8']:
            return text_to_print.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding, errors='ignore')
        return text_to_print
    except Exception:
        return "".join(c if ord(c) < 128 else '?' for c in text_to_print)

def load_whisper_model_for_worker(model_name_worker: str, download_root_worker: Optional[str]):
    global WHISPER_MODEL_WORKER
    if WHISPER_MODEL_WORKER is None:
        try:
            WHISPER_MODEL_WORKER = whisper.load_model(model_name_worker, download_root=download_root_worker)
            if torch.cuda.is_available():
                 WHISPER_MODEL_WORKER.cuda()
            print(f"INFO [Worker PID {os.getpid()}]: Whisper model '{sanitize_for_print(model_name_worker)}' loaded.", flush=True)
        except Exception as e:
            print(f"ERROR [Worker PID {os.getpid()}]: Failed to load Whisper model '{sanitize_for_print(model_name_worker)}': {sanitize_for_print(str(e))}", file=sys.stderr, flush=True)
            WHISPER_MODEL_WORKER = "error"

def transcribe_chunk_worker(args_tuple):
    audio_chunk_np_worker, model_name_worker, download_root_worker, whisper_options_worker, chunk_start_sec_worker = args_tuple
    worker_pid = os.getpid()
    print(f"INFO [Worker PID {worker_pid}]: Task started for VAD chunk at {chunk_start_sec_worker:.2f}s.", flush=True)

    if WHISPER_MODEL_WORKER is None or WHISPER_MODEL_WORKER == "error":
        load_whisper_model_for_worker(model_name_worker, download_root_worker)

    if WHISPER_MODEL_WORKER is None or WHISPER_MODEL_WORKER == "error":
        print(f"ERROR [Worker PID {worker_pid}]: Whisper model not available for VAD chunk at {chunk_start_sec_worker:.2f}s.", file=sys.stderr, flush=True)
        return []

    processed_segments = []
    try:
        print(f"INFO [Worker PID {worker_pid}]: Transcribing VAD chunk at {chunk_start_sec_worker:.2f}s...", flush=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            whisper_options_worker["verbose"] = False
            result_from_chunk = WHISPER_MODEL_WORKER.transcribe(audio_chunk_np_worker, **whisper_options_worker)
        print(f"INFO [Worker PID {worker_pid}]: Transcription finished for VAD chunk at {chunk_start_sec_worker:.2f}s.", flush=True)

        segments_in_chunk = result_from_chunk.get("segments", [])
        for segment in segments_in_chunk:
            segment['start'] += chunk_start_sec_worker
            segment['end'] += chunk_start_sec_worker
            processed_segments.append(segment)
        print(f"INFO [Worker PID {worker_pid}]: Processed {len(processed_segments)} segments for VAD chunk at {chunk_start_sec_worker:.2f}s.", flush=True)
        return processed_segments
    except Exception as e:
        print(f"ERROR [Worker PID {worker_pid}]: Transcription failed for VAD chunk starting at {chunk_start_sec_worker:.2f}s: {sanitize_for_print(str(e))}", file=sys.stderr, flush=True)
        return []

def load_vad_model():
    global VAD_MODEL, VAD_UTILS
    if VAD_MODEL is None:
        vad_model_storage_location_info = ""
        try:
            current_file_dir = os.path.dirname(os.path.abspath(__file__))
            scripts_dir_level = os.path.dirname(current_file_dir)
            models_dir_for_hub_parent = os.path.join(scripts_dir_level, "models")
            
            os.makedirs(models_dir_for_hub_parent, exist_ok=True)
            
            torch.hub.set_dir(models_dir_for_hub_parent)
            
            vad_model_storage_location_info = os.path.join(models_dir_for_hub_parent, 'hub')
            print(f"INFO: Silero VAD models will be checked/stored in: {sanitize_for_print(vad_model_storage_location_info)}", flush=True)

            torch.set_num_threads(1)
            model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                          model='silero_vad',
                                          force_reload=False,
                                          trust_repo=True)
            VAD_MODEL = model
            VAD_UTILS = utils
            print("INFO: Silero VAD model loaded successfully.", flush=True)
        except Exception as e:
            detailed_error_msg = f"Attempted to use/create VAD model cache in: {vad_model_storage_location_info}" if vad_model_storage_location_info else "Path setup for VAD model cache failed."
            print(f"ERROR: Could not load Silero VAD model: {sanitize_for_print(str(e))}. {sanitize_for_print(detailed_error_msg)}. VAD will be disabled.", file=sys.stderr, flush=True)
            VAD_MODEL = "error"

def normalize_text_for_comparison(text: str) -> str:
    if not text: return ""
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'").replace("”", '"').replace("“", '"')
    punctuation_to_remove = "".join(c for c in string.punctuation if c not in ["'", "-"])
    translator = str.maketrans('', '', punctuation_to_remove)
    text = text.translate(translator)
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    return text

def load_audio_for_vad(audio_path: str, target_sr: int = 16000) -> Optional[Tuple[torch.Tensor, int]]:
    waveform = None; sr = 0
    if sf:
        try:
            data, sr = sf.read(audio_path, dtype='float32')
            waveform = torch.from_numpy(data)
            if waveform.ndim > 1 and waveform.shape[1] > 1 : waveform = torch.mean(waveform, dim=1)
            elif waveform.ndim > 1 and waveform.shape[1] == 1: waveform = waveform.squeeze(1)
        except Exception as e_sf:
            print(f"INFO: soundfile failed to load {sanitize_for_print(audio_path)}: {sanitize_for_print(str(e_sf))}. Attempting torchaudio.", flush=True)
            waveform = None
    if waveform is None and torchaudio:
        try:
            waveform_ta, sr_ta = torchaudio.load(audio_path)
            waveform = waveform_ta; sr = sr_ta
            if waveform.ndim > 1: waveform = torch.mean(waveform, dim=0)
        except Exception as e_ta:
            print(f"ERROR: Both soundfile and torchaudio failed to load {sanitize_for_print(audio_path)}. soundfile: (see above), torchaudio: {sanitize_for_print(str(e_ta))}", file=sys.stderr, flush=True)
            return None
    elif waveform is None and not torchaudio:
        print(f"ERROR: soundfile failed and torchaudio is not available to load {sanitize_for_print(audio_path)}", file=sys.stderr, flush=True)
        return None
    if sr != target_sr and torchaudio and hasattr(torchaudio, 'transforms') and hasattr(torchaudio.transforms, 'Resample'):
        transform = torchaudio.transforms.Resample(orig_freq=sr, new_freq=target_sr)
        waveform = transform(waveform); sr = target_sr
    elif sr != target_sr:
        print(f"WARNING: Audio SR is {sr} but target is {target_sr}. Resampling failed or torchaudio.transforms not available.", file=sys.stderr, flush=True)
        return None
    return waveform, sr

def get_speech_timestamps_from_vad(
    audio_waveform: torch.Tensor, audio_sr: int, vad_model: Callable, vad_utils_get_speech_ts: Callable,
    sampling_rate: int = 16000, vad_threshold: float = 0.5, min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 100, window_size_samples: int = 512, speech_pad_ms: int = 30
    ) -> List[Dict[str, float]]:
    try:
        if audio_sr != sampling_rate:
            print(f"ERROR: VAD input audio SR ({audio_sr}) does not match target SR ({sampling_rate}). This should have been handled by loader.", file=sys.stderr, flush=True)
            return []
        speech_timestamps = vad_utils_get_speech_ts(
            audio_waveform, vad_model, threshold=vad_threshold, sampling_rate=sampling_rate,
            min_speech_duration_ms=min_speech_duration_ms, min_silence_duration_ms=min_silence_duration_ms,
            window_size_samples=window_size_samples, speech_pad_ms=speech_pad_ms
        )
        return speech_timestamps
    except Exception as e:
        print(f"ERROR: VAD processing failed during speech timestamp detection: {sanitize_for_print(str(e))}", file=sys.stderr, flush=True)
        return []

def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("video", nargs="+", type=str, help="paths to video files to transcribe")
    parser.add_argument("--model", default="small", choices=whisper.available_models(), help="name of the Whisper model to use")
    parser.add_argument("--output_dir", "-o", type=str, default=".", help="directory to save the outputs")
    parser.add_argument("--output_srt", type=str2bool, default=False, help="whether to output the .srt file along with the video files")
    parser.add_argument("--srt_only", type=str2bool, default=False, help="only generate the .srt file and not create overlayed video")
    parser.add_argument("--verbose", type=str2bool, default=False, help="whether to print out progress messages from this script. Whisper's own verbose output is controlled separately by its transcribe method's verbose option.")
    parser.add_argument("--task", type=str, default="transcribe", choices=["transcribe", "translate"], help="whether to perform X->X speech recognition ('transcribe') or X->English translation ('translate')")
    parser.add_argument("--language", type=str, default="auto", choices=["auto","af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs","cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu","ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka","kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml","mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt","ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw","ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo","zh"], help="What is the origin language of the video? If unset, it is detected automatically.")
    parser.add_argument("--ffmpeg_executable_path", type=str, default="ffmpeg", help="Full path to the ffmpeg executable. Defaults to 'ffmpeg' (expected in PATH).")
    parser.add_argument("--model_download_root", type=str, default=None, help="Optional root directory for Whisper model cache. Whisper will create a 'whisper' subdir here.")
    parser.add_argument("--no_speech_threshold", type=float, default=0.6, help="Whisper's segment no_speech_prob threshold. Segments above this will be skipped. Range 0.0-1.0. Default is 0.6.")
    parser.add_argument("--merge_repetitive_segments", type=str2bool, default=True, help="Whether to merge consecutive subtitle segments if their text is identical. Default is True.")
    parser.add_argument("--use_vad", type=str2bool, default=True, help="Whether to use Silero VAD to pre-segment audio before sending to Whisper. Default is True.")
    parser.add_argument("--vad_threshold", type=float, default=0.5, help="VAD threshold for speech detection. Range 0.0-1.0. Higher is more sensitive to speech. Default is 0.5.")
    parser.add_argument("--min_speech_duration_ms", type=int, default=250, help="VAD: Minimum duration for a speech segment in milliseconds. Default is 250.")
    parser.add_argument("--min_silence_duration_ms", type=int, default=100, help="VAD: Minimum duration for a silence gap in milliseconds. Default is 100.")
    parser.add_argument("--num_workers", type=int, default=1, help="Number of CPU worker processes for transcribing VAD chunks. Default is 1 (no multiprocessing). Set to 0 to use os.cpu_count().")

    args_dict = parser.parse_args().__dict__
    video_files: List[str] = args_dict.pop("video")
    model_name: str = args_dict.pop("model")
    output_dir: str = args_dict.pop("output_dir")
    output_srt: bool = args_dict.pop("output_srt")
    srt_only: bool = args_dict.pop("srt_only")
    language: str = args_dict.pop("language")
    ffmpeg_exec_path: str = args_dict.pop("ffmpeg_executable_path")
    model_download_root_path: Optional[str] = args_dict.pop("model_download_root")
    no_speech_threshold_value: float = args_dict.pop("no_speech_threshold")
    merge_repetitions: bool = args_dict.pop("merge_repetitive_segments")
    use_vad_filter: bool = args_dict.pop("use_vad")
    num_workers_arg: int = args_dict.pop("num_workers")
    vad_parameters = {"vad_threshold": args_dict.pop("vad_threshold"), "min_speech_duration_ms": args_dict.pop("min_speech_duration_ms"), "min_silence_duration_ms": args_dict.pop("min_silence_duration_ms")}
    script_verbose_logging: bool = args_dict.pop("verbose")
    os.makedirs(output_dir, exist_ok=True)
    if use_vad_filter: load_vad_model()
    
    whisper_transcribe_options = args_dict.copy()
    
    if model_name.endswith(".en"):
        warnings.warn(f"{sanitize_for_print(model_name)} is an English-only model, forcing English detection.")
        whisper_transcribe_options["language"] = "en"
    elif language != "auto": whisper_transcribe_options["language"] = language
    
    main_whisper_model = whisper.load_model(model_name, download_root=model_download_root_path)
    audios = get_audio(video_files, ffmpeg_exec_path)
    actual_num_workers = max(1, os.cpu_count() or 1) if num_workers_arg == 0 else max(1, num_workers_arg)
    if script_verbose_logging: print(f"INFO: Using up to {actual_num_workers} worker(s) for VAD chunk transcription.", flush=True)
    subtitles = get_subtitles(
        audios, main_whisper_model, model_name, model_download_root_path,
        whisper_transcribe_options, output_srt or srt_only, output_dir,
        no_speech_threshold_value, merge_repetitions,
        use_vad_filter and VAD_MODEL not in [None, "error"],
        vad_parameters, actual_num_workers, script_verbose_logging
    )
    if srt_only: return
    for path, srt_path in subtitles.items():
        if not srt_path:
            print(f"Skipping video overlay for {sanitize_for_print(filename(path))} as no valid SRT was generated.", flush=True)
            continue
        out_path = os.path.join(output_dir, f"{filename(path)}.mp4")
        print(f"Adding subtitles to {sanitize_for_print(filename(path))}...")
        video = ffmpeg.input(path); audio = video.audio
        try:
            ffmpeg.concat(
                video.filter('subtitles', srt_path, force_style="OutlineColour=&H40000000,BorderStyle=3"), audio, v=1, a=1
            ).output(out_path).run(cmd=ffmpeg_exec_path, quiet=True, overwrite_output=True)
            print(f"Saved subtitled video to {sanitize_for_print(os.path.abspath(out_path))}.")
        except ffmpeg.Error as e:
            print(f"Error during FFmpeg processing for {sanitize_for_print(filename(path))}: {e.stderr.decode('utf8') if e.stderr else sanitize_for_print(str(e))}", file=sys.stderr, flush=True)
            print(f"Failed to add subtitles to {sanitize_for_print(filename(path))}. SRT file may still be available at: {sanitize_for_print(srt_path)}", file=sys.stderr, flush=True)

def get_audio(paths: List[str], ffmpeg_cmd: str = "ffmpeg") -> Dict[str, str]:
    temp_dir = tempfile.gettempdir(); audio_paths: Dict[str, str] = {}
    for path in paths:
        print(f"Extracting audio from {sanitize_for_print(filename(path))}...")
        output_path = os.path.join(temp_dir, f"{filename(path)}.wav")
        try:
            ffmpeg.input(path).output(output_path, acodec="pcm_s16le", ac=1, ar="16k").run(cmd=ffmpeg_cmd, quiet=True, overwrite_output=True)
            audio_paths[path] = output_path
        except ffmpeg.Error as e:
            print(f"Error extracting audio from {sanitize_for_print(filename(path))}: {e.stderr.decode('utf8') if e.stderr else sanitize_for_print(str(e))}", file=sys.stderr, flush=True)
            continue
    return audio_paths

def get_subtitles(
    audio_paths: Dict[str, str], main_whisper_model_obj: whisper.Whisper, model_name_for_worker: str,
    model_root_for_worker: Optional[str], whisper_options_base: Dict[str, Any], output_srt_flag: bool,
    output_dir_path: str, no_speech_thresh_val: float, merge_repetitive: bool, use_vad_processing: bool,
    vad_params: Dict[str, Any], num_workers_for_pool: int, script_verbose_flag: bool
) -> Dict[str, Optional[str]]:
    subtitles_path_map: Dict[str, Optional[str]] = {}; SAMPLING_RATE = 16000
    
    for original_video_path, current_audio_path in audio_paths.items():
        target_srt_path = os.path.join(output_dir_path if output_srt_flag else tempfile.gettempdir(), f"{filename(original_video_path)}.srt")
        print(f"Generating subtitles for {sanitize_for_print(filename(original_video_path))}... This might take a while.", flush=True)
        all_transcribed_segments: List[Dict[str, Any]] = []
        use_vad_for_this_file = False
        full_waveform_for_vad = None

        if use_vad_processing and VAD_MODEL and VAD_UTILS:
            if script_verbose_flag: print(f"INFO: Using Silero VAD for {sanitize_for_print(filename(original_video_path))}.", flush=True)
            (get_speech_timestamps_util, _, _, _, _) = VAD_UTILS
            loaded_audio_data = load_audio_for_vad(current_audio_path, SAMPLING_RATE)
            if loaded_audio_data:
                full_waveform_for_vad, sr_for_vad = loaded_audio_data
                use_vad_for_this_file = True
            else:
                print(f"ERROR: VAD audio load failed for {sanitize_for_print(filename(original_video_path))}. Skipping VAD for this file.", file=sys.stderr, flush=True)

            if use_vad_for_this_file and full_waveform_for_vad is not None:
                speech_ts_from_vad = get_speech_timestamps_from_vad(
                    full_waveform_for_vad, sr_for_vad, VAD_MODEL, get_speech_timestamps_util, SAMPLING_RATE,
                    vad_params["vad_threshold"], vad_params["min_speech_duration_ms"], vad_params["min_silence_duration_ms"]
                )
                if not speech_ts_from_vad:
                    if script_verbose_flag: print(f"INFO: VAD found no speech in {sanitize_for_print(filename(original_video_path))}.", flush=True)
                else:
                    if script_verbose_flag: print(f"INFO: VAD found {len(speech_ts_from_vad)} speech segments.", flush=True)
                    tasks_for_pool = []
                    for ts_chunk in speech_ts_from_vad:
                        cs_s, cs_e = ts_chunk['start'], ts_chunk['end']; c_start_sec = cs_s / SAMPLING_RATE
                        audio_chunk_np = full_waveform_for_vad[cs_s:cs_e].numpy().astype(np.float32)
                        if len(audio_chunk_np) < 0.05 * SAMPLING_RATE:
                            if script_verbose_flag: print(f"INFO: Skipping very short VAD chunk (pre-pool) at {c_start_sec:.2f}s", flush=True)
                            continue
                        worker_opts_for_pool = whisper_options_base.copy()
                        worker_opts_for_pool["verbose"] = False 
                        tasks_for_pool.append((audio_chunk_np, model_name_for_worker, model_root_for_worker, worker_opts_for_pool, c_start_sec))

                    if full_waveform_for_vad is not None:
                        del full_waveform_for_vad; full_waveform_for_vad = None
                        if torch.cuda.is_available(): torch.cuda.empty_cache()
                        gc.collect()

                    if tasks_for_pool:
                        if num_workers_for_pool > 1 and len(tasks_for_pool) > 1 :
                            if script_verbose_flag: print(f"INFO: Using multiprocessing pool ({num_workers_for_pool} workers) for {len(tasks_for_pool)} VAD tasks.", flush=True)
                            try:
                                ctx = multiprocessing.get_context('spawn')
                                with ctx.Pool(processes=num_workers_for_pool) as pool:
                                    results_from_pool = pool.map(transcribe_chunk_worker, tasks_for_pool)
                                if script_verbose_flag: print(f"INFO: Pool.map finished. Received {len(results_from_pool)} results.", flush=True)
                                for result_list in results_from_pool:
                                    all_transcribed_segments.extend(result_list)
                            except Exception as e_pool:
                                print(f"ERROR: Multiprocessing pool failed for {sanitize_for_print(filename(original_video_path))}: {sanitize_for_print(str(e_pool))}. Falling back to serial VAD processing for this file.", file=sys.stderr, flush=True)
                                all_transcribed_segments = [] 
                                use_vad_for_this_file = False 
                        else: 
                            if script_verbose_flag: print(f"INFO: Processing {len(tasks_for_pool)} VAD tasks serially for {sanitize_for_print(filename(original_video_path))}.", flush=True)
                            for i_task, task_args_serial in enumerate(tasks_for_pool):
                                audio_np_s, _, _, opts_s, start_s_s = task_args_serial
                                if script_verbose_flag: print(f"INFO: Serial VAD task {i_task+1}/{len(tasks_for_pool)} starting for chunk at {start_s_s:.2f}s", flush=True)
                                opts_s["verbose"] = False 
                                result_s = main_whisper_model_obj.transcribe(audio_np_s, **opts_s)
                                segs_s = result_s.get("segments", [])
                                for s_s_item in segs_s: s_s_item['start'] += start_s_s; s_s_item['end'] += start_s_s; all_transcribed_segments.append(s_s_item)
                                if script_verbose_flag: print(f"INFO: Serial VAD task {i_task+1}/{len(tasks_for_pool)} finished. Found {len(segs_s)} segments.", flush=True)
        
        if not use_vad_for_this_file: 
            if script_verbose_flag: print(f"INFO: VAD not used for {sanitize_for_print(filename(original_video_path))}. Transcribing full audio.", flush=True)
            
            current_whisper_opts = whisper_options_base.copy()
            current_whisper_opts["verbose"] = True if script_verbose_flag else False

            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    transcription_result = main_whisper_model_obj.transcribe(current_audio_path, **current_whisper_opts)
                all_transcribed_segments = transcription_result.get("segments", [])
            except UnicodeEncodeError:
                if script_verbose_flag:
                    print(f"INFO: Whisper's verbose output caused a UnicodeEncodeError for {sanitize_for_print(filename(original_video_path))}.", flush=True)
                    print(f"INFO: Retrying transcription for {sanitize_for_print(filename(original_video_path))} with Whisper's internal verbose output disabled...", flush=True)
                
                current_whisper_opts["verbose"] = False 
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        transcription_result = main_whisper_model_obj.transcribe(current_audio_path, **current_whisper_opts)
                    all_transcribed_segments = transcription_result.get("segments", [])
                except Exception as e_retry:
                    print(f"ERROR: Transcription failed for {sanitize_for_print(filename(original_video_path))} even after disabling verbose: {sanitize_for_print(str(e_retry))}", file=sys.stderr, flush=True)
                    all_transcribed_segments = []
            except Exception as e_initial:
                print(f"ERROR: Transcription failed for {sanitize_for_print(filename(original_video_path))}: {sanitize_for_print(str(e_initial))}", file=sys.stderr, flush=True)
                all_transcribed_segments = []
        
        speech_segments_after_silence_filter: List[Dict[str, Any]] = []
        if not all_transcribed_segments:
            if script_verbose_flag: print(f"INFO: No segments transcribed for '{sanitize_for_print(filename(original_video_path))}'.", flush=True)
        else:
            for segment in all_transcribed_segments:
                seg_no_speech_p = segment.get("no_speech_prob", 0.0)
                if seg_no_speech_p < no_speech_thresh_val: speech_segments_after_silence_filter.append(segment)
                else:
                    if script_verbose_flag:
                        txt_prev = segment.get('text', '').strip()
                        txt_prev_display = (txt_prev[:27] + "...") if len(txt_prev) > 30 else txt_prev
                        print(f"INFO: Skipping silent segment ({segment['start']:.2f}s-{segment['end']:.2f}s) for '{sanitize_for_print(filename(original_video_path))}' (prob: {seg_no_speech_p:.2f} >= {no_speech_thresh_val:.2f}). Text: '{sanitize_for_print(txt_prev_display)}'", flush=True)
        
        if not speech_segments_after_silence_filter:
            if script_verbose_flag and len(all_transcribed_segments) > 0 : 
                print(f"INFO: All segments for '{sanitize_for_print(filename(original_video_path))}' were filtered by no-speech threshold or transcription failed. No SRT generated.", flush=True)
            subtitles_path_map[original_video_path] = None 
            if os.path.exists(target_srt_path): 
                try: os.remove(target_srt_path)
                except OSError: pass
            continue 

        final_segments_to_write: List[Dict[str, Any]] = []
        if merge_repetitive and speech_segments_after_silence_filter:
            final_segments_to_write.append(dict(speech_segments_after_silence_filter[0])) 
            for i in range(1, len(speech_segments_after_silence_filter)):
                curr_seg = speech_segments_after_silence_filter[i]; last_add_seg = final_segments_to_write[-1] 
                curr_txt_norm = normalize_text_for_comparison(curr_seg.get('text', ''))
                prev_txt_norm = normalize_text_for_comparison(last_add_seg.get('text', ''))
                if curr_txt_norm == prev_txt_norm and curr_txt_norm != "":
                    last_add_seg['end'] = curr_seg['end'] 
                    if script_verbose_flag: 
                        text_content = curr_seg.get('text', '').strip()
                        print(f"INFO: Merged repetitive segment ({curr_seg['start']:.2f}s-{curr_seg['end']:.2f}s) for '{sanitize_for_print(filename(original_video_path))}'. Text: '{sanitize_for_print(text_content)}'", flush=True)
                else: final_segments_to_write.append(dict(curr_seg)) 
        elif speech_segments_after_silence_filter: final_segments_to_write = [dict(s) for s in speech_segments_after_silence_filter] 
        
        if not final_segments_to_write:
            if script_verbose_flag: print(f"INFO: No segments remaining for '{sanitize_for_print(filename(original_video_path))}' after all processing. No SRT.", flush=True)
            subtitles_path_map[original_video_path] = None
            if os.path.exists(target_srt_path):
                try: os.remove(target_srt_path)
                except OSError: pass
            continue
        with open(target_srt_path, "w", encoding="utf-8") as srt_file: write_srt(final_segments_to_write, file=srt_file)
        subtitles_path_map[original_video_path] = target_srt_path
    return subtitles_path_map

if __name__ == '__main__':
    if os.name == 'nt': 
        multiprocessing.freeze_support()
    main()