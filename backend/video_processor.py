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
import re

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
        
        # Load existing tasks from disk
        self._load_tasks_from_disk()
        
        # Validate FFmpeg installation
        self._validate_ffmpeg_installation()
    
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
                    # Update progress (adjusted for intro/outro)
                    progress = int((i / total_clips) * 70)  # 70% for clip processing (intro/outro will take 10%)
                    self._update_task_status(task_id, "processing", progress, f"Processing clip {i+1}/{total_clips}")
                    
                    # Process individual clip
                    processed_clip = self._process_clip(clip, request, i)
                    processed_clips.append(processed_clip)
                    
                except Exception as e:
                    logger.error(f"Error processing clip {i}: {e}")
                    self._update_task_status(task_id, "error", 0, f"Error processing clip {i+1}: {str(e)}")
                    return
            
            # Update progress
            self._update_task_status(task_id, "processing", 80, "Stitching intro, clips, and outro together...")
            
            # Create intro and outro clips
            self._update_task_status(task_id, "processing", 75, "Creating intro sequence...")
            intro_clip = self._create_intro_clip(processed_clips[0], request)
            
            self._update_task_status(task_id, "processing", 77, "Creating outro sequence...")
            outro_clip = self._create_outro_clip(processed_clips[0], request)
            
            # Combine intro + clips + outro
            all_clips = [intro_clip] + processed_clips + [outro_clip]
            
            # Debug logging for clip combination
            logger.info(f"Combining clips for stitching:")
            logger.info(f"Intro clip: {intro_clip} (exists: {os.path.exists(intro_clip)})")
            for i, clip in enumerate(processed_clips):
                logger.info(f"Content clip {i}: {clip} (exists: {os.path.exists(clip)})")
            logger.info(f"Outro clip: {outro_clip} (exists: {os.path.exists(outro_clip)})")
            logger.info(f"Total clips to stitch: {len(all_clips)}")
            
            # Stitch all clips together
            final_video = self._stitch_clips(all_clips, request)
            
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
            
            # 5. Normalize timestamps to ensure proper concatenation
            normalized_clip = self._normalize_timestamps(final_clip, temp_dir)
            
            return normalized_clip
            
        except Exception as e:
            logger.error(f"Error processing clip {index}: {e}")
            raise
    
    def _download_clip(self, url: str, timestamp: int, output_path: str):
        """
        Download a 3-second clip from YouTube starting at the specified timestamp
        
        Timeout handling:
        - Base timeout: 120 seconds (2 minutes)
        - Additional time: 3 seconds per MB of video file
        - Large files (100MB+) get extra logging and progress updates
        """
        # Convert HttpUrl to string if needed
        url_str = str(url)
        
        # Create a unique temp filename to avoid conflicts
        temp_dir = os.path.dirname(output_path)
        temp_video = os.path.join(temp_dir, f"temp_{os.path.basename(output_path)}")
        
        ydl_opts = {
            # Video-only formats: 1080p > 720p > 480p, prefer MP4, NO audio
            "format": "bestvideo[height>=720][ext=mp4]/bestvideo[height>=720]/best[height>=720]/best[ext=mp4]/best",
            "outtmpl": temp_video,
            "quiet": True,
            "no_warnings": True,
            # No need for audio merging since we mute everything
            "noplaylist": True
        }
        
        try:
            # Download the full video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get video info first to log quality
                try:
                    info = ydl.extract_info(url_str, download=False)
                    if 'formats' in info and info['formats']:
                        # Find best format that was selected
                        formats = info['formats']
                        best_format = None
                        for fmt in formats:
                            if isinstance(fmt, dict) and fmt.get('height', 0) >= 720:
                                best_format = fmt
                                break
                        if best_format:
                            height = best_format.get('height', 'unknown')
                            width = best_format.get('width', 'unknown')
                            ext = best_format.get('ext', 'unknown')
                            filesize = best_format.get('filesize', 'unknown')
                            logger.info(f"Selected video format: {width}x{height} {ext}, size: {filesize} bytes")
                        else:
                            logger.warning("No HD format found, using best available")
                    else:
                        logger.info("Video info extracted, format details not available")
                except Exception as info_e:
                    logger.warning(f"Could not extract video info: {info_e}")
                
                # Download the video
                ydl.download([url_str])
            
            # Check if the temp file was created with the expected name
            # yt-dlp might add extensions or modify the filename
            actual_temp_file = None
            if os.path.exists(temp_video):
                actual_temp_file = temp_video
                logger.info(f"Using expected temp file: {actual_temp_file}")
            else:
                # Look for the actual downloaded file
                logger.info(f"Expected temp file not found: {temp_video}")
                logger.info(f"Searching in directory: {temp_dir}")
                logger.info(f"Directory contents: {os.listdir(temp_dir) if os.path.exists(temp_dir) else 'Directory does not exist'}")
                
                for filename in os.listdir(temp_dir):
                    if filename.startswith("temp_") and filename.endswith(('.mp4', '.webm', '.mkv')):
                        actual_temp_file = os.path.join(temp_dir, filename)
                        logger.info(f"Found downloaded file: {actual_temp_file}")
                        break
                
                # If still not found, try to find any video file
                if not actual_temp_file:
                    for filename in os.listdir(temp_dir):
                        if filename.endswith(('.mp4', '.webm', '.mkv')):
                            actual_temp_file = os.path.join(temp_dir, filename)
                            logger.info(f"Found alternative video file: {actual_temp_file}")
                            break
            
            if not actual_temp_file:
                raise Exception(f"Downloaded video file not found. Expected: {temp_video}, Directory contents: {os.listdir(temp_dir) if os.path.exists(temp_dir) else 'Directory does not exist'}")
            
            logger.info(f"Processing downloaded video: {actual_temp_file}")
            
            # Now extract the exact 3-second segment using FFmpeg
            # Use faster settings for quicker processing
            # MUTE the audio completely
            cmd = [
                settings.FFMPEG_PATH,
                "-i", actual_temp_file,
                "-ss", str(timestamp),  # Start at timestamp
                "-t", str(settings.CLIP_DURATION),  # Duration of 3 seconds
                "-c:v", "libx264",  # Re-encode video for timestamp accuracy
                "-an",               # Remove audio completely (mute)
                "-preset", "ultrafast",  # Fastest encoding for speed
                "-crf", "28",        # Slightly lower quality for speed
                "-avoid_negative_ts", "make_zero",  # Reset timestamps
                "-vsync", "cfr",     # Constant frame rate
                "-threads", "0",     # Use all available CPU threads
                "-y",  # Overwrite output
                output_path
            ]
            
            # Log the full FFmpeg command for debugging
            logger.info(f"FFmpeg command: {' '.join(cmd)}")
            logger.info(f"Input file exists: {os.path.exists(actual_temp_file)}")
            logger.info(f"Input file size: {os.path.getsize(actual_temp_file) if os.path.exists(actual_temp_file) else 'N/A'} bytes")
            logger.info(f"Output directory exists: {os.path.exists(os.path.dirname(output_path))}")
            
            try:
                # Verify all paths before running FFmpeg
                if not os.path.exists(actual_temp_file):
                    raise Exception(f"Input file does not exist: {actual_temp_file}")
                
                output_dir = os.path.dirname(output_path)
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
                    logger.info(f"Created output directory: {output_dir}")
                
                # Check if FFmpeg executable exists
                logger.info(f"FFmpeg path from settings: {settings.FFMPEG_PATH}")
                if not os.path.exists(settings.FFMPEG_PATH):
                    raise Exception(f"FFmpeg executable not found at: {settings.FFMPEG_PATH}")
                
                logger.info(f"FFmpeg executable verified, size: {os.path.getsize(settings.FFMPEG_PATH)} bytes")
                
                # Test if FFmpeg can run at all
                try:
                    test_result = subprocess.run([settings.FFMPEG_PATH, "-version"], 
                                              capture_output=True, text=True, timeout=10)
                    logger.info(f"FFmpeg version test successful: {test_result.stdout[:100]}...")
                except Exception as test_e:
                    logger.error(f"FFmpeg version test failed: {test_e}")
                    raise Exception(f"FFmpeg is not working: {test_e}")
                
                logger.info(f"Running FFmpeg command...")
                # Increase timeout for large files - base timeout + additional time per MB
                file_size_mb = os.path.getsize(actual_temp_file) / (1024 * 1024)
                timeout_seconds = max(120, int(file_size_mb * 3))  # At least 120s, plus 3s per MB for safety
                logger.info(f"File size: {file_size_mb:.1f}MB, using timeout: {timeout_seconds}s")
                logger.info(f"Processing large file - this may take several minutes...")
                logger.info(f"FFmpeg processing started at: {time.strftime('%H:%M:%S')}")
                
                # For large files, provide more frequent progress updates
                if file_size_mb > 100:  # Very large files
                    logger.info(f"Large file detected ({file_size_mb:.1f}MB) - processing may take 5-10 minutes")
                
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout_seconds)
                logger.info(f"FFmpeg processing completed at: {time.strftime('%H:%M:%S')}")
                logger.info(f"FFmpeg clip extraction completed: {result.stdout}")
                
            except subprocess.TimeoutExpired:
                logger.error(f"FFmpeg command timed out after {timeout_seconds} seconds")
                raise Exception(f"FFmpeg command timed out after {timeout_seconds} seconds")
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg command failed with return code {e.returncode}")
                logger.error(f"FFmpeg stderr: {e.stderr}")
                logger.error(f"FFmpeg stdout: {e.stdout}")
                raise Exception(f"FFmpeg command failed: {e.stderr}")
            except FileNotFoundError as e:
                logger.error(f"File not found error: {e}")
                raise Exception(f"File not found: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during FFmpeg execution: {e}")
                raise Exception(f"FFmpeg execution error: {e}")
            
            # Clean up temporary file
            if os.path.exists(actual_temp_file):
                os.remove(actual_temp_file)
                
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
        Overlay text on video using FFmpeg with text wrapping
        """
        # Calculate text position based on placement
        position = self._calculate_text_position(request.placement)
        
        # Get the directory from the output path more explicitly
        output_dir = os.path.dirname(output_path)
        text_file = os.path.join(output_dir, "text.txt")
        
        # Ensure the directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Create wrapped text with line breaks
        wrapped_text = self._wrap_text(text, request.font_size, request.format)
        
        # Debug: Log the actual paths being used
        logger.info(f"Output path: {output_path}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Text file path: {text_file}")
        logger.info(f"Original text: {text}")
        logger.info(f"Wrapped text: {wrapped_text}")
        
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(wrapped_text)
        
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
        
        # Create filter with custom font, black outline, and minimal line spacing
        # Increase font size for MrBeast-style visibility and reduce line spacing
        adjusted_font_size = max(request.font_size, 48)  # Minimum 48px for visibility
        filter_complex = f'drawtext=textfile={text_file_ffmpeg}:fontfile={font_path_ffmpeg}:fontcolor={request.font_color}:fontsize={adjusted_font_size}:{position}:borderw=4:bordercolor=black:line_spacing=2'
        
        # Debug logging
        logger.info(f"Original text file path: {text_file}")
        logger.info(f"FFmpeg-compatible text file path: {text_file_ffmpeg}")
        logger.info(f"Font path: {font_path}")
        logger.info(f"FFmpeg-compatible font path: {font_path_ffmpeg}")
        logger.info(f"Original font size: {request.font_size}, Adjusted font size: {adjusted_font_size}")
        logger.info(f"FFmpeg filter: {filter_complex}")
        
        cmd = [
            settings.FFMPEG_PATH,
            "-i", input_path,
            "-vf", filter_complex,
            "-an",               # Remove audio (mute)
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
            return "x=w*0.075:y=50"  # 7.5% from left
        elif placement == "center":
            return "x=w*0.075:y=(h-text_h)/2"  # 7.5% from left, center vertically
        else:  # bottom - 80% from bottom, 7.5% from left
            return "x=w*0.075:y=h*0.8-text_h/2"
    
    def _wrap_text(self, text: str, font_size: int, format_type: str) -> str:
        """
        Wrap text to fit within video width with 7.5% padding on both sides
        Estimated characters per line based on font size and video width
        """
        # Estimate characters per line based on font size and format
        # For vertical formats (shorts), we need fewer characters per line due to narrower width
        if format_type == "shorts":
            # YouTube Shorts: 1080px width (vs 1920px for horizontal)
            if font_size <= 24:
                chars_per_line = 20  # Reduced for vertical format
            elif font_size <= 36:
                chars_per_line = 15
            elif font_size <= 48:
                chars_per_line = 12
            else:
                chars_per_line = 10
        elif format_type == "instagram":
            # Instagram: 1080px width (square format)
            if font_size <= 24:
                chars_per_line = 25
            elif font_size <= 36:
                chars_per_line = 20
            elif font_size <= 48:
                chars_per_line = 15
            else:
                chars_per_line = 12
        else:
            # YouTube: 1920px width (horizontal format)
            if font_size <= 24:
                chars_per_line = 40
            elif font_size <= 36:
                chars_per_line = 30
            elif font_size <= 48:
                chars_per_line = 25
            else:
                chars_per_line = 20
        
        # Split text into words
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            # Check if adding this word would exceed the line limit
            if len(current_line + " " + word) <= chars_per_line:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
            else:
                # Add current line to lines and start new line
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        # Add the last line if it exists
        if current_line:
            lines.append(current_line)
        
        # Join lines with newline characters for FFmpeg
        wrapped_text = "\n".join(lines)
        
        logger.info(f"Text wrapping for {format_type}: {len(words)} words, {len(lines)} lines, ~{chars_per_line} chars per line")
        
        return wrapped_text
    
    def _normalize_timestamps(self, input_path: str, temp_dir: str) -> str:
        """
        Normalize video timestamps to start at 0 for proper concatenation
        """
        normalized_path = os.path.join(temp_dir, "normalized.mp4")
        
        # FFmpeg command to reset timestamps and ensure proper sync
        cmd = [
            settings.FFMPEG_PATH,
            "-i", input_path,
            "-c:v", "copy",        # Copy video stream
            "-c:a", "copy",        # Copy audio stream
            "-avoid_negative_ts", "make_zero",  # Reset timestamps to 0
            "-fflags", "+genpts",  # Generate presentation timestamps
            "-y",
            normalized_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"Timestamp normalization completed: {result.stdout}")
            
            # Verify the normalized file
            if os.path.exists(normalized_path):
                file_size = os.path.getsize(normalized_path)
                logger.info(f"Normalized clip created, size: {file_size} bytes")
                return normalized_path
            else:
                logger.warning("Normalized clip not created, using original")
                return input_path
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Timestamp normalization failed: {e.stderr}")
            logger.warning("Using original clip due to normalization failure")
            return input_path

    def _format_video(self, input_path: str, output_path: str, format_type: VideoFormat):
        """
        Format video to target dimensions with proper aspect ratio handling
        
        Cropping Strategy:
        - YouTube Shorts (9:16): Crop width from sides, maintain height, then scale
        - Instagram (1:1): Crop to square, center content, then scale  
        - YouTube (16:9): Scale with padding to maintain aspect ratio
        
        This ensures videos are properly cropped instead of squeezed/stretched.
        """
        format_info = settings.VIDEO_FORMATS[format_type]
        target_width = format_info["width"]
        target_height = format_info["height"]
        
        # Log the formatting operation
        logger.info(f"Formatting video to {target_width}x{target_height} ({format_type})")
        
        # First, check if the input video is already in the target format
        try:
            # Get video dimensions using FFprobe
            probe_cmd = [
                settings.FFMPEG_PATH.replace("ffmpeg", "ffprobe"),
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "v:0",
                input_path
            ]
            
            # Try to use ffprobe, fallback to ffmpeg if not available
            if not os.path.exists(probe_cmd[0]):
                probe_cmd[0] = settings.FFMPEG_PATH
                probe_cmd[1:3] = ["-i", input_path]
                probe_cmd[3:] = ["-f", "null", "-"]
            
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            
            if probe_result.returncode == 0:
                # Parse video dimensions from ffprobe output
                if "ffprobe" in probe_cmd[0]:
                    try:
                        import json
                        video_info = json.loads(probe_result.stdout)
                        if 'streams' in video_info and video_info['streams']:
                            stream = video_info['streams'][0]
                            input_width = int(stream.get('width', 0))
                            input_height = int(stream.get('height', 0))
                            
                            # Calculate aspect ratios
                            input_ratio = input_width / input_height if input_height > 0 else 0
                            target_ratio = target_width / target_height
                            
                            logger.info(f"Input video dimensions: {input_width}x{input_height} (ratio: {input_ratio:.3f})")
                            logger.info(f"Target dimensions: {target_width}x{target_height} (ratio: {target_ratio:.3f})")
                            
                            # Check if aspect ratios are close enough (within 0.1 tolerance)
                            if abs(input_ratio - target_ratio) < 0.1:
                                logger.info(f"Video is already in target format ({format_type}), skipping formatting")
                                # Just copy the file to output path
                                shutil.copy2(input_path, output_path)
                                return
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Could not parse video info: {e}, proceeding with formatting")
                else:
                    # Fallback: try to extract dimensions from ffmpeg output
                    lines = probe_result.stderr.split('\n')
                    for line in lines:
                        if 'Stream' in line and 'Video' in line:
                            # Look for dimensions like "1920x1080"
                            import re
                            match = re.search(r'(\d+)x(\d+)', line)
                            if match:
                                input_width = int(match.group(1))
                                input_height = int(match.group(2))
                                input_ratio = input_width / input_height
                                target_ratio = target_width / target_height
                                
                                logger.info(f"Input video dimensions: {input_width}x{input_height} (ratio: {input_ratio:.3f})")
                                logger.info(f"Target dimensions: {target_width}x{target_height} (ratio: {target_ratio:.3f})")
                                
                                if abs(input_ratio - target_ratio) < 0.1:
                                    logger.info(f"Video is already in target format ({format_type}), skipping formatting")
                                    shutil.copy2(input_path, output_path)
                                    return
                                break
        except Exception as e:
            logger.warning(f"Could not check video dimensions: {e}, proceeding with formatting")
        
        # Build FFmpeg command with improved aspect ratio handling
        if format_type == "shorts":
            # For YouTube Shorts (9:16): Crop from sides, maintain center content
            # This ensures we crop from the sides instead of squeezing
            # For 16:9 input (1920x1080) -> crop to 608x1080 (9:16 ratio) -> scale to 1080x1920
            # For 4:3 input (1440x1080) -> crop to 608x1080 (9:16 ratio) -> scale to 1080x1920
            # The key is to maintain the original height and crop the width proportionally
            
            # Calculate expected crop dimensions for logging
            # For a 1920x1080 input: crop width = 1920 * 9/16 = 1080, crop height = 1080
            # This gives us a 1080x1080 crop, which when scaled becomes 1080x1920 (9:16)
            filter_complex = (
                f"crop=iw*9/16:ih:(iw-iw*9/16)/2:0,"  # Crop to 9:16 ratio, center horizontally
                f"scale={target_width}:{target_height}"  # Scale to target dimensions
            )
            logger.info(f"Using crop filter for YouTube Shorts: crop=iw*9/16:ih:(iw-iw*9/16)/2:0")
            logger.info(f"This will crop the width to 9/16 of original while maintaining height")
            logger.info(f"Example: 1920x1080 -> crop to 1080x1080 -> scale to 1080x1920")
        elif format_type == "instagram":
            # For Instagram (1:1): Crop to square, scale to 1080x1080
            filter_complex = (
                f"crop=min(iw,ih):min(iw,ih):(iw-min(iw,ih))/2:(ih-min(iw,ih))/2,"  # Crop to square, center
                f"scale={target_width}:{target_height}"  # Scale to target dimensions
            )
        else:
            # For YouTube (16:9): Use standard scaling with padding
            filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black"
        
        cmd = [
            settings.FFMPEG_PATH,
            "-i", input_path,
            "-vf", filter_complex,
            "-an",               # Remove audio (mute)
            "-y",
            output_path
        ]
        
        logger.info(f"FFmpeg format command: {' '.join(cmd)}")
        logger.info(f"Filter complex: {filter_complex}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Video formatting completed successfully: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"Formatted video created at {output_path}, size: {file_size} bytes")
            else:
                logger.error(f"Formatted video was not created at {output_path}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Video formatting failed: {e.stderr}")
            raise Exception(f"Video formatting failed: {e.stderr}")
    
    def _stitch_clips(self, clip_paths: List[str], request: VideoRequest) -> str:
        """
        Stitch multiple clips together using FFmpeg with crossfade transitions
        """
        # Debug: Log all clip paths being stitched
        logger.info(f"Stitching {len(clip_paths)} clips together with crossfade transitions")
        for i, clip_path in enumerate(clip_paths):
            logger.info(f"Clip {i}: {clip_path}")
            if os.path.exists(clip_path):
                file_size = os.path.getsize(clip_path)
                logger.info(f"Clip {i} exists, size: {file_size} bytes")
                
                # Verify the clip is a valid video file
                if file_size < 10000:  # Less than 10KB is suspicious
                    logger.warning(f"Clip {i} seems too small ({file_size} bytes), may be corrupted")
                
                # Try to get video info for each clip
                probe_cmd = [
                    settings.FFMPEG_PATH,
                    "-i", clip_path,
                    "-hide_banner"
                ]
                try:
                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
                    logger.info(f"Clip {i} video info: {probe_result.stderr}")  # FFmpeg outputs info to stderr
                except Exception as probe_e:
                    logger.error(f"Failed to probe clip {i}: {probe_e}")
                    
            else:
                logger.warning(f"Clip {i} does not exist: {clip_path}")
        
        # Output path for stitched video
        stitched_path = os.path.join(settings.TEMP_DIR, "stitched.mp4")
        
        if len(clip_paths) == 1:
            # Single clip - just copy it
            logger.info("Single clip detected, copying directly")
            shutil.copy2(clip_paths[0], stitched_path)
            return stitched_path
        
        elif len(clip_paths) == 2:
            # Two clips - use crossfade transition
            return self._stitch_two_clips_with_crossfade(clip_paths[0], clip_paths[1], stitched_path)
        
        elif len(clip_paths) == 3:
            # Three clips (intro + 1 clip + outro) - use crossfade transitions
            return self._stitch_three_clips_with_crossfades(clip_paths, stitched_path)
        
        elif len(clip_paths) == 4:
            # Four clips (intro + 2 clips + outro) - use crossfade transitions
            return self._stitch_four_clips_with_crossfades(clip_paths, stitched_path)
        
        else:
            # Multiple clips - use enhanced concat with crossfades
            return self._stitch_multiple_clips_with_enhanced_transitions(clip_paths, stitched_path)
    
    def _stitch_two_clips_with_crossfade(self, clip1_path: str, clip2_path: str, output_path: str) -> str:
        """
        Stitch two clips with a crossfade transition
        """
        # Crossfade duration: 0.2 seconds (200ms)
        crossfade_duration = 0.2
        
        # Convert Windows backslashes to forward slashes for FFmpeg compatibility
        clip1_ffmpeg = clip1_path.replace('\\', '/')
        clip2_ffmpeg = clip2_path.replace('\\', '/')
        
        # FFmpeg command with crossfade transition and frame rate normalization
        cmd = [
            settings.FFMPEG_PATH,
            "-i", clip1_ffmpeg,
            "-i", clip2_ffmpeg,
            "-filter_complex", f"[0:v]fps=fps=30:round=up,fade=t=out:st=2.8:d={crossfade_duration}[v0];[1:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration}[v1];[v0][v1]xfade=transition=fade:duration={crossfade_duration}:offset=2.8[v]",
            "-map", "[v]",
            "-c:v", "libx264",      # Re-encode for filter compatibility
            "-preset", "ultrafast",  # Fastest encoding for speed
            "-crf", "28",            # Slightly lower quality for speed
            "-threads", "0",         # Use all available CPU threads
            "-an",                   # No audio
            "-r", "30",              # Force output to 30fps
            "-y",
            output_path
        ]
        
        logger.info(f"FFmpeg crossfade command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Crossfade stitching completed: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path)
                logger.info(f"Crossfade video created successfully, size: {final_size} bytes")
                return output_path
            else:
                logger.error("Crossfade video file was not created")
                raise Exception("Crossfade video file was not created")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Crossfade stitching failed: {e.stderr}")
            # Fallback to concat method if crossfade fails
            logger.info("Crossfade failed, falling back to concat method")
            return self._stitch_clips_with_concat_fallback([clip1_path, clip2_path], output_path)
    
    def _stitch_multiple_clips_with_enhanced_transitions(self, clip_paths: List[str], output_path: str) -> str:
        """
        Stitch multiple clips with enhanced crossfade transitions
        """
        logger.info(f"Multiple clips detected ({len(clip_paths)}), using enhanced crossfade transitions")
        
        # Check if this is intro + clips + outro pattern
        if len(clip_paths) >= 3:
            # First clip should be intro (2s), last clip should be outro (2s)
            # Middle clips are the actual video content (3s each)
            intro_clip = clip_paths[0]
            outro_clip = clip_paths[-1]
            content_clips = clip_paths[1:-1]
            
            logger.info(f"Detected intro + {len(content_clips)} content clips + outro pattern")
            logger.info(f"Intro: {intro_clip}")
            logger.info(f"Content clips: {content_clips}")
            logger.info(f"Outro: {outro_clip}")
            
            # Use specialized method for intro + content + outro
            return self._stitch_intro_content_outro_with_transitions(intro_clip, content_clips, outro_clip, output_path)
        else:
            # Fallback to chain method
            return self._stitch_clips_with_chain_transitions(clip_paths, output_path)
    
    def _stitch_intro_content_outro_with_transitions(self, intro_clip: str, content_clips: List[str], outro_clip: str, output_path: str) -> str:
        """
        Stitch intro + content clips + outro with smooth crossfade transitions
        """
        # Crossfade duration: 0.2 seconds (200ms)
        crossfade_duration = 0.2
        
        # Convert Windows backslashes to forward slashes for FFmpeg compatibility
        intro_ffmpeg = intro_clip.replace('\\', '/')
        outro_ffmpeg = outro_clip.replace('\\', '/')
        content_ffmpeg_paths = [clip.replace('\\', '/') for clip in content_clips]
        
        # Build complex filter for all clips with transitions
        # Intro (2s) -> Content clips (3s each) -> Outro (2s)
        
        # Start with intro fade out
        filter_parts = [f"[0:v]fps=fps=30:round=up,fade=t=out:st=1.8:d={crossfade_duration}[intro]"]
        
        # Add content clips with fade in/out
        for i, content_path in enumerate(content_ffmpeg_paths):
            if i == 0:
                # First content clip: fade in at start, fade out at end
                filter_parts.append(f"[{i+1}:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration},fade=t=out:st=2.8:d={crossfade_duration}[content{i}]")
            else:
                # Other content clips: fade in at start, fade out at end
                filter_parts.append(f"[{i+1}:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration},fade=t=out:st=2.8:d={crossfade_duration}[content{i}]")
        
        # Add outro fade in
        outro_index = len(content_clips) + 1
        filter_parts.append(f"[{outro_index}:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration}[outro]")
        
        # Build xfade chain
        xfade_parts = []
        current_input = "intro"
        
        # Crossfade intro to first content clip
        xfade_parts.append(f"[{current_input}][content0]xfade=transition=fade:duration={crossfade_duration}:offset=1.8[tmp0]")
        current_input = "tmp0"
        
        # Crossfade between content clips
        for i in range(len(content_clips) - 1):
            xfade_parts.append(f"[{current_input}][content{i+1}]xfade=transition=fade:duration={crossfade_duration}:offset={1.8 + (i+1)*3.0}[tmp{i+1}]")
            current_input = f"tmp{i+1}"
        
        # Crossfade last content clip to outro
        final_offset = 1.8 + len(content_clips) * 3.0
        xfade_parts.append(f"[{current_input}][outro]xfade=transition=fade:duration={crossfade_duration}:offset={final_offset}[v]")
        
        # Combine all filter parts
        filter_complex = ";".join(filter_parts + xfade_parts)
        
        # Build FFmpeg command
        cmd = [settings.FFMPEG_PATH]
        
        # Add input files
        cmd.extend(["-i", intro_ffmpeg])
        for content_path in content_ffmpeg_paths:
            cmd.extend(["-i", content_path])
        cmd.extend(["-i", outro_ffmpeg])
        
        # Add filter and output options
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-an",
            "-r", "30",
            "-y",
            output_path
        ])
        
        logger.info(f"FFmpeg intro+content+outro command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Intro+content+outro stitching completed: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path)
                logger.info(f"Intro+content+outro video created successfully, size: {final_size} bytes")
                return output_path
            else:
                logger.error("Intro+content+outro video file was not created")
                raise Exception("Intro+content+outro video file was not created")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Intro+content+outro stitching failed: {e.stderr}")
            # Fallback to concat method if crossfade fails
            logger.info("Crossfade failed, falling back to concat method")
            return self._stitch_clips_with_concat_fallback([intro_clip] + content_clips + [outro_clip], output_path)
    
    def _stitch_four_clips_with_crossfades(self, clip_paths: List[str], output_path: str) -> str:
        """
        Stitch four clips (intro + 2 clips + outro) with crossfade transitions
        """
        # Crossfade duration: 0.2 seconds (200ms)
        crossfade_duration = 0.2
        
        # Convert Windows backslashes to forward slashes for FFmpeg compatibility
        intro_ffmpeg = clip_paths[0].replace('\\', '/')
        clip1_ffmpeg = clip_paths[1].replace('\\', '/')
        clip2_ffmpeg = clip_paths[2].replace('\\', '/')
        outro_ffmpeg = clip_paths[3].replace('\\', '/')
        
        # FFmpeg command with crossfade transitions between all four clips
        # Intro (2s) -> Clip1 (3s) -> Clip2 (3s) -> Outro (2s)
        # Crossfades at: 1.8s, 4.8s, 7.8s
        filter_complex = (
            f"[0:v]fps=fps=30:round=up,fade=t=out:st=1.8:d={crossfade_duration}[intro];"
            f"[1:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration},fade=t=out:st=2.8:d={crossfade_duration}[v1];"
            f"[2:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration},fade=t=out:st=2.8:d={crossfade_duration}[v2];"
            f"[3:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration}[outro];"
            f"[intro][v1]xfade=transition=fade:duration={crossfade_duration}:offset=1.8[tmp1];"
            f"[tmp1][v2]xfade=transition=fade:duration={crossfade_duration}:offset=4.6[tmp2];"
            f"[tmp2][outro]xfade=transition=fade:duration={crossfade_duration}:offset=7.6[v]"
        )
        
        cmd = [
            settings.FFMPEG_PATH,
            "-i", intro_ffmpeg,
            "-i", clip1_ffmpeg,
            "-i", clip2_ffmpeg,
            "-i", outro_ffmpeg,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-c:v", "libx264",      # Re-encode for filter compatibility
            "-preset", "ultrafast",  # Fastest encoding for speed
            "-crf", "28",            # Slightly lower quality for speed
            "-threads", "0",         # Use all available CPU threads
            "-an",                   # No audio
            "-r", "30",              # Force output to 30fps
            "-y",
            output_path
        ]
        
        logger.info(f"FFmpeg four-clip crossfade command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Four-clip crossfade stitching completed: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path)
                logger.info(f"Four-clip crossfade video created successfully, size: {final_size} bytes")
                return output_path
            else:
                logger.error("Four-clip crossfade video file was not created")
                raise Exception("Four-clip crossfade video file was not created")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Four-clip crossfade stitching failed: {e.stderr}")
            # Fallback to concat method if crossfade fails
            logger.info("Crossfade failed, falling back to concat method")
            return self._stitch_clips_with_concat_fallback(clip_paths, output_path)
    
    def _stitch_three_clips_with_crossfades(self, clip_paths: List[str], output_path: str) -> str:
        """
        Stitch three clips (intro + 1 clip + outro) with crossfade transitions
        """
        # Crossfade duration: 0.2 seconds (200ms)
        crossfade_duration = 0.2
        
        # Convert Windows backslashes to forward slashes for FFmpeg compatibility
        intro_ffmpeg = clip_paths[0].replace('\\', '/')
        clip_ffmpeg = clip_paths[1].replace('\\', '/')
        outro_ffmpeg = clip_paths[2].replace('\\', '/')
        
        # FFmpeg command with crossfade transitions between intro, clip, and outro
        # Intro (2s) -> Clip (3s) -> Outro (2s)
        # Crossfades at: 1.8s and 4.8s
        filter_complex = (
            f"[0:v]fps=fps=30:round=up,fade=t=out:st=1.8:d={crossfade_duration}[intro];"
            f"[1:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration},fade=t=out:st=2.8:d={crossfade_duration}[clip];"
            f"[2:v]fps=fps=30:round=up,fade=t=in:st=0:d={crossfade_duration}[outro];"
            f"[intro][clip]xfade=transition=fade:duration={crossfade_duration}:offset=1.8[tmp1];"
            f"[tmp1][outro]xfade=transition=fade:duration={crossfade_duration}:offset=4.6[v]"
        )
        
        cmd = [
            settings.FFMPEG_PATH,
            "-i", intro_ffmpeg,
            "-i", clip_ffmpeg,
            "-i", outro_ffmpeg,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-c:v", "libx264",      # Re-encode for filter compatibility
            "-preset", "ultrafast",  # Fastest encoding for speed
            "-crf", "28",            # Slightly lower quality for speed
            "-threads", "0",         # Use all available CPU threads
            "-an",                   # No audio
            "-r", "30",              # Force output to 30fps
            "-y",
            output_path
        ]
        
        logger.info(f"FFmpeg three-clip crossfade command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Three-clip crossfade stitching completed: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path)
                logger.info(f"Three-clip crossfade video created successfully, size: {final_size} bytes")
                return output_path
            else:
                logger.error("Three-clip crossfade video file was not created")
                raise Exception("Three-clip crossfade video file was not created")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Three-clip crossfade stitching failed: {e.stderr}")
            # Fallback to concat method if crossfade fails
            logger.info("Crossfade failed, falling back to concat method")
            return self._stitch_clips_with_concat_fallback(clip_paths, output_path)
    
    def _stitch_clips_with_concat_fallback(self, clip_paths: List[str], output_path: str) -> str:
        """
        Fallback method using concat demuxer when crossfade fails
        """
        logger.info("Using concat fallback method")
        
        # Create concat file with absolute paths
        concat_file = os.path.join(settings.TEMP_DIR, "concat_list.txt")
        with open(concat_file, "w") as f:
            for clip_path in clip_paths:
                absolute_path = os.path.abspath(clip_path)
                ffmpeg_path = absolute_path.replace('\\', '/')
                f.write(f"file '{ffmpeg_path}'\n")
        
        concat_file_ffmpeg = concat_file.replace('\\', '/')
        
        # Use concat demuxer with frame rate normalization
        cmd = [
            settings.FFMPEG_PATH,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file_ffmpeg,
            "-c:v", "libx264",  # Re-encode video
            "-an",               # No audio
            "-preset", "fast",   # Fast encoding
            "-crf", "23",        # Good quality
            "-r", "30",          # Force output to 30fps
            "-avoid_negative_ts", "make_zero",  # Handle timestamp issues
            "-fflags", "+genpts",  # Generate presentation timestamps
            "-y",
            output_path
        ]
        
        logger.info(f"FFmpeg concat fallback command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Concat fallback stitching completed: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path)
                logger.info(f"Concat fallback video created successfully, size: {final_size} bytes")
            else:
                logger.error("Concat fallback video file was not created")
            
            # Clean up concat file
            os.remove(concat_file)
            return output_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Concat fallback stitching failed: {e.stderr}")
            # Clean up on error
            if os.path.exists(concat_file):
                os.remove(concat_file)
            raise Exception(f"Concat fallback stitching failed: {e.stderr}")
    
    def _stitch_clips_with_chain_transitions(self, clip_paths: List[str], output_path: str) -> str:
        """
        Stitch 4+ clips with chain crossfade transitions
        """
        logger.info(f"Using chain transitions for {len(clip_paths)} clips")
        
        # For 4+ clips, we'll use a different approach with concat demuxer
        # This ensures all clips are included and transitions are smooth
        
        # Create concat file with absolute paths
        concat_file = os.path.join(settings.TEMP_DIR, "concat_list.txt")
        with open(concat_file, "w") as f:
            for clip_path in clip_paths:
                absolute_path = os.path.abspath(clip_path)
                ffmpeg_path = absolute_path.replace('\\', '/')
                f.write(f"file '{ffmpeg_path}'\n")
        
        # Log the concat file contents
        with open(concat_file, "r") as f:
            concat_contents = f.read()
        logger.info(f"Concat file contents:\n{concat_contents}")
        
        concat_file_ffmpeg = concat_file.replace('\\', '/')
        
        # Use concat demuxer with re-encoding for multiple clips
        # This ensures all clips are included and properly sequenced
        cmd = [
            settings.FFMPEG_PATH,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file_ffmpeg,
            "-c:v", "libx264",  # Re-encode video
            "-an",               # No audio
            "-preset", "fast",   # Fast encoding
            "-crf", "23",        # Good quality
            "-avoid_negative_ts", "make_zero",  # Handle timestamp issues
            "-fflags", "+genpts",  # Generate presentation timestamps
            "-y",
            output_path
        ]
        
        logger.info(f"FFmpeg chain concat command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Chain concat stitching completed: {result.stdout}")
            
            # Verify the output file
            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path)
                logger.info(f"Chain concat video created successfully, size: {final_size} bytes")
            else:
                logger.error("Chain concat video file was not created")
            
            # Clean up concat file
            os.remove(concat_file)
            return output_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Chain concat stitching failed: {e.stderr}")
            # Clean up on error
            if os.path.exists(concat_file):
                os.remove(concat_file)
            raise Exception(f"Chain concat stitching failed: {e.stderr}")
    
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
                    try:
                        # Try to remove individual files first
                        for root, dirs, files in os.walk(clip_dir, topdown=False):
                            for file in files:
                                try:
                                    file_path = os.path.join(root, file)
                                    os.chmod(file_path, 0o777)  # Make writable
                                    os.remove(file_path)
                                except Exception as e:
                                    logger.debug(f"Could not remove file {file}: {e}")
                            
                            for dir_name in dirs:
                                try:
                                    dir_path = os.path.join(root, dir_name)
                                    os.chmod(dir_path, 0o777)  # Make writable
                                    os.rmdir(dir_path)
                                except Exception as e:
                                    logger.debug(f"Could not remove directory {dir_name}: {e}")
                        
                        # Try to remove the main directory
                        try:
                            os.chmod(clip_dir, 0o777)  # Make writable
                            os.rmdir(clip_dir)
                            logger.debug(f"Cleaned up directory: {clip_dir}")
                        except Exception as e:
                            logger.debug(f"Could not remove main directory {clip_dir}: {e}")
                            
                    except Exception as e:
                        logger.warning(f"Failed to clean up {clip_dir}: {e}")
            
            # Clean up other temp files
            temp_files = ["stitched.mp4", "with_music.mp4", "intro.mp4", "outro.mp4"]
            for temp_file in temp_files:
                temp_path = os.path.join(settings.TEMP_DIR, temp_file)
                if os.path.exists(temp_path):
                    try:
                        os.chmod(temp_path, 0o777)  # Make writable
                        os.remove(temp_path)
                        logger.debug(f"Cleaned up temp file: {temp_path}")
                    except PermissionError as pe:
                        logger.warning(f"Permission denied cleaning up {temp_path}: {pe}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up {temp_path}: {e}")
                    
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
    

    
    def get_task_status(self, task_id: str) -> ProcessingStatus:
        """
        Get the current status of a processing task
        """
        if task_id not in self.tasks:
            raise Exception("Task not found")
        return self.tasks[task_id]
    
    def _save_tasks_to_disk(self):
        """
        Save all tasks to disk for persistence
        """
        try:
            tasks_file = os.path.join(settings.TEMP_DIR, "tasks.json")
            tasks_data = {}
            
            for task_id, task in self.tasks.items():
                tasks_data[task_id] = {
                    "task_id": task.task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "message": task.message,
                    "download_url": task.download_url,
                    "error": task.error
                }
            
            with open(tasks_file, "w", encoding="utf-8") as f:
                json.dump(tasks_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.warning(f"Failed to save tasks to disk: {e}")
    
    def _load_tasks_from_disk(self):
        """
        Load tasks from disk on startup
        """
        try:
            tasks_file = os.path.join(settings.TEMP_DIR, "tasks.json")
            if os.path.exists(tasks_file):
                with open(tasks_file, "r", encoding="utf-8") as f:
                    tasks_data = json.load(f)
                
                for task_id, task_info in tasks_data.items():
                    # Only load completed or error tasks (skip processing ones)
                    if task_info["status"] in ["completed", "error"]:
                        self.tasks[task_id] = ProcessingStatus(**task_info)
                        logger.info(f"Loaded task from disk: {task_id} - {task_info['status']}")
                        
        except Exception as e:
            logger.warning(f"Failed to load tasks from disk: {e}")
    
    def _update_task_status(self, task_id: str, status: str, progress: int, message: str, download_url: Optional[str] = None):
        """
        Update the status of a processing task and persist to disk
        """
        if task_id in self.tasks:
            self.tasks[task_id].status = status
            self.tasks[task_id].progress = progress
            self.tasks[task_id].message = message
            if download_url:
                self.tasks[task_id].download_url = download_url
            
            # Save to disk after each update
            self._save_tasks_to_disk()
        else:
            # Create new task if it doesn't exist
            self.tasks[task_id] = ProcessingStatus(
                task_id=task_id,
                status=status,
                progress=progress,
                message=message,
                download_url=download_url
            )
            # Save to disk after creating new task
            self._save_tasks_to_disk()
    
    def _create_intro_clip(self, first_clip_path: str, request: VideoRequest) -> str:
         """
         Create a 2-second blurred intro clip from the first video with title overlay
         """
         try:
             intro_path = os.path.join(settings.TEMP_DIR, "intro.mp4")
             
             # Get target dimensions based on the selected format
             format_info = settings.VIDEO_FORMATS[request.format]
             target_width = format_info["width"]
             target_height = format_info["height"]
             
             # Adjust font size based on format (smaller for vertical formats)
             if request.format == "shorts":
                 font_size = 48  # Smaller font for vertical format
             else:
                 font_size = 72  # Standard font size for horizontal formats
            
            # Normalize font path for FFmpeg (use forward slashes)
            fontfile = os.path.join(settings.FONT_DIR, settings.DEFAULT_FONT).replace('\\', '/')
             
             # Extract 2 seconds from the beginning of the first clip
             # Apply heavy blur effect and overlay title text
             # Use the same formatting logic as the main video
             if request.format == "shorts":
                 # For YouTube Shorts: Crop from sides, maintain center content
                 filter_complex = (
                     f"crop=iw*9/16:ih:(iw-iw*9/16)/2:0,"  # Crop to 9:16 ratio, center horizontally
                     f"scale={target_width}:{target_height},"  # Scale to target dimensions
                     f"boxblur=20:20,"  # Apply blur effect
                     f"drawtext=text='{request.title}':fontfile={fontfile}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
                 )
             elif request.format == "instagram":
                 # For Instagram: Crop to square, center
                 filter_complex = (
                     f"crop=min(iw,ih):min(iw,ih):(iw-min(iw,ih))/2:(ih-min(iw,ih))/2,"  # Crop to square, center
                     f"scale={target_width}:{target_height},"  # Scale to target dimensions
                     f"boxblur=20:20,"  # Apply blur effect
                     f"drawtext=text='{request.title}':fontfile={fontfile}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
                 )
             else:
                 # For YouTube: Standard scaling with padding
                 filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black,boxblur=20:20,drawtext=text='{request.title}':fontfile={fontfile}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
             
             cmd = [
                 settings.FFMPEG_PATH,
                 "-i", first_clip_path,
                 "-t", "2",  # 2 seconds duration
                 "-vf", filter_complex,
                 "-c:v", "libx264",
                 "-preset", "ultrafast",  # Fastest encoding for speed
                 "-crf", "28",            # Slightly lower quality for speed
                 "-threads", "0",         # Use all available CPU threads
                 "-an",  # No audio
                 "-y",
                 intro_path
             ]
             
             logger.info(f"Creating intro clip: {' '.join(cmd)}")
             logger.info(f"Intro output path: {intro_path}")
             logger.info(f"First clip path: {first_clip_path}")
             logger.info(f"First clip exists: {os.path.exists(first_clip_path)}")
             
             result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
             logger.info(f"Intro clip created successfully: {result.stdout}")
             
             # Verify the intro file was created
             if os.path.exists(intro_path):
                 intro_size = os.path.getsize(intro_path)
                 logger.info(f"Intro clip created at {intro_path}, size: {intro_size} bytes")
             else:
                 logger.error(f"Intro clip was not created at {intro_path}")
             
             return intro_path
             
         except Exception as e:
             logger.error(f"Failed to create intro clip: {e}")
             # Fallback: return first clip if intro creation fails
             return first_clip_path
    
    def _create_outro_clip(self, first_clip_path: str, request: VideoRequest) -> str:
         """
         Create a 2-second blurred outro clip from the first video with subscribe message
         """
         try:
             outro_path = os.path.join(settings.TEMP_DIR, "outro.mp4")
             
             # Get target dimensions based on the selected format
             format_info = settings.VIDEO_FORMATS[request.format]
             target_width = format_info["width"]
             target_height = format_info["height"]
             
             # Adjust font size based on format (smaller for vertical formats)
             if request.format == "shorts":
                 font_size = 48  # Smaller font for vertical format
             else:
                 font_size = 72  # Standard font size for horizontal formats
             
             # Extract 2 seconds from the beginning of the first clip
             # Apply heavy blur effect and overlay subscribe message
             # Use the same formatting logic as the main video
             subscribe_text = "SUBSCRIBE FOR MORE!"
             
             if request.format == "shorts":
                 # For YouTube Shorts: Crop from sides, maintain center content
                 filter_complex = (
                     f"crop=iw*9/16:ih:(iw-iw*9/16)/2:0,"  # Crop to 9:16 ratio, center horizontally
                     f"scale={target_width}:{target_height},"  # Scale to target dimensions
                     f"boxblur=20:20,"  # Apply blur effect
                     f"drawtext=text='{subscribe_text}':fontfile={os.path.join(settings.FONT_DIR, settings.DEFAULT_FONT).replace('\\', '/')}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
                 )
             elif request.format == "instagram":
                 # For Instagram: Crop to square, center
                 filter_complex = (
                     f"crop=min(iw,ih):min(iw,ih):(iw-min(iw,ih))/2:(ih-min(iw,ih))/2,"  # Crop to square, center
                     f"scale={target_width}:{target_height},"  # Scale to target dimensions
                     f"boxblur=20:20,"  # Apply blur effect
                     f"drawtext=text='{subscribe_text}':fontfile={os.path.join(settings.FONT_DIR, settings.DEFAULT_FONT).replace('\\', '/')}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
                 )
             else:
                 # For YouTube: Standard scaling with padding
                 filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black,boxblur=20:20,drawtext=text='{subscribe_text}':fontfile={os.path.join(settings.FONT_DIR, settings.DEFAULT_FONT).replace('\\', '/')}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
             
             cmd = [
                 settings.FFMPEG_PATH,
                 "-i", first_clip_path,
                 "-t", "2",  # 2 seconds duration
                 "-vf", filter_complex,
                 "-c:v", "libx264",
                 "-preset", "ultrafast",  # Fastest encoding for speed
                 "-crf", "28",            # Slightly lower quality for speed
                 "-threads", "0",         # Use all available CPU threads
                 "-an",  # No audio
                 "-y",
                 outro_path
             ]
             
             logger.info(f"Creating outro clip: {' '.join(cmd)}")
             logger.info(f"Outro output path: {outro_path}")
             logger.info(f"First clip path: {first_clip_path}")
             logger.info(f"First clip exists: {os.path.exists(first_clip_path)}")
             
             result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
             logger.info(f"Outro clip created successfully: {result.stdout}")
             
             # Verify the outro file was created
             if os.path.exists(outro_path):
                 outro_size = os.path.getsize(outro_path)
                 logger.info(f"Outro clip created at {outro_path}, size: {outro_size} bytes")
             else:
                 logger.error(f"Outro clip was not created at {outro_path}")
             
             return outro_path
             
         except Exception as e:
             logger.error(f"Failed to create outro clip: {e}")
             # Fallback: return first clip if outro creation fails
             return first_clip_path

    def _validate_ffmpeg_installation(self):
        """
        Validate that FFmpeg is properly installed and accessible
        """
        try:
            logger.info(f"Validating FFmpeg installation at: {settings.FFMPEG_PATH}")
            
            # Check if FFmpeg executable exists
            if not os.path.exists(settings.FFMPEG_PATH):
                logger.error(f"FFmpeg executable not found at: {settings.FFMPEG_PATH}")
                logger.error("Please install FFmpeg or set FFMPEG_PATH environment variable")
                logger.error("Common Windows paths: C:\\ffmpeg\\bin\\ffmpeg.exe")
                logger.error("Common Unix paths: /usr/bin/ffmpeg, /usr/local/bin/ffmpeg")
                return
            
            # Test if FFmpeg can run
            try:
                result = subprocess.run([settings.FFMPEG_PATH, "-version"], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    version_line = result.stdout.split('\n')[0]
                    logger.info(f"FFmpeg validation successful: {version_line}")
                else:
                    logger.error(f"FFmpeg validation failed with return code: {result.returncode}")
                    logger.error(f"FFmpeg stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.error("FFmpeg validation timed out")
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg validation failed: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during FFmpeg validation: {e}")
                
        except Exception as e:
            logger.error(f"Error during FFmpeg validation: {e}")
