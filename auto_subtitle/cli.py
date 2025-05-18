import os
import sys
print(f"DEBUG [cli.py]: sys.executable: {sys.executable}", flush=True)
print(f"DEBUG [cli.py]: Current Working Directory: {os.getcwd()}", flush=True)
print(f"DEBUG [cli.py]: sys.path: {sys.path}", flush=True)

import ffmpeg
print(f"DEBUG [cli.py]: ffmpeg module successfully imported.", flush=True)
print(f"DEBUG [cli.py]: ffmpeg module location: {ffmpeg.__file__}", flush=True)
print(f"DEBUG [cli.py]: ffmpeg module type: {type(ffmpeg)}", flush=True)
print(f"DEBUG [cli.py]: Does ffmpeg module have 'input' attribute? {hasattr(ffmpeg, 'input')}", flush=True)

import whisper
import argparse
import warnings
import tempfile
from .utils import filename, str2bool, write_srt
from typing import Optional, List, Dict, Any


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("video", nargs="+", type=str,
                        help="paths to video files to transcribe")
    parser.add_argument("--model", default="small",
                        choices=whisper.available_models(), help="name of the Whisper model to use")
    parser.add_argument("--output_dir", "-o", type=str,
                        default=".", help="directory to save the outputs")
    parser.add_argument("--output_srt", type=str2bool, default=False,
                        help="whether to output the .srt file along with the video files")
    parser.add_argument("--srt_only", type=str2bool, default=False,
                        help="only generate the .srt file and not create overlayed video")
    parser.add_argument("--verbose", type=str2bool, default=False,
                        help="whether to print out the progress and debug messages for this script's operations and Whisper's transcription")

    parser.add_argument("--task", type=str, default="transcribe", choices=[
                        "transcribe", "translate"], help="whether to perform X->X speech recognition ('transcribe') or X->English translation ('translate')")
    parser.add_argument("--language", type=str, default="auto", choices=["auto","af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs","cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu","ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka","kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml","mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt","ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw","ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo","zh"],
    help="What is the origin language of the video? If unset, it is detected automatically.")

    parser.add_argument("--ffmpeg_executable_path", type=str, default="ffmpeg",
                        help="Full path to the ffmpeg executable. Defaults to 'ffmpeg' (expected in PATH).")

    parser.add_argument("--model_download_root", type=str, default=None,
                        help="Optional root directory for Whisper model cache. Whisper will create a 'whisper' subdir here.")

    parser.add_argument("--no_speech_threshold", type=float, default=0.6,
                        help="Threshold for no speech probability. Segments with no_speech_prob above this value will be skipped. Range 0.0-1.0. Default is 0.6.")
    
    parser.add_argument("--merge_repetitive_segments", type=str2bool, default=True,
                        help="Whether to merge consecutive subtitle segments if their text is identical. Default is True.")


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
    
    script_verbose_logging: bool = args_dict.get("verbose", False) 

    os.makedirs(output_dir, exist_ok=True)

    transcribe_options = args_dict 

    if model_name.endswith(".en"):
        warnings.warn(
            f"{model_name} is an English-only model, forcing English detection.")
        transcribe_options["language"] = "en"
    elif language != "auto": 
        transcribe_options["language"] = language


    model = whisper.load_model(model_name, download_root=model_download_root_path)
    audios = get_audio(video_files, ffmpeg_exec_path)
    
    subtitles = get_subtitles(
        audios, 
        output_srt or srt_only, 
        output_dir, 
        lambda audio_path: model.transcribe(audio_path, **transcribe_options),
        no_speech_threshold_value,
        merge_repetitions,
        script_verbose_logging
    )

    if srt_only:
        return

    for path, srt_path in subtitles.items():
        if not srt_path: 
            print(f"Skipping video overlay for {filename(path)} as no valid SRT was generated.", flush=True)
            continue
            
        out_path = os.path.join(output_dir, f"{filename(path)}.mp4")

        print(f"Adding subtitles to {filename(path)}...")

        video = ffmpeg.input(path)
        audio = video.audio

        try:
            ffmpeg.concat(
                video.filter('subtitles', srt_path, force_style="OutlineColour=&H40000000,BorderStyle=3"), audio, v=1, a=1
            ).output(out_path).run(cmd=ffmpeg_exec_path, quiet=not script_verbose_logging, overwrite_output=True)
            print(f"Saved subtitled video to {os.path.abspath(out_path)}.")
        except ffmpeg.Error as e:
            print(f"Error during FFmpeg processing for {filename(path)}: {e.stderr.decode('utf8') if e.stderr else str(e)}", file=sys.stderr, flush=True)
            print(f"Failed to add subtitles to {filename(path)}. SRT file may still be available at: {srt_path}", file=sys.stderr, flush=True)


