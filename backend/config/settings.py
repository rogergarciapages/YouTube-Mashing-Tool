import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def _get_default_ffmpeg_path() -> str:
    """
    Auto-detect FFmpeg path based on common installation locations
    """
    import platform
    import subprocess
    
    # Common FFmpeg installation paths
    common_paths = []
    
    if platform.system() == "Windows":
        # Windows common paths
        common_paths = [
            "C:\\ffmpeg\\bin\\ffmpeg.exe",
            "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
            "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
            os.path.expanduser("~\\ffmpeg\\bin\\ffmpeg.exe"),
            "ffmpeg.exe"  # If in current directory
        ]
    else:
        # Unix-like systems
        common_paths = [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",  # macOS Homebrew
            "ffmpeg"  # If in PATH
        ]
    
    # Check if any of the common paths exist
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # If no common path found, try to run 'ffmpeg -version' to check if it's in PATH
    try:
        result = subprocess.run(["ffmpeg", "-version"], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return "ffmpeg"  # It's in PATH
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Default fallback
    return "ffmpeg"

class Settings:
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "YouTube Clip Compilation Tool"
    
    # Google AI Configuration
    GOOGLE_AI_API_KEY: Optional[str] = os.getenv("GOOGLE_AI_API_KEY")
    
    # Video Processing Configuration
    CLIP_DURATION: int = 3  # seconds
    MAX_CLIPS: int = 20
    TEMP_DIR: str = "videos/temp"
    OUTPUT_DIR: str = "videos/output"
    
    # Font Configuration
    DEFAULT_FONT: str = "KOMIKAX_.ttf"  # Mr Beast's Komika Axis font
    FONT_DIR: str = "fonts"
    
    # Video Formats
    VIDEO_FORMATS = {
        "youtube": {"width": 1920, "height": 1080, "aspect": "16:9"},
        "shorts": {"width": 1080, "height": 1920, "aspect": "9:16"},
        "instagram": {"width": 1080, "height": 1080, "aspect": "1:1"}
    }
    
    # FFmpeg Configuration
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", _get_default_ffmpeg_path())  # Auto-detect or use env var
    
    # Processing Configuration
    MAX_PROCESSING_TIME: int = 300  # 5 minutes
    CLEANUP_TEMP_FILES: bool = True
    DOWNLOAD_RETRIES: int = 3
    
    # Quality Configuration
    FFMPEG_PRESET: str = "medium"  # Balance between speed and compression
    FFMPEG_CRF: int = 20           # Quality (lower is better, 18-28 is standard)
    
    # Subtitle Configuration
    SUBTITLE_WORD_DURATION: float = 0.5  # Seconds per word
    SUBTITLE_FONT_SIZE: int = 30         # Smaller font size (approx 60% smaller than 96)
    SUBTITLE_Y_POS: float = 0.8          # 80% down the screen

def get_settings() -> Settings:
    return Settings()

# Global settings instance
settings = get_settings()
