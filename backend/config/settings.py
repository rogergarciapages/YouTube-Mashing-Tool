import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
    DEFAULT_FONT: str = "Arial"
    FONT_DIR: str = "fonts"
    
    # Video Formats
    VIDEO_FORMATS = {
        "youtube": {"width": 1920, "height": 1080, "aspect": "16:9"},
        "shorts": {"width": 1080, "height": 1920, "aspect": "9:16"},
        "instagram": {"width": 1080, "height": 1080, "aspect": "1:1"}
    }
    
    # FFmpeg Configuration
    FFMPEG_PATH: str = "ffmpeg"  # Assumes ffmpeg is in PATH
    
    # Processing Configuration
    MAX_PROCESSING_TIME: int = 300  # 5 minutes
    CLEANUP_TEMP_FILES: bool = True

def get_settings() -> Settings:
    return Settings()

# Global settings instance
settings = get_settings()