def get_audio(paths: List[str], ffmpeg_cmd: str = "ffmpeg") -> Dict[str, str]:
    temp_dir = tempfile.gettempdir()
    audio_paths: Dict[str, str] = {}

    for path in paths:
        print(f"Extracting audio from {filename(path)}...")
        output_path = os.path.join(temp_dir, f"{filename(path)}.wav")

        try:
            ffmpeg.input(path).output(
                output_path,
                acodec="pcm_s16le", ac=1, ar="16k" 
            ).run(cmd=ffmpeg_cmd, quiet=True, overwrite_output=True)
            audio_paths[path] = output_path
        except ffmpeg.Error as e:
            print(f"Error extracting audio from {filename(path)}: {e.stderr.decode('utf8') if e.stderr else str(e)}", file=sys.stderr, flush=True)
            continue 
            
    return audio_paths


def get_subtitles(
    audio_paths: Dict[str, str], 
    output_srt_flag: bool, 
    output_dir_path: str, 
    transcribe_func: callable, 
    no_speech_thresh_val: float,
    merge_repetitive: bool,
    script_verbose_flag: bool
) -> Dict[str, Optional[str]]:
    
    subtitles_path_map: Dict[str, Optional[str]] = {}

    for original_video_path, current_audio_path in audio_paths.items():
        target_srt_path = output_dir_path if output_srt_flag else tempfile.gettempdir()
        target_srt_path = os.path.join(target_srt_path, f"{filename(original_video_path)}.srt")

        print(
            f"Generating subtitles for {filename(original_video_path)}... This might take a while."
        , flush=True)

        warnings.filterwarnings("ignore")
        transcription_result = transcribe_func(current_audio_path)
        warnings.filterwarnings("default")

        all_transcribed_segments: List[Dict[str, Any]] = transcription_result.get("segments", [])
        
        speech_segments_after_silence_filter: List[Dict[str, Any]] = []
        if not all_transcribed_segments:
            if script_verbose_flag:
                print(f"INFO: No segments transcribed by Whisper for '{filename(original_video_path)}'.", flush=True)
        else:
            for segment in all_transcribed_segments:
                segment_no_speech_prob = segment.get("no_speech_prob", 0.0)
                if segment_no_speech_prob < no_speech_thresh_val:
                    speech_segments_after_silence_filter.append(segment)
                else:
                    if script_verbose_flag:
                        text_preview = segment.get('text', '').strip()
                        if len(text_preview) > 30: text_preview = text_preview[:27] + "..."
                        print(f"INFO: Skipping silent segment ({segment['start']:.2f}s-{segment['end']:.2f}s) for '{filename(original_video_path)}' (no_speech_prob: {segment_no_speech_prob:.2f} >= {no_speech_thresh_val:.2f}). Text: '{text_preview}'", flush=True)
        
        if not speech_segments_after_silence_filter:
            if script_verbose_flag and all_transcribed_segments : 
                print(f"INFO: All segments for '{filename(original_video_path)}' were filtered out by no-speech threshold. No SRT will be generated.", flush=True)
            subtitles_path_map[original_video_path] = None 
            if os.path.exists(target_srt_path): 
                try: os.remove(target_srt_path)
                except OSError: pass
            continue 

        final_segments_to_write: List[Dict[str, Any]] = []
        if merge_repetitive and speech_segments_after_silence_filter:
            final_segments_to_write.append(dict(speech_segments_after_silence_filter[0])) 

            for i in range(1, len(speech_segments_after_silence_filter)):
                current_segment = speech_segments_after_silence_filter[i]
                last_added_segment = final_segments_to_write[-1] 

                current_text = current_segment.get('text', '').strip().lower()
                previous_text = last_added_segment.get('text', '').strip().lower()

                if current_text == previous_text:
                    last_added_segment['end'] = current_segment['end'] 
                    
                    if script_verbose_flag:
                        print(f"INFO: Merged repetitive segment ({current_segment['start']:.2f}s-{current_segment['end']:.2f}s) into previous for '{filename(original_video_path)}'. Text: '{current_segment.get('text', '').strip()}'", flush=True)
                else:
                    final_segments_to_write.append(dict(current_segment)) 
        elif speech_segments_after_silence_filter: 
            final_segments_to_write = [dict(s) for s in speech_segments_after_silence_filter] 
        else: 
            pass 

        if not final_segments_to_write:
            if script_verbose_flag:
                 print(f"INFO: No segments remaining for '{filename(original_video_path)}' after all processing. No SRT will be generated.", flush=True)
            subtitles_path_map[original_video_path] = None
            if os.path.exists(target_srt_path):
                try: os.remove(target_srt_path)
                except OSError: pass
            continue

        with open(target_srt_path, "w", encoding="utf-8") as srt_file:
            write_srt(final_segments_to_write, file=srt_file)
        
        subtitles_path_map[original_video_path] = target_srt_path

    return subtitles_path_map


if __name__ == '__main__':
    main()