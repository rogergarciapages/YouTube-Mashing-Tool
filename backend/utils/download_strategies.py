"""
Multiple YouTube download strategies to bypass blocking and DRM protection.
Falls back through: yt-dlp (standard) → yt-dlp (geo-bypass) → pytube → external API
"""

import os
import sys
import subprocess
import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)


def try_yt_dlp_standard(url: str, output_path: str, timeout: int = 180) -> bool:
    """
    Try downloading with yt-dlp using standard options.
    Returns True if successful, False otherwise.
    """
    try:
        logger.info(f"[Strategy 1/4] Attempting yt-dlp standard download: {url}")
        
        env = os.environ.copy()
        try:
            import certifi
            env['SSL_CERT_FILE'] = certifi.where()
            env['REQUESTS_CA_BUNDLE'] = certifi.where()
        except:
            env['PYTHONHTTPSVERIFY'] = '0'
        
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-warnings", "--no-color",
            "-f", "bestvideo[height>=720][ext=mp4]/bestvideo[height>=720]/best[height>=720]/best[ext=mp4]/best",
            "-o", output_path,
            "--retries", "5",
            "--socket-timeout", "30",
            "--http-chunk-size", "1048576",
            "--no-check-certificates",
            "-q",  # Quiet mode
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=True)
        logger.info("[Strategy 1/4] ✓ yt-dlp standard succeeded")
        return True
    except Exception as e:
        logger.warning(f"[Strategy 1/4] ✗ yt-dlp standard failed: {str(e)[:100]}")
        return False


def try_yt_dlp_with_scraping(url: str, output_path: str, timeout: int = 300) -> bool:
    """
    Try yt-dlp with aggressive scraping and geo-bypass options.
    """
    try:
        logger.info(f"[Strategy 2/4] Attempting yt-dlp with scraping extractors: {url}")
        
        env = os.environ.copy()
        try:
            import certifi
            env['SSL_CERT_FILE'] = certifi.where()
        except:
            env['PYTHONHTTPSVERIFY'] = '0'
        
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-warnings", "--no-color",
            "-f", "best[height<=480]/best",
            "-o", output_path,
            "--retries", "15",
            "--socket-timeout", "60",
            "--http-chunk-size", "1048576",
            "--skip-unavailable-fragments",
            "--no-check-certificates",
            "--geo-bypass",
            "--geo-bypass-country", "US",
            "--fragment-retries", "15",
            "--extractor-args", "youtube:player_client=web,android",  # Try different clients
            "-q",  # Quiet mode
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=True)
        logger.info("[Strategy 2/4] ✓ yt-dlp scraping succeeded")
        return True
    except Exception as e:
        logger.warning(f"[Strategy 2/4] ✗ yt-dlp scraping failed: {str(e)[:100]}")
        return False


def try_pytube_download(url: str, output_path: str) -> bool:
    """
    Try downloading with pytube library as fallback.
    """
    try:
        logger.info(f"[Strategy 3/4] Attempting pytube download: {url}")
        
        from pytube import YouTube
        from pytube.exceptions import AgeRestrictedError, RegionBlocked
        
        # Extract video ID from various URL formats
        if "youtu.be/" in url:
            video_id = url.split("youtu.be/")[-1].split("?")[0]
        elif "youtube.com/watch?v=" in url:
            video_id = url.split("v=")[-1].split("&")[0]
        else:
            video_id = url
        
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        
        # Try to get the best stream available
        stream = yt.streams.get_highest_resolution()
        if stream is None:
            stream = yt.streams.first()
        
        if stream:
            logger.info(f"[Strategy 3/4] Downloading with pytube: {stream.resolution or 'unknown resolution'}")
            stream.download(output_path=os.path.dirname(output_path), filename=os.path.basename(output_path))
            logger.info("[Strategy 3/4] ✓ pytube download succeeded")
            return True
        else:
            logger.warning("[Strategy 3/4] ✗ pytube: No streams available")
            return False
            
    except ImportError:
        logger.warning("[Strategy 3/4] ✗ pytube not installed")
        return False
    except Exception as e:
        logger.warning(f"[Strategy 3/4] ✗ pytube failed: {str(e)[:100]}")
        return False


def try_external_api(url: str, output_path: str) -> bool:
    """
    Try downloading using external API services.
    Falls back to popular free YouTube download APIs.
    """
    try:
        logger.info(f"[Strategy 4/4] Attempting external download API: {url}")
        
        # Extract video ID
        if "youtu.be/" in url:
            video_id = url.split("youtu.be/")[-1].split("?")[0]
        elif "youtube.com/watch?v=" in url:
            video_id = url.split("v=")[-1].split("&")[0]
        else:
            video_id = url
        
        # Try multiple API endpoints (some may be rate-limited or down)
        apis = [
            f"https://api.cobalt.tools/api/json",  # cobalt.tools API
        ]
        
        for api_url in apis:
            try:
                logger.info(f"[Strategy 4/4] Trying API: {api_url}")
                
                if "cobalt" in api_url:
                    # cobalt.tools format
                    payload = {
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "vQuality": "360",
                        "aFormat": "mp4"
                    }
                    response = requests.post(api_url, json=payload, timeout=60)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if "url" in data:
                            download_url = data["url"]
                            logger.info(f"[Strategy 4/4] Got download URL from API, fetching video...")
                            
                            video_response = requests.get(download_url, timeout=300, stream=True)
                            video_response.raise_for_status()
                            
                            with open(output_path, 'wb') as f:
                                for chunk in video_response.iter_content(chunk_size=1048576):
                                    if chunk:
                                        f.write(chunk)
                            
                            logger.info("[Strategy 4/4] ✓ External API download succeeded")
                            return True
            except Exception as api_error:
                logger.debug(f"[Strategy 4/4] API failed: {str(api_error)[:100]}")
                continue
        
        logger.warning("[Strategy 4/4] ✗ No external APIs available or working")
        return False
        
    except Exception as e:
        logger.warning(f"[Strategy 4/4] ✗ External API strategy failed: {str(e)[:100]}")
        return False


def download_with_fallbacks(url: str, output_path: str, timeout_base: int = 180) -> bool:
    """
    Try downloading using multiple strategies in order.
    Returns True if any strategy succeeds, False if all fail.
    """
    logger.info(f"Starting multi-strategy download for: {url}")
    logger.info(f"Output will be saved to: {output_path}")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    
    strategies = [
        (try_yt_dlp_standard, {"timeout": timeout_base}),
        (try_yt_dlp_with_scraping, {"timeout": timeout_base * 2}),
        (try_pytube_download, {}),
        (try_external_api, {}),
    ]
    
    for strategy_func, kwargs in strategies:
        try:
            if strategy_func(url, output_path, **kwargs):
                logger.info(f"✓ Download successful using {strategy_func.__name__}")
                return True
        except Exception as e:
            logger.error(f"Error in {strategy_func.__name__}: {e}")
            continue
    
    logger.error("✗ All download strategies failed")
    return False
