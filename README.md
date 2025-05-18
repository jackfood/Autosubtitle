# Subtitles Generation (SRT) for Videos (Whisper-based)
## Fully Portable, Offline, running on CPU
V1.06 (With FFmpeg and packages installed)

This application provides a user-friendly graphical interface for automatically generating high-quality SRT subtitle files from video files. It leverages the power of cutting-edge Whisper model for transcription and translation, and includes all necessary components (Python environment, packages, and FFmpeg) for portability and ease of use.

## Overview

The Subtitles Generation GUI is a python-based, designed to make the process of subtitling videos straightforward. Unlike traditional setups that might require installing Python, specific libraries, and FFmpeg system-wide and managing complex PATH configurations, this portable version bundles everything you need. You can just bring it to your office or any workstations where internet is not available / restricted. Transcribe your meetings recording or audios with few-clicks.

You simply unzip the package, run a setup script once, and then launch the GUI. The application automatically handles the complexities of calling the Whisper model via the `auto-subtitle` script and using FFmpeg for audio extraction, ensuring a smooth workflow even without prior technical setup.

## Setup and Running Instructions

Follow these simple steps to get the application running:

1.  **Download and Unzip:**
    *   Download the application package (a zip file containing the `Python311` folder, etc.) from the provided Google Drive link: **https://drive.google.com/file/d/13Wb7Nl4ZfD_ypKmlCl_nPF20JLcr2Ano/view?usp=drive_link** (Zipped Version) **https://drive.google.com/drive/folders/1MPJKU_Aru1hTJNiYQSmFHZMtCH46lole?usp=drive_link** (Unzipped Version for viewing and inspection)
    *   Unzip the downloaded file to a desired location on your computer. Make sure you have enough disk space (the package itself, downloaded models, and output SRTs will consume space).

2.  **Initialize/Update Virtual Environment:**
    *   Navigate into the main `Python311` folder that was created when you unzipped the package.
    *   Locate the batch file named `createNewEnv.bat`.
    *   **Double-click** this batch file.
    *   A command prompt window will open and run. This script will ensure it updates the virtual environment to the correct directory.
    *   **Wait for the script to finish.** The window bat will close automatically when done.

3.  **Run the Application:**
    *   Navigate to the `App_AutoSub\Scripts` folder located inside the `Python311` folder.
    *   Locate the batch file named `run.bat`.
    *   **Double-click** this batch file.
    *   A command prompt window will briefly appear, then the "Auto Subtitle GUI (Portable FFmpeg)" application window will open.
    *   If you select other models size (except small), internet connection is **required**.

## Using the GUI

*   **Select Files:** Use "Select Video File(s)" to add single/multiple videos or *batch* - folders containing videos. "Clear List" removes them.
*   **Choose Options:**
    *   Select the **Model** and **Language**.
    *   Adjust **No Speech Threshold**.
    *   Toggle **Merge Repetitive Segments**.
    *   Enable **Use Voice Activity Detection (VAD)** for VAD-specific settings (**VAD Threshold**, **Min Speech**, **Min Silence**, and **CPU Workers** for parallel processing).
    *   Set the **SRT Output Dir**.
*   **Start Processing:** Click "Start Processing".
*   **Monitor Progress:** View progress and messages in the "Log Output" area within the GUI or in the command prompt where you launched the application.

## Model Downloading and Storage

This application utilizes the Whisper model for speech-to-text transcription. The first time you run the application and select a model other than the pre-provided `small.pt`, it will need to download the model weights from the internet.

### Internet Connection Requirement

An internet connection is **required** for the **initial** download of any Whisper model you choose, *except* for the `small.pt` model if it is already present in the designated model cache directory.

### Model Cache Location

To ensure portability and keep the model files within your application's structure, the application is configured to store the downloaded Whisper models in a specific location relative to the script's directory.

The model cache directory is set to:

`[Your App_AutoSub Directory]/Scripts/models`

When you select a model (e.g., "base", "medium", "large") for the first time, Whisper will automatically download the necessary files into this `models` directory. Subsequent uses of the same model will load the weights from this local 'models' cache, eliminating the need for further downloads.

### Provided `small.pt` Model

For convenience, a `small.pt` model file is expected to be included with the application distribution. If this file is placed in the `[Your App_AutoSub Directory]/Scripts/models` directory, selecting the "small" model will not require an internet connection for the initial load, as the model will be loaded directly from the provided file.

If you choose a different model (e.g., "base", "medium"), it will be downloaded to the same `models` directory.

## Key Features

