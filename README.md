# Auto Subtitle GUI (With FFmpeg and packages installed)

This application provides a user-friendly graphical interface for automatically generating high-quality SRT subtitle files from video files. It leverages the power of OpenAI's cutting-edge Whisper model for transcription and translation, and includes all necessary components (Python environment, packages, and FFmpeg) for portability and ease of use.

## Overview

The Auto Subtitle GUI is designed to make the process of subtitling videos straightforward. Unlike traditional setups that might require installing Python, specific libraries, and FFmpeg system-wide and managing complex PATH configurations, this portable version bundles everything you need.

You simply unzip the package, run a setup script once, and then launch the GUI. The application automatically handles the complexities of calling the Whisper model via the `auto-subtitle` script and using FFmpeg for audio extraction, ensuring a smooth workflow even without prior technical setup.

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

## Credits

*   This GUI application is built upon the excellent `auto-subtitle` command-line script, which handles the core integration with Whisper and FFmpeg. Many thanks to the original `auto-subtitle` project and its contributors: **[https://github.com/m1guelpf/auto-subtitle](https://github.com/m1guelpf/auto-subtitle)**
*   Audio processing relies on the powerful FFmpeg multimedia framework. A portable distribution of FFmpeg is included in this package for your convenience.

## Setup and Running Instructions

Follow these simple steps to get the application running:

1.  **Download and Unzip:**
    *   Download the application package (a zip file containing the `Python311` folder, etc.) from the provided Google Drive link: **[https://drive.google.com/drive/folders/1MPJKU_Aru1hTJNiYQSmFHZMtCH46lole?usp=drive_link](https://drive.google.com/drive/folders/1MPJKU_Aru1hTJNiYQSmFHZMtCH46lole?usp=drive_link)** (Unzip format for inspection) **[https://drive.google.com/file/d/1N82xwGCTnaywauU1VKy0iHFICwA45P6i/view?usp=drive_link]** (Zipped format for download)
    *   Unzip the downloaded file to a desired location on your computer. Make sure you have enough disk space (the package itself, downloaded models, and output SRTs will consume space).

2.  **Initialize/Update Virtual Environment:**
    *   Navigate into the main `Python311` folder that was created when you unzipped the package.
    *   Locate the batch file named `createNewEnv.bat`.
    *   **Double-click** this batch file.
    *   A command prompt window will open and run. This script will ensure it updates the virtual environment to the correct directory and ensure all necessary Python packages (including `auto-subtitle`, `whisper`, `torch`, `torchaudio`, `numba`, `tqdm`, and `ffmpeg-python`) are correctly installed within this environment. **Note:** `torch` is installed with CPU support, making it broadly compatible with most Windows computers without requiring a specific graphics card.
    *   **Wait for the script to finish.** The window will likely indicate completion or close automatically when done. This step requires an internet connection to download Python packages.

3.  **Run the Application:**
    *   Navigate to the `App_AutoSub\Scripts` folder located inside the `Python311` folder.
    *   Locate the batch file named `run.bat`.
    *   **Double-click** this batch file.
    *   A command prompt window will briefly appear (it's used to activate the environment and launch the GUI), and then the "Auto Subtitle GUI (Portable FFmpeg)" application window will open.

## Using the GUI

*   **Selecting Files:** Click "Select Video File(s)" to browse and add videos to the list.
*   **Choosing Options:** Select your desired Whisper model and the audio language. Choose the output folder for the SRT files.
*   **Starting Processing:** Click "Start Processing". The log area will show progress.
*   **Monitoring Progress:** The GUI's log window provides detailed output. If you ran `run.bat` from an existing command prompt, you will also see the progress printed there.

## Additional Notes

*   **CPU Performance:** As `torch` is configured for CPU-only processing, performance will be entirely dependent on your computer's processor speed. Transcription can be quite CPU-intensive, especially with larger models.
*   **GPU (Optional):** This package does *not* include the necessary CUDA-enabled `torch` binaries or require a GPU. If you need faster performance and have an NVIDIA GPU, you would need to manually install a CUDA-compatible version of `torch` into the virtual environment after running `createNewEnv.bat`, following the instructions on the PyTorch website.
*   **Model Downloads:** The `small.pt` model is included. If you use a different model size for the first time, it will be downloaded automatically by the `whisper` library. Download size varies by model (e.g., `medium` is several GB, `large-v3` is larger). Ensure you have sufficient disk space and an internet connection.
*   **Output Files:** The generated `.srt` files will be named the same as the input video file (e.g., `myvideo.mp4` will produce `myvideo.srt`) and placed in the specified "SRT Output Dir".
