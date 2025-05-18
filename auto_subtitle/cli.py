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
from typing import Optional


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
                        help="whether to print out the progress and debug messages for this script's operations")

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

    args_dict = parser.parse_args().__dict__
    model_name: str = args_dict.pop("model")
    output_dir: str = args_dict.pop("output_dir")
    output_srt: bool = args_dict.pop("output_srt")
    srt_only: bool = args_dict.pop("srt_only")
    language: str = args_dict.pop("language")
    ffmpeg_exec_path: str = args_dict.pop("ffmpeg_executable_path")
    model_download_root_path: Optional[str] = args_dict.pop("model_download_root")
    
    no_speech_threshold_value: float = args_dict.pop("no_speech_threshold")
    # The 'verbose' argument from argparse is for Whisper's internal progress.
    # We'll use it also for our script's verbose logging.
    script_verbose_logging: bool = args_dict.get("verbose", False)


    os.makedirs(output_dir, exist_ok=True)

    # All remaining args in args_dict are intended for whisper.transcribe
    transcribe_options = args_dict 

    if model_name.endswith(".en"):
        warnings.warn(
            f"{model_name} is an English-only model, forcing English detection.")
        transcribe_options["language"] = "en"
    elif language != "auto":
        transcribe_options["language"] = language
    # If language is "auto", it's not explicitly set in transcribe_options,
    # allowing Whisper to perform auto-detection.


    model = whisper.load_model(model_name, download_root=model_download_root_path)
    audios = get_audio(transcribe_options.pop("video"), ffmpeg_exec_path) #.pop("video") from transcribe_options as it's not a whisper.transcribe arg
    
    subtitles = get_subtitles(
        audios, 
        output_srt or srt_only, 
        output_dir, 
        lambda audio_path: model.transcribe(audio_path, **transcribe_options),
        no_speech_threshold_value,
        script_verbose_logging
    )

    if srt_only:
        return

    for path, srt_path in subtitles.items():
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
            print(f"Failed to add subtitles to {filename(path)}. SRT file is available at: {srt_path}", file=sys.stderr, flush=True)


def get_audio(paths, ffmpeg_cmd="ffmpeg"):
    temp_dir = tempfile.gettempdir()
    audio_paths = {}

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
            # Decide if you want to skip this file or halt. Here, we'll skip.
            continue 
            
    return audio_paths


def get_subtitles(audio_paths: dict, output_srt: bool, output_dir: str, transcribe: callable, 
                  no_speech_thresh: float, script_verbose: bool):
    subtitles_path = {}

    for path, audio_path in audio_paths.items():
        srt_path = output_dir if output_srt else tempfile.gettempdir()
        srt_path = os.path.join(srt_path, f"{filename(path)}.srt")

        print(
            f"Generating subtitles for {filename(path)}... This might take a while."
        )

        warnings.filterwarnings("ignore")
        result = transcribe(audio_path)
        warnings.filterwarnings("default")

        all_segments = result.get("segments", [])
        speech_segments = []

        for segment in all_segments:
            segment_no_speech_prob = segment.get("no_speech_prob", 0.0)
            if segment_no_speech_prob < no_speech_thresh:
                speech_segments.append(segment)
            else:
                if script_verbose:
                    text_preview = segment.get('text', '').strip()
                    if len(text_preview) > 30: text_preview = text_preview[:27] + "..."
                    print(f"INFO: Skipping segment ({segment['start']:.2f}s-{segment['end']:.2f}s) for '{filename(path)}' due to no_speech_prob: {segment_no_speech_prob:.2f} >= threshold {no_speech_thresh:.2f}. Text: '{text_preview}'", flush=True)
        
        if not speech_segments and all_segments:
             if script_verbose:
                print(f"INFO: All segments for '{filename(path)}' were filtered out by no-speech threshold. Original subtitle would have content.", flush=True)
        elif not all_segments:
            if script_verbose:
                print(f"INFO: No segments transcribed for '{filename(path)}' by Whisper.", flush=True)


        with open(srt_path, "w", encoding="utf-8") as srt:
            write_srt(speech_segments, file=srt)

        subtitles_path[path] = srt_path

    return subtitles_path


if __name__ == '__main__':
    main()