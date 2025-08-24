import os
import subprocess
import logging
from typing import Tuple, Optional
from config.settings import settings

logger = logging.getLogger(__name__)

class VideoUtils:
    def __init__(self):
        self.ffmpeg_path = settings.FFMPEG_PATH
    
    def check_ffmpeg_availability(self) -> bool:
        """
        Check if FFmpeg is available in the system
        """
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False
    
    def get_video_info(self, file_path: str) -> Optional[dict]:
        """
        Get video information using FFmpeg
        """
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", file_path,
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Parse FFmpeg output for video information
            output = result.stderr  # FFmpeg outputs info to stderr
            
            info = {}
            
            # Extract duration
            if "Duration:" in output:
                duration_line = [line for line in output.split('\n') if "Duration:" in line][0]
                duration_str = duration_line.split("Duration:")[1].split(",")[0].strip()
                info['duration'] = self._parse_duration(duration_str)
            
            # Extract resolution
            if "Video:" in output:
                video_line = [line for line in output.split('\n') if "Video:" in line][0]
                if "x" in video_line:
                    resolution_part = video_line.split("Video:")[1].split()[0]
                    if "x" in resolution_part:
                        width, height = resolution_part.split("x")
                        info['width'] = int(width)
                        info['height'] = int(height)
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
    
    def _parse_duration(self, duration_str: str) -> float:
        """
        Parse FFmpeg duration string to seconds
        Format: HH:MM:SS.microseconds
        """
        try:
            parts = duration_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            
            total_seconds = hours * 3600 + minutes * 60 + seconds
            return total_seconds
        except (ValueError, IndexError):
            return 0.0
    
    def validate_video_file(self, file_path: str) -> bool:
        """
        Validate if a video file is valid and readable
        """
        if not os.path.exists(file_path):
            return False
        
        try:
            # Try to get video info
            info = self.get_video_info(file_path)
            return info is not None and info.get('duration', 0) > 0
        except Exception:
            return False
    
    def get_supported_formats(self) -> dict:
        """
        Get supported video output formats
        """
        return settings.VIDEO_FORMATS
    
    def calculate_aspect_ratio(self, width: int, height: int) -> str:
        """
        Calculate aspect ratio from dimensions
        """
        def gcd(a, b):
            while b:
                a, b = b, a % b
            return a
        
        divisor = gcd(width, height)
        w = width // divisor
        h = height // divisor
        
        return f"{w}:{h}"
    
    def estimate_processing_time(self, num_clips: int, total_duration: float) -> int:
        """
        Estimate processing time in seconds
        """
        # Rough estimation: 2 seconds per clip + 1 second per second of video
        base_time = num_clips * 2
        video_time = total_duration * 1
        return int(base_time + video_time)
    
    def cleanup_old_files(self, directory: str, max_age_hours: int = 24):
        """
        Clean up old temporary files
        """
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > max_age_seconds:
                        os.remove(file_path)
                        logger.debug(f"Cleaned up old file: {filename}")
                        
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
    
    def get_file_size_mb(self, file_path: str) -> float:
        """
        Get file size in megabytes
        """
        try:
            size_bytes = os.path.getsize(file_path)
            return size_bytes / (1024 * 1024)
        except OSError:
            return 0.0
