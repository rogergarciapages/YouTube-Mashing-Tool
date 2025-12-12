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
import ssl
import urllib3
import math

# On Windows, recommending certifi-win32 can resolve Python SSL verification issues by
# using the Windows Certificate Store. Try to import it early so its effects apply.
_CERTIFI_WIN32_AVAILABLE = False
try:
    import certifi
    try:
        import certifi_win32  # type: ignore
        _CERTIFI_WIN32_AVAILABLE = True
        # Refresh certifi.where() result (certifi_win32 patches CA selection on import)
        ca_path = certifi.where()
        os.environ['SSL_CERT_FILE'] = ca_path
        os.environ['REQUESTS_CA_BUNDLE'] = ca_path
        logger = logging.getLogger(__name__)
        logger.info(f"certifi-win32 detected, using CA bundle from Windows store via certifi: {ca_path}")
    except Exception:
        # certifi is available but certifi-win32 is not installed
        pass
except Exception:
    # certifi not available; we'll attempt to import it later where needed
    pass


# SSL/Certifi handling is managed locally in specific methods or via env vars if needed
# We removed the global ssl._create_unverified_context override locally to avoid security risks
# unless explicitly needed (e.g. for yt-dlp internal handling).


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
    
    async def process_video_request(self, request: VideoRequest, task_id: str):
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
            # Create task directory
            task_dir = os.path.join(settings.OUTPUT_DIR, task_id)
            os.makedirs(task_dir, exist_ok=True)

            # Process clips from items
            processed_clips = []
            total_clips = sum(len(item.clips) for item in request.items)
            clips_processed_count = 0
            
            for item_idx, item in enumerate(request.items):
                logger.info(f"Processing Item {item_idx+1}: {item.title}")
                
                for clip_idx, clip in enumerate(item.clips):
                    try:
                        # Update progress
                        # 70% of progress bar allocated to clip processing
                        if total_clips > 0:
                            progress = int((clips_processed_count / total_clips) * 70)
                        else:
                            progress = 0
                            
                        self._update_task_status(
                            task_id, 
                            "processing", 
                            progress, 
                            f"Processing Item '{item.title}' ({clip_idx+1}/{len(item.clips)})"
                        )
                        
                        # Process individual clip
                        # Pass a unique index based on total count to avoid overwrites if using index-based naming
                        processed_clip = await self._process_single_clip(task_id, clip, clips_processed_count, request, task_dir)
                        processed_clips.append(processed_clip)
                        clips_processed_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing clip {clip_idx} in item {item.title}: {e}")
                        # We continue processing other clips instead of failing completely?
                        # Or fail hard? For now, let's try to continue but log error.
                        # Actually, if a clip fails, the video might be incomplete.
                        # Let's note it but continue.
                        continue
            
            # Update progress
            self._update_task_status(task_id, "processing", 80, "Stitching clips and outro together...")
            
            # Skip intro - start directly with first content clip
            self._update_task_status(task_id, "processing", 77, "Creating outro sequence...")
            outro_clip = self._create_outro_clip(processed_clips[0], request)
            
            # Combine clips + outro (no intro)
            all_clips = processed_clips + [outro_clip]
            
            # Debug logging for clip combination
            logger.info(f"Combining clips for stitching (intro skipped):")
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
    
    async def _process_single_clip(self, task_id: str, clip: ClipRequest, index: int, request: VideoRequest, task_dir: str) -> str:
        """
        Process a single clip: download, generate summary, overlay text, format
        """
        try:
            # Generate temporary filenames
            temp_dir = os.path.join(settings.TEMP_DIR, f"task_{task_id}", f"clip_{index}")
            os.makedirs(temp_dir, exist_ok=True)
            
            raw_clip = os.path.join(temp_dir, "raw.mp4")
            styled_clip = os.path.join(temp_dir, "styled.mp4")
            final_clip = os.path.join(temp_dir, "final.mp4")
            
            # 1. Generate AI summary (First, to determine duration)
            summary = self._generate_summary(clip)
            
            # Calculate duration based on word count
            # Formula: ceil(word_count * time_per_word)
            # Use input keywords/text for duration calculation to respect user intent, 
            # as AI summary might be shorter (condensed).
            if clip.custom_text:
                count_source = clip.custom_text
            elif clip.keywords:
                count_source = clip.keywords
            else:
                count_source = summary

            # handle comma-separated keywords
            clean_source = count_source.replace(',', ' ')
            word_count = len(clean_source.split())
            
            calculated_duration = math.ceil(word_count * settings.SUBTITLE_WORD_DURATION)
            
            # Ensure a sensible minimum duration
            if calculated_duration < 2:
                calculated_duration = 2 # Minimum 2 seconds for technical stability
            
            logger.info(f"Calculated duration for clip {index}: {calculated_duration}s (Words: {word_count} from input)")
            
            # 2. Download YouTube clip - pass duration
            self._download_clip(clip.url, clip.timestamp, raw_clip, calculated_duration, request.download_config)
            
            # 3. Overlay text
            # Note: _overlay_text calls ffmpeg which re-encodes. 
            # We already have raw_clip of correct duration?
            # Yes, _download_clip cuts it to duration.
            
            # We need to pass the summary we already generated
            # Refactor _overlay_text or just pass it?
            # _overlay_text signature: (self, input_path: str, output_path: str, text: str, request: VideoRequest)
            # It already takes text. Perfect.
            
            self._overlay_text(raw_clip, styled_clip, summary, request)
            
            # 4. Format video to target dimensions
            self._format_video(styled_clip, final_clip, request.format)
            
            # 5. Normalize timestamps to ensure proper concatenation
            normalized_clip = self._normalize_timestamps(final_clip, temp_dir)
            
            return normalized_clip
            
        except Exception as e:
            logger.error(f"Error processing clip {index}: {e}")
            raise
    
    def _download_clip(self, url: str, timestamp: int, output_path: str, duration: float, download_config=None):
        """
        Download a clip from YouTube starting at the specified timestamp with specific duration
        """
        from utils.download_strategies import download_with_fallbacks
        
        url_str = str(url)
        temp_dir = os.path.dirname(output_path)
        temp_video = os.path.join(temp_dir, f"temp_{os.path.basename(output_path)}")
        
        logger.info(f"Downloading clip from: {url_str} at timestamp {timestamp}s for {duration}s")
        
        # Try to download the full video using fallback strategies
        try:
            if not download_with_fallbacks(url_str, temp_video + ".mp4", timeout_base=180):
                raise Exception("All download strategies failed - video may be DRM-protected, geo-blocked, or age-restricted. Try uploading browser cookies.")
        except Exception as download_error:
            logger.error(f"Download failed: {download_error}")
            raise Exception(f"yt-dlp download failed: {str(download_error)}")
            
        # The download_with_fallbacks function downloads to temp_video + ".mp4"
        actual_temp_file = temp_video + ".mp4"
        
        if not os.path.exists(actual_temp_file):
            raise Exception(f"Downloaded video file not found at: {actual_temp_file}")

        logger.info(f"Processing downloaded video: {actual_temp_file}")
            
        # Now extract the exact segment using FFmpeg
        cmd = [
            settings.FFMPEG_PATH,
            "-fflags", "+discardcorrupt",  # Handle corrupt frames from seeking
            "-i", actual_temp_file,
            "-ss", str(timestamp),  # Start at timestamp
            "-t", str(duration),    # Dynamic duration

            "-c:v", "libx264",       # Re-encode with h264 for valid stream metadata
            "-preset", settings.FFMPEG_PRESET,  # Balance speed/quality
            "-crf", str(settings.FFMPEG_CRF),   # Quality based on settings
            "-an",                   # Remove audio completely (mute)
            "-y",                    # Overwrite output
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
            # Clean up on error
            if os.path.exists(actual_temp_file):
                try:
                    os.remove(actual_temp_file)
                except Exception:
                    pass
            raise Exception(f"FFmpeg command failed: {e.stderr}")
        except FileNotFoundError as e:
            logger.error(f"File not found error: {e}")
            raise Exception(f"File not found: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during FFmpeg execution: {e}")
            # Clean up on error
            if os.path.exists(actual_temp_file):
                try:
                    os.remove(actual_temp_file)
                except Exception:
                    pass
            raise Exception(f"FFmpeg execution error: {e}")

        # Clean up temporary file
        if os.path.exists(actual_temp_file):
            try:
                os.remove(actual_temp_file)
            except Exception:
                pass

    def _cleanup_temp_files(self, processed_clips: List[str]):
        """
        Cleanup temporary files generated during processing
        """
        try:
            # Delete clip directories
            for clip_path in processed_clips:
                clip_dir = os.path.dirname(clip_path)
                if os.path.exists(clip_dir) and "temp" in clip_dir:
                    shutil.rmtree(clip_dir, ignore_errors=True)
                    logger.info(f"Cleaned up temp directory: {clip_dir}")
            
            # Additional cleanup of temp dir top-level files
            for file in os.listdir(settings.TEMP_DIR):
                file_path = os.path.join(settings.TEMP_DIR, file)
                if os.path.isfile(file_path):
                    # Check if file is old (greater than 1 hour)
                    if time.time() - os.path.getmtime(file_path) > 3600:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old temp file: {file}")
                        
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")
    
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
        Overlay text on video using FFmpeg with word-by-word dynamic display (MrBeast style)
        """
        # Cleanup text: remove extra spaces and newlines
        clean_text = " ".join(text.split())
        words = clean_text.split()
        
        if not words:
            # Just copy input to output if no text
            shutil.copy2(input_path, output_path)
            return

        # Use custom font with black outline (Mr Beast style)
        font_path = os.path.join(settings.FONT_DIR, settings.DEFAULT_FONT)
        # Convert paths for FFmpeg
        # Windows absolute paths (C:/...) need the colon escaped (C\:/...) in filter strings
        font_path_ffmpeg = font_path.replace('\\', '/').replace(':', '\\\\:')
        
        # Word duration setup
        word_duration = settings.SUBTITLE_WORD_DURATION
        
        # Create filter chain
        filters = []
        
        # Base font config
        font_size = settings.SUBTITLE_FONT_SIZE
        y_pos = f"h*{settings.SUBTITLE_Y_POS}"
        
        current_time = 0.0
        
        # Process word by word
        for i, word in enumerate(words):
            start_time = i * word_duration
            end_time = start_time + word_duration
            
            # Escape chars for FFmpeg text
            # specialized escaping for drawtext: ' -> \', : -> \:, \ -> \\
            safe_word = word.replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'")
            
            # Create drawtext filter for this word
            # enable=between(t, start, end) makes it appear only during that window
            # box=1:boxcolor=black@0.5:boxborderw=10 -> Optional background box for clarity? 
            # User asked for "Mr Beast fashion", usually just thick stroke.
            
            # centering: x=(w-text_w)/2
            filter_str = (
                f"drawtext=fontfile='{font_path_ffmpeg}':"
                f"text='{safe_word}':"
                f"fontcolor=yellow:"  # MrBeast style typically uses White or Yellow with black stroke
                f"fontsize={font_size}:"
                f"x=(w-text_w)/2:"
                f"y={y_pos}-text_h/2:"
                f"borderw=5:bordercolor=black:"
                f"shadowx=2:shadowy=2:shadowcolor=black@0.5:"  # Drop shadow depth
                f"enable='between(t,{start_time},{end_time})'"
            )
            filters.append(filter_str)
            
        # Combine all drawtext filters with commas
        filter_complex = ",".join(filters)
        
        # NOTE: If text is too long (too many filters), command line might exceed limits.
        # Ideally we'd burn this via a subtitle file (.ass/.srt) but drawtext allows precise animation control easily.
        # For < 50 words this is fine.
        
        cmd = [
            settings.FFMPEG_PATH,
            "-i", input_path,
            "-vf", filter_complex,
            "-an",               # Remove audio (mute)
            "-y",  # Overwrite output file
            output_path
        ]
        
        try:
            logger.info(f"Applying dynamic text overlay with {len(words)} words...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"FFmpeg dynamic overlay completed")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg text overlay failed: {e.stderr}")
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
        - YouTube Shorts (9:16): Crop width from sides, maintain height, center content
        - Instagram (1:1): Crop to square, center content, then scale  
        - YouTube (16:9): Scale with padding to maintain aspect ratio
        
        This ensures videos are properly cropped instead of squeezed/stretched.
        """
        format_info = settings.VIDEO_FORMATS[format_type]
        target_width = format_info["width"]
        target_height = format_info["height"]
        
        logger.info(f"Formatting video to {target_width}x{target_height} ({format_type})")
        
        # Get input video dimensions using FFprobe with a simpler, more reliable approach
        input_width = None
        input_height = None
        
        try:
            import json
            ffprobe_path = settings.FFMPEG_PATH.replace("ffmpeg.exe", "ffprobe.exe")
            
            if os.path.exists(ffprobe_path):
                probe_cmd = [
                    ffprobe_path,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-select_streams", "v:0",
                    input_path
                ]
                
                probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
                
                if probe_result.returncode == 0:
                    try:
                        video_info = json.loads(probe_result.stdout)
                        if 'streams' in video_info and video_info['streams']:
                            stream = video_info['streams'][0]
                            input_width = int(stream.get('width', 0))
                            input_height = int(stream.get('height', 0))
                            logger.info(f"FFprobe detected: {input_width}x{input_height}")
                    except Exception as e:
                        logger.warning(f"Could not parse ffprobe output: {e}")
        except Exception as e:
            logger.warning(f"FFprobe not available: {e}")
        
        # Fallback: extract dimensions from FFmpeg output
        if not input_width or not input_height:
            try:
                cmd = [settings.FFMPEG_PATH, "-i", input_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                # FFmpeg outputs to stderr
                import re
                match = re.search(r'(\d+)x(\d+)', result.stderr)
                if match:
                    input_width = int(match.group(1))
                    input_height = int(match.group(2))
                    logger.info(f"FFmpeg detected: {input_width}x{input_height}")
            except Exception as e:
                logger.warning(f"Could not extract dimensions from FFmpeg: {e}")
        
        # If we still can't get dimensions, use default 16:9
        if not input_width or not input_height or input_width == 0 or input_height == 0:
            logger.warning(f"Could not detect input dimensions, assuming 16:9 (1920x1080)")
            input_width = 1920
            input_height = 1080
        
        input_ratio = input_width / input_height if input_height > 0 else 1.778
        target_ratio = target_width / target_height
        
        logger.info(f"Input video dimensions: {input_width}x{input_height} (ratio: {input_ratio:.3f})")
        logger.info(f"Target dimensions: {target_width}x{target_height} (ratio: {target_ratio:.3f})")
        
        # Check if aspect ratios are close enough (within 0.1 tolerance)
        if abs(input_ratio - target_ratio) < 0.1:
            logger.info(f"Video is already in target format ({format_type}), skipping formatting")
            shutil.copy2(input_path, output_path)
            return
        
        # Build FFmpeg command with improved aspect ratio handling
        if format_type == "shorts":
            # For YouTube Shorts (9:16): Crop from sides to create center-focused vertical video
            # This maintains the center content and crops equally from left and right edges
            # Formula: crop_width = input_height * (9/16), x_offset = (input_width - crop_width) / 2
            filter_complex = (
                f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"  # Crop to 9:16 ratio (height * 9/16), center horizontally
                f"scale={target_width}:{target_height}"  # Scale to target dimensions
            )
            logger.info(f"YouTube Shorts (9:16) crop formula: crop=ih*9/16:ih:(iw-ih*9/16)/2:0")
            logger.info(f"This crops width to (height × 9/16) and centers content horizontally")
            logger.info(f"Example: 1920x1080 -> crop to 607.5x1080 -> scale to 1080x1920")
            
        elif format_type == "instagram":
            # For Instagram (1:1): Crop to square, scale to 1080x1080
            filter_complex = (
                f"crop=min(iw,ih):min(iw,ih):(iw-min(iw,ih))/2:(ih-min(iw,ih))/2,"  # Crop to square, center
                f"scale={target_width}:{target_height}"  # Scale to target dimensions
            )
            logger.info(f"Instagram (1:1) crop: center-focused square crop")
            
        else:
            # For YouTube (16:9): Use standard scaling with padding
            filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black"
            logger.info(f"YouTube (16:9) format: scale with black padding")
        
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
            logger.info(f"Video formatting completed successfully")
            
            # Verify the output file
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"Formatted video created at {output_path}, size: {file_size} bytes")
            else:
                logger.error(f"Formatted video was not created at {output_path}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Video formatting failed: {e.stderr}")
            raise Exception(f"Video formatting failed: {e.stderr}")
    
    async def _get_clip_duration(self, clip_path: str) -> float:
        """
        Get exact duration of a video clip using ffprobe
        """
        try:
            cmd = [
                settings.FFMPEG_PATH.replace("ffmpeg.exe", "ffprobe.exe"),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                clip_path
            ]
            
            # Run in thread pool to avoid blocking async loop? 
            # Actually process_video_request is async but calls this synchronously?
            # subprocess.run is blocking. Ideally should use asyncio.create_subprocess_exec
            # For now, keep it simple but functional.
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            logger.error(f"Failed to get duration for {clip_path}: {e}")
            # Fallback: try to guess or return 0 (will cause issues)
            # If we fail, maybe default to 3.0?
            return 3.0

    def _stitch_clips(self, clip_paths: List[str], request: VideoRequest) -> str:
        """
        Stitch multiple clips together using FFmpeg with crossfade transitions
        Dynamically handles varying clip durations.
        """
        if not clip_paths:
            raise ValueError("No clips to stitch")

        # Output path for stitched video
        stitched_path = os.path.join(settings.TEMP_DIR, "stitched.mp4")
        
        if len(clip_paths) == 1:
            logger.info("Single clip detected, copying directly")
            shutil.copy2(clip_paths[0], stitched_path)
            return stitched_path

        # 1. Get durations for all clips
        clip_durations = []
        for path in clip_paths:
            # We use a synchronous hack here since _stitch_clips is called synchronously in the main loop currently
            # (Main loop calls `final_video = self._stitch_clips(all_clips, request)`)
            # If we want async, we need to refactor _stitch_clips to be async.
            # But getting info via subprocess is fast enough for now.
            try:
                # Re-implement simple probe here to avoid async complexity in this sync method
                ffprobe = settings.FFMPEG_PATH.replace("ffmpeg.exe", "ffprobe.exe")
                cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                d = float(res.stdout.strip())
                clip_durations.append(d)
                logger.info(f"Clip {os.path.basename(path)} duration: {d}s")
            except Exception as e:
                logger.warning(f"Could not probe duration for {path}, assuming 3.0s: {e}")
                clip_durations.append(3.0)

        # 2. Build Filter Complex
        return self._stitch_clips_dynamic(clip_paths, clip_durations, stitched_path)

    def _stitch_clips_dynamic(self, clip_paths: List[str], durations: List[float], output_path: str) -> str:
        """
        Generic function to stitch any number of clips with crossfades based on actual durations.
        """
        crossfade_duration = 0.5  # 0.5s crossfade
        
        # Prepare inputs
        inputs = []
        for i, path in enumerate(clip_paths):
            path_fixed = path.replace('\\', '/')
            inputs.extend(["-i", path_fixed])
        
        filter_parts = []
        
        # 1. Prepare each stream (fade in/out for opacity, though xfade mostly handles the transition, 
        # distinct fade filters are often used for visual smoothness or if xfade isn't sufficient).
        # Actually xfade takes 'offset'. We typically don't need manual fade in/out UNLESS
        # we want a specific look. Standard xfade just dissolves from A to B.
        # Let's simple use [v0][v1]xfade...
        
        # BUT: ffmpeg xfade stream consumption is tricky.
        # [0][1]xfade[q1]; [q1][2]xfade[q2]...
        
        # We also need to normalize inputs (fps, scale) to ensure xfade works.
        # xfade requires identical resolution/framerate.
        # We assume _format_video handled resolution.
        # we should enforce fps=30 just in case.
        
        for i in range(len(clip_paths)):
            # Force timestamp reset? pts=0?
            filter_parts.append(f"[{i}:v]fps=30,settb=AVTB,setpts=PTS-STARTPTS[v{i}];")
            
        # Build xfade chain
        current_stream = "[v0]"
        current_offset = 0.0
        
        # Offset calculation:
        # Clip 0 starts at 0. Ends at D0.
        # Clip 1 starts at D0 - Crossfade.
        # xfade offset is the timestamp in the FIRST stream where transition begins.
        # For first transition: offset = D0 - C.
        # Resulting stream length = D0 + D1 - C.
        # Next interaction starts at (ResultLength) - C = D0 + D1 - 2C.
        
        # General formula for offset of i-th transition (joining clip i and i+1):
        # Accumulate (Duration_k - Crossfade) for k=0 to i.
        
        xfade_chain = []
        accumulated_offset = 0.0
        
        for i in range(len(clip_paths) - 1):
            d1 = durations[i]
            
            # Safety: if clip is shorter than crossfade, reduce crossfade
            actual_crossfade = min(crossfade_duration, d1 / 2, durations[i+1] / 2)
            
            offset = accumulated_offset + d1 - actual_crossfade
            
            next_stream = f"[v{i+1}]"
            out_stream = f"[x{i}]" if i < len(clip_paths) - 2 else "[out]"
            
            xfade_cmd = f"{current_stream}{next_stream}xfade=transition=fade:duration={actual_crossfade}:offset={offset}{out_stream}"
            xfade_chain.append(xfade_cmd)
            
            current_stream = out_stream
            accumulated_offset = offset # The offset for the NEXT transition is relative to the start of the *first* clip in the chain?
            # WAIT. xfade offset is relative to the START of the FIRST input stream.
            # But the first input stream for the 2nd xfade is the RESULT of the 1st xfade.
            # So the timebase is consistent?
            # Yes, if we chain [q1][v2]xfade, the offset refers to timestamp in [q1].
            # [q1] effectively starts at 0.
            # The length of [q1] is (D0 + D1 - C).
            # We want to overlap [v2] at the end of [q1].
            # So offset = Length([q1]) - C.
            # = (D0 + D1 - C) - C = D0 + D1 - 2C.
            
            # So we accumulate (Duration - Crossfade)
            pass
            
        # Let's rebuild the loop with correct logic
        filter_complex_str = ""
        # Inputs preparation
        for i in range(len(clip_paths)):
            filter_complex_str += f"[{i}:v]fps=30,settb=AVTB,setpts=PTS-STARTPTS[v{i}];"
            
        prev_stream = "[v0]"
        total_duration_so_far = 0.0
        
        for i in range(len(clip_paths) - 1):
            d_current = durations[i]
            d_next = durations[i+1]
            actual_crossfade = min(crossfade_duration, d_current/2.1, d_next/2.1) # 2.1 divisor to ensure we don't consume entire clip
            
            # Offset is where the crossfade STARTS in the `prev_stream` timeline.
            # If i==0: prev_stream is v0 (len D0). Offset = D0 - C.
            # If i==1: prev_stream is result of 0 (len D0+D1-C). Offset = CurLen - C.
            
            if i == 0:
                current_offset = d_current - actual_crossfade
            else:
                current_offset += d_current - actual_crossfade
                
            out_label = f"[res{i}]" if i < len(clip_paths) - 2 else "[final]"
            
            filter_complex_str += f"{prev_stream}[v{i+1}]xfade=transition=fade:duration={actual_crossfade}:offset={current_offset}{out_label};"
            prev_stream = out_label

        # Clean trailing semicolon
        if filter_complex_str.endswith(";"):
            filter_complex_str = filter_complex_str[:-1]

        cmd = [
            settings.FFMPEG_PATH,
        ] + inputs + [
            "-filter_complex", filter_complex_str,
            "-map", "[final]",
            "-c:v", "libx264",
            "-preset", settings.FFMPEG_PRESET,
            "-crf", str(settings.FFMPEG_CRF),
            "-an",
            "-y",
            output_path
        ]
        
        logger.info(f"Dynamic Stitch Command: {' '.join(cmd)}")
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Stitched video created at {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Stitching failed: {e.stderr}")
            # Fallback to concat demuxer if filter complex fails (robustness)
            logger.warning("Dynamic stitching failed, falling back to concat demuxer (no transitions)")
            return self._stitch_clips_with_concat_fallback(clip_paths, output_path)

    def _stitch_clips_with_concat_fallback(self, clip_paths: List[str], output_path: str) -> str:
        """
        Fallback method using concat demuxer - no transitions but robust
        """
        # Create input text file
        list_path = os.path.join(settings.TEMP_DIR, "concat_list.txt")
        with open(list_path, 'w', encoding='utf-8') as f:
            for path in clip_paths:
                # Escape path for FFmpeg concat file
                safe_path = path.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")
        
        cmd = [
            settings.FFMPEG_PATH,
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            "-y",
            output_path
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
        
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

            # Normalize font path for FFmpeg (use forward slashes)
            fontfile = os.path.join(settings.FONT_DIR, settings.DEFAULT_FONT).replace('\\', '/')

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
                    f"drawtext=text='{subscribe_text}':fontfile={fontfile}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
                )
            elif request.format == "instagram":
                # For Instagram: Crop to square, center
                filter_complex = (
                    f"crop=min(iw,ih):min(iw,ih):(iw-min(iw,ih))/2:(ih-min(iw,ih))/2,"  # Crop to square, center
                    f"scale={target_width}:{target_height},"  # Scale to target dimensions
                    f"boxblur=20:20,"  # Apply blur effect
                    f"drawtext=text='{subscribe_text}':fontfile={fontfile}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"
                )
            else:
                # For YouTube: Standard scaling with padding
                filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black,boxblur=20:20,drawtext=text='{subscribe_text}':fontfile={fontfile}:fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.4-text_h/2:borderw=6:bordercolor=black"

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
