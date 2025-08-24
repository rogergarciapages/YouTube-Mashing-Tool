import os
import subprocess
import logging
import yt_dlp
import google.generativeai as genai
from typing import List, Dict, Optional
import tempfile
import shutil
from pathlib import Path
import json
import time

from models.schemas import VideoRequest, ClipRequest, ProcessingStatus, VideoFormat
from config.settings import settings
from utils.ai_client import AIClient
from utils.video_utils import VideoUtils

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        self.ai_client = AIClient()
        self.video_utils = VideoUtils()
        self.tasks: Dict[str, ProcessingStatus] = {}
        
        # Ensure directories exist
        os.makedirs(settings.TEMP_DIR, exist_ok=True)
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        os.makedirs(settings.FONT_DIR, exist_ok=True)
    
    def process_video_request(self, request: VideoRequest, task_id: str):
        """
        Process a video compilation request in the background
        """
        try:
            # Update task status
            self.tasks[task_id] = ProcessingStatus(
                task_id=task_id,
                status="processing",
                progress=0,
                message="Starting video processing..."
            )
            
            # Process each clip
            processed_clips = []
            total_clips = len(request.clips)
            
            for i, clip in enumerate(request.clips):
                try:
                    # Update progress
                    progress = int((i / total_clips) * 80)  # 80% for clip processing
                    self._update_task_status(task_id, "processing", progress, f"Processing clip {i+1}/{total_clips}")
                    
                    # Process individual clip
                    processed_clip = self._process_clip(clip, request, i)
                    processed_clips.append(processed_clip)
                    
                except Exception as e:
                    logger.error(f"Error processing clip {i}: {e}")
                    self._update_task_status(task_id, "error", 0, f"Error processing clip {i+1}: {str(e)}")
                    return
            
            # Update progress
            self._update_task_status(task_id, "processing", 80, "Stitching clips together...")
            
            # Stitch clips together
            final_video = self._stitch_clips(processed_clips, request)
            
            # Add background music if specified
            if request.music:
                self._update_task_status(task_id, "processing", 90, "Adding background music...")
                final_video = self._add_background_music(final_video, request.music)
            
            # Move to output directory
            output_filename = f"compilation_{task_id}.mp4"
            output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
            shutil.move(final_video, output_path)
            
            # Update final status
            download_url = f"/download/{output_filename}"
            self._update_task_status(
                task_id, 
                "completed", 
                100, 
                "Video compilation completed successfully!",
                download_url
            )
            
            # Cleanup temporary files
            if settings.CLEANUP_TEMP_FILES:
                self._cleanup_temp_files(processed_clips)
                
        except Exception as e:
            logger.error(f"Error in video processing task {task_id}: {e}")
            self._update_task_status(task_id, "error", 0, f"Processing failed: {str(e)}")
    
    def _process_clip(self, clip: ClipRequest, request: VideoRequest, index: int) -> str:
        """
        Process a single clip: download, generate summary, overlay text, format
        """
        try:
            # Generate temporary filenames
            temp_dir = os.path.join(settings.TEMP_DIR, f"clip_{index}")
            os.makedirs(temp_dir, exist_ok=True)
            
            raw_clip = os.path.join(temp_dir, "raw.mp4")
            styled_clip = os.path.join(temp_dir, "styled.mp4")
            final_clip = os.path.join(temp_dir, "final.mp4")
            
            # 1. Download YouTube clip
            self._download_clip(clip.url, clip.timestamp, raw_clip)
            
            # 2. Generate AI summary
            summary = self._generate_summary(clip)
            
            # 3. Overlay text
            self._overlay_text(raw_clip, styled_clip, summary, request)
            
            # 4. Format video to target dimensions
            self._format_video(styled_clip, final_clip, request.format)
            
            return final_clip
            
        except Exception as e:
            logger.error(f"Error processing clip {index}: {e}")
            raise
    
    def _download_clip(self, url: str, timestamp: int, output_path: str):
        """
        Download a 3-second clip from YouTube starting at the specified timestamp
        """
        ydl_opts = {
            "format": "best[height<=1080]",  # Limit to 1080p max
            "download_sections": {
                "*": [{"start_time": timestamp, "end_time": timestamp + settings.CLIP_DURATION}]
            },
            "outtmpl": output_path,
            "quiet": True,
            "no_warnings": True
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.error(f"Error downloading clip from {url}: {e}")
            raise Exception(f"Failed to download video: {str(e)}")
    
    def _generate_summary(self, clip: ClipRequest) -> str:
        """
        Generate AI summary from keywords or use custom text
        """
        if clip.custom_text:
            return clip.custom_text
        
        if not clip.keywords:
            return "Video clip"
        
        try:
            return self.ai_client.generate_summary(clip.keywords)
        except Exception as e:
            logger.warning(f"AI summary generation failed, using fallback: {e}")
            return clip.keywords[:50] + "..." if len(clip.keywords) > 50 else clip.keywords
    
    def _overlay_text(self, input_path: str, output_path: str, text: str, request: VideoRequest):
        """
        Overlay text on video using FFmpeg
        """
        # Escape text for FFmpeg
        escaped_text = text.replace("'", "\\'").replace('"', '\\"')
        
        # Calculate text position based on placement
        position = self._calculate_text_position(request.placement)
        
        # Build FFmpeg command
        cmd = [
            settings.FFMPEG_PATH,
            "-i", input_path,
            "-vf", f"drawtext=text='{escaped_text}':fontcolor={request.font_color}:fontsize={request.font_size}:{position}",
            "-codec:a", "copy",
            "-y",  # Overwrite output file
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"FFmpeg text overlay completed: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg text overlay failed: {e.stderr}")
            raise Exception(f"Text overlay failed: {e.stderr}")
    
    def _calculate_text_position(self, placement: str) -> str:
        """
        Calculate text position for FFmpeg drawtext filter
        """
        if placement == "top":
            return "x=(w-text_w)/2:y=50"
        elif placement == "center":
            return "x=(w-text_w)/2:y=(h-text_h)/2"
        else:  # bottom
            return "x=(w-text_w)/2:y=h-50"
    
    def _format_video(self, input_path: str, output_path: str, format_type: VideoFormat):
        """
        Format video to target dimensions with padding if necessary
        """
        format_info = settings.VIDEO_FORMATS[format_type]
        width = format_info["width"]
        height = format_info["height"]
        
        # Build FFmpeg command for resizing and padding
        cmd = [
            settings.FFMPEG_PATH,
            "-i", input_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "-c:a", "copy",
            "-y",
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"Video formatting completed: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Video formatting failed: {e.stderr}")
            raise Exception(f"Video formatting failed: {e.stderr}")
    
    def _stitch_clips(self, clip_paths: List[str], request: VideoRequest) -> str:
        """
        Stitch multiple clips together using FFmpeg concat
        """
        # Create concat file
        concat_file = os.path.join(settings.TEMP_DIR, "concat_list.txt")
        with open(concat_file, "w") as f:
            for clip_path in clip_paths:
                f.write(f"file '{clip_path}'\n")
        
        # Output path for stitched video
        stitched_path = os.path.join(settings.TEMP_DIR, "stitched.mp4")
        
        # FFmpeg concat command
        cmd = [
            settings.FFMPEG_PATH,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            "-y",
            stitched_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"Video stitching completed: {result.stdout}")
            
            # Clean up concat file
            os.remove(concat_file)
            
            return stitched_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Video stitching failed: {e.stderr}")
            raise Exception(f"Video stitching failed: {e.stderr}")
    
    def _add_background_music(self, video_path: str, music_path: str) -> str:
        """
        Add background music to the video
        """
        output_path = os.path.join(settings.TEMP_DIR, "with_music.mp4")
        
        # FFmpeg command to mix audio
        cmd = [
            settings.FFMPEG_PATH,
            "-i", video_path,
            "-i", music_path,
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2",
            "-c:v", "copy",
            "-y",
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"Background music added: {result.stdout}")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Background music addition failed: {e.stderr}")
            # Return original video if music addition fails
            return video_path
    
    def _cleanup_temp_files(self, clip_paths: List[str]):
        """
        Clean up temporary files and directories
        """
        try:
            for clip_path in clip_paths:
                clip_dir = os.path.dirname(clip_path)
                if os.path.exists(clip_dir):
                    shutil.rmtree(clip_dir)
            
            # Clean up other temp files
            temp_files = ["stitched.mp4", "with_music.mp4"]
            for temp_file in temp_files:
                temp_path = os.path.join(settings.TEMP_DIR, temp_file)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
    
    def _update_task_status(self, task_id: str, status: str, progress: int, message: str, download_url: Optional[str] = None):
        """
        Update the status of a processing task
        """
        if task_id in self.tasks:
            self.tasks[task_id].status = status
            self.tasks[task_id].progress = progress
            self.tasks[task_id].message = message
            if download_url:
                self.tasks[task_id].download_url = download_url
    
    def get_task_status(self, task_id: str) -> ProcessingStatus:
        """
        Get the current status of a processing task
        """
        if task_id not in self.tasks:
            raise Exception("Task not found")
        return self.tasks[task_id]