*   **Intuitive GUI:** A simple and clear interface for selecting files, choosing options, and monitoring progress.
*   **Completely Portable:** The package includes a dedicated Python environment, pre-installed libraries, and a portable FFmpeg build. No system-level installations or modifications are necessary.
*   **Self-Contained Environment:** Avoids conflicts with your system's Python or other installed software. Everything runs within the provided `Python311` folder.
*   **Integrated FFmpeg:** A full, portable distribution of FFmpeg is included. This is essential for extracting audio from your video files before transcription.
*   **Whisper Integration:** Utilizes the powerful Whisper model for highly accurate speech-to-text transcription (and translation if the underlying `auto-subtitle` script supports it via command-line arguments - note: this GUI is configured for transcription with language selection).
*   **Model Selection:** Allows you to choose from various Whisper model sizes to balance speed, accuracy, and resource usage.
*   **Intelligent Model Handling:** The `small.pt` model file is conveniently included in the distribution. Other models you select (like "medium" or "large") will be automatically downloaded by Whisper to its default cache location (typically within the application's `Scripts` folder) the first time they are required, simplifying setup for different model preferences.
*   **Language Detection & Selection:** Choose to auto-detect the language or specify it for potentially faster and more accurate results.
*   **Direct SRT Output:** Generates standard `.srt` subtitle files compatible with most video players and editing software.
*   **Real-time Logging:** View detailed processing status and progress updates within the GUI's log area and, if launched from a terminal, directly in the console.

## Additional Notes

*   **CPU Performance:** As `torch` is configured for CPU-only processing, performance will be entirely dependent on your computer's processor speed. Transcription can be quite CPU-intensive, especially with larger models.
*   **GPU (Optional):** This package does *not* include the necessary CUDA-enabled `torch` binaries or require a GPU. If you need faster performance and have an NVIDIA GPU, you would need to manually install a CUDA-compatible version of `torch` into the virtual environment after running `createNewEnv.bat`, following the instructions on the PyTorch website.
*   **Model Downloads:** The `small.pt` model is included. If you use a different model size for the first time, it will be downloaded automatically by the `whisper` library. Download size varies by model (e.g., `medium` is several GB, `large-v3` is larger). Ensure you have sufficient disk space and an internet connection.
*   **Output Files:** The generated `.srt` files will be named the same as the input video file (e.g., `myvideo.mp4` will produce `myvideo.srt`). You can select the output location of the generated `srt`.

## Updates Log
*   **V1.02** Added - Silent Thresholds options, merge duplicate subtitle along same segment
*   **V1.05**
-- Improved Voice Activity Detection (VAD) Control: Enhanced the Voice Activity Detection feature for more flexible processing.
-- Multi-core Support for VAD Chunks: When VAD is enabled, the application now utilizes multiple CPU cores to transcribe speech segments in parallel, significantly speeding up processing on multi-core systems.
-- CPU Workers Option: Added a "CPU Workers (VAD Chunks)" option allowing users to specify the number of CPU cores to use for VAD-based transcription. Set to 0 for automatic detection (uses all available cores), 1 for serial processing, or a specific number up to your system's core count.
-- Dynamic UI: VAD-specific options (VAD Threshold, Min Speech, Min Silence, and CPU Workers) are now automatically shown when "Use Voice Activity Detection (VAD)" is checked and hidden when it's unchecked, simplifying the interface.
-- Enhanced Logging: Added more detailed logging for VAD processing when using multiple workers, providing better visibility into the progress of individual transcription tasks.
*   **V1.06** Increased transcription stability by implementing a fallback mechanism for console character encoding issues during transcription by automatically disabling detailed progress output and replaced with a progress bar if an issue is detected.

## Credits and Used Libraries

This project is heavily influenced by and built upon the excellent **auto-subtitle** command-line script developed by m1guelpf. Many thanks to the original auto-subtitle project and its contributors for providing the core logic and integration with Whisper and FFmpeg.

*   **auto-subtitle command-line script:**
    *   The foundational command-line tool that this GUI wraps around.
    *   Credit: m1guelpf and contributors (https://github.com/m1guelpf/auto-subtitle)
    *   Role: Provides the core script for interacting with Whisper, VAD, and FFmpeg.

I extend my sincere thanks to the developers and communities behind the following key packages:

*   **OpenAI Whisper:**
    *   The core of the transcription functionality is powered by OpenAI's state-of-the-art Whisper model.
    *   Credit: OpenAI (https://github.com/openai/whisper)
    *   Role: Performs the heavy lifting of speech-to-text conversion.

*   **Silero VAD:**
    *   For Voice Activity Detection (VAD), which helps segment audio into speech and non-speech parts before transcription, we use the Silero VAD model.
    *   Credit: Silero Team (https://github.com/snakers4/silero-vad)
    *   Role: Detects speech segments in audio to optimize transcription, especially when using multiple CPU workers.

*   **FFmpeg:**
    *   Essential for extracting audio streams from various video formats and for embedding the generated subtitles back into the video files (if that option is used).
    *   Credit: The FFmpeg team and contributors (https://ffmpeg.org/)
    *   Role: Handles all underlying audio and video stream manipulation. This application uses a portable FFmpeg binary.

*   **PyTorch:**
    *   Both OpenAI Whisper and Silero VAD are deep learning models that rely on the PyTorch framework for their execution.
    *   Credit: PyTorch Team (https://pytorch.org/)
    *   Role: Provides the foundation for running the neural network models.

*   **NumPy:**
    *   A fundamental package for numerical computation in Python, widely used by PyTorch and other scientific libraries.
    *   Credit: The NumPy community (https://numpy.org/)
    *   Role: Provides efficient array operations used in data handling for the models.

*   **soundfile & torchaudio:**
    *   These libraries are used by the VAD functionality for robust loading and handling of audio files.
    *   Credit: soundfile (https://github.com/bastibe/python-soundfile), torchaudio (https://github.com/pytorch/audio)
    *   Role: Facilitate reading and processing audio data for VAD analysis.

*   **Python `tkinter`:**
    *   The graphical user interface itself is built using Python's standard `tkinter` library and its themed widget extension `ttk`.
    *   Credit: Python core development team.
    *   Role: Creates the application window, buttons, inputs, and log display.
