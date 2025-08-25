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
        # Convert HttpUrl to string if needed
        url_str = str(url)
        
        # First, download the full video to a temporary file
        temp_video = output_path.replace('.mp4', '_temp.mp4')
        
        ydl_opts = {
            "format": "best[height<=1080]",  # Limit to 1080p max
            "outtmpl": temp_video,
            "quiet": True,
            "no_warnings": True
        }
        
        try:
            # Download the full video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url_str])
            
            # Now extract the exact 3-second segment using FFmpeg
            cmd = [
                settings.FFMPEG_PATH,
                "-i", temp_video,
                "-ss", str(timestamp),  # Start at timestamp
                "-t", str(settings.CLIP_DURATION),  # Duration of 3 seconds
                "-c:v", "copy",  # Copy video codec (fast)
                "-c:a", "copy",  # Copy audio codec (fast)
                "-avoid_negative_ts", "make_zero",  # Handle timestamp issues
                "-y",  # Overwrite output
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"FFmpeg clip extraction completed: {result.stdout}")
            
            # Clean up temporary file
            if os.path.exists(temp_video):
                os.remove(temp_video)
                
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg clip extraction failed: {e.stderr}")
            # Clean up on error
            if os.path.exists(temp_video):
                os.remove(temp_video)
            raise Exception(f"Failed to extract video clip: {e.stderr}")
        except Exception as e:
            logger.error(f"Error downloading video from {url_str}: {e}")
            # Clean up on error
            if os.path.exists(temp_video):
                os.remove(temp_video)
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
        # Calculate text position based on placement
        position = self._calculate_text_position(request.placement)
        
        # Use a simpler approach - create a text file for the text content
        # This avoids all escaping issues with FFmpeg
        # Get the directory from the output path more explicitly
        output_dir = os.path.dirname(output_path)
        text_file = os.path.join(output_dir, "text.txt")
        
        # Ensure the directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Debug: Log the actual paths being used
        logger.info(f"Output path: {output_path}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Text file path: {text_file}")
        
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(text)
        
        # Verify the file was created and has content
        if os.path.exists(text_file):
            with open(text_file, "r", encoding="utf-8") as f:
                file_content = f.read()
            logger.info(f"Text file created successfully at: {text_file}")
            logger.info(f"Text file content: {file_content}")
            logger.info(f"Text file size: {os.path.getsize(text_file)} bytes")
        else:
            logger.error(f"Text file was not created at: {text_file}")
            raise Exception(f"Failed to create text file at {text_file}")
        
        # Build FFmpeg command using textfile for reliable text handling
        # Convert Windows backslashes to forward slashes for FFmpeg compatibility
        text_file_ffmpeg = text_file.replace('\\', '/')
        
        # Use custom font with black outline (Mr Beast style)
        font_path = os.path.join(settings.FONT_DIR, settings.DEFAULT_FONT)
        font_path_ffmpeg = font_path.replace('\\', '/')
        
        # Create filter with custom font and black outline
        filter_complex = f'drawtext=textfile={text_file_ffmpeg}:fontfile={font_path_ffmpeg}:fontcolor={request.font_color}:fontsize={request.font_size}:{position}:borderw=4:bordercolor=black'
        
        # Debug logging
        logger.info(f"Original text file path: {text_file}")
        logger.info(f"FFmpeg-compatible text file path: {text_file_ffmpeg}")
        logger.info(f"Font path: {font_path}")
        logger.info(f"FFmpeg-compatible font path: {font_path_ffmpeg}")
        logger.info(f"FFmpeg filter: {filter_complex}")
        
        cmd = [
            settings.FFMPEG_PATH,
            "-i", input_path,
            "-vf", filter_complex,
            "-codec:a", "copy",
            "-y",  # Overwrite output file
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"FFmpeg text overlay completed: {result.stdout}")
            
            # Clean up text file
            if os.path.exists(text_file):
                os.remove(text_file)
                
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg text overlay failed: {e.stderr}")
            # Clean up text file on error
            if os.path.exists(text_file):
                os.remove(text_file)
            raise Exception(f"Text overlay failed: {e.stderr}")
    
    def _calculate_text_position(self, placement: str) -> str:
        """
        Calculate text position for FFmpeg drawtext filter
        """
        if placement == "top":
            return "x=(w-text_w)/2:y=50"
        elif placement == "center":
            return "x=(w-text_w)/2:y=(h-text_h)/2"
        else:  # bottom - 80% from bottom (20% padding)
            return "x=(w-text_w)/2:y=h*0.8-text_h/2"
    
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
        # Debug: Log all clip paths being stitched
        logger.info(f"Stitching {len(clip_paths)} clips together")
        for i, clip_path in enumerate(clip_paths):
            logger.info(f"Clip {i}: {clip_path}")
            if os.path.exists(clip_path):
                file_size = os.path.getsize(clip_path)
                logger.info(f"Clip {i} exists, size: {file_size} bytes")
            else:
                logger.warning(f"Clip {i} does not exist: {clip_path}")
        
        # Create concat file
        concat_file = os.path.join(settings.TEMP_DIR, "concat_list.txt")
        with open(concat_file, "w") as f:
            for clip_path in clip_paths:
                f.write(f"file '{clip_path}'\n")
        
        # Log the concat file contents
        with open(concat_file, "r") as f:
            concat_contents = f.read()
        logger.info(f"Concat file contents:\n{concat_contents}")
        
        # Output path for stitched video
        stitched_path = os.path.join(settings.TEMP_DIR, "stitched.mp4")
        
        # FFmpeg concat command - use re-encoding for better compatibility
        cmd = [
            settings.FFMPEG_PATH,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",  # Re-encode video for better compatibility
            "-c:a", "aac",       # Re-encode audio for better compatibility
            "-preset", "fast",   # Fast encoding
            "-crf", "23",        # Good quality
            "-y",
            stitched_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Video stitching completed: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(stitched_path):
                final_size = os.path.getsize(stitched_path)
                logger.info(f"Stitched video created successfully, size: {final_size} bytes")
            else:
                logger.error("Stitched video file was not created")
            
            # Clean up concat file
            os.remove(concat_file)
            
            return stitched_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Video stitching failed: {e.stderr}")
            # Clean up on error
            if os.path.exists(concat_file):
                os.remove(concat_file)
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
