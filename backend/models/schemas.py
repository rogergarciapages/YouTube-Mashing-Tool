from pydantic import BaseModel, HttpUrl, validator
from typing import List, Optional
from enum import Enum

class VideoFormat(str, Enum):
    youtube = "youtube"      # 16:9 (1920x1080)
    shorts = "shorts"        # 9:16 (1080x1920)
    instagram = "instagram"  # 1:1 (1080x1080)

class TextPlacement(str, Enum):
    top = "top"
    center = "center"
    bottom = "bottom"

class ClipRequest(BaseModel):
    url: HttpUrl
    timestamp: int
    keywords: Optional[str] = None
    custom_text: Optional[str] = None
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        if v < 0:
            raise ValueError('Timestamp must be non-negative')
        return v

class DownloadConfig(BaseModel):
    """Configuration for downloading videos (cookies, headers, etc.)"""
    cookies_file: Optional[str] = None  # Path to cookies.txt file
    use_geo_bypass: bool = True  # Whether to use geo-bypass
    retries: int = 3  # Number of retries

class VideoItem(BaseModel):
    title: str  # e.g. "Rolex"
    order: int
    clips: List[ClipRequest]

class VideoRequest(BaseModel):
    items: List[VideoItem]
    title: str = "Amazing Video Compilation"  # Default title for intro
    font: str = "Arial"
    font_size: int = 36
    font_color: str = "white"
    placement: TextPlacement = TextPlacement.bottom
    music: Optional[str] = None
    format: VideoFormat = VideoFormat.youtube
    download_config: Optional[DownloadConfig] = None  # Optional cookies/download settings
    
    @validator('items')
    def validate_items(cls, v):
        if not v:
            raise ValueError('At least one item must be provided')
        total_clips = sum(len(item.clips) for item in v)
        if total_clips > 50:
            raise ValueError('Maximum 50 clips allowed total')
        if total_clips == 0:
            raise ValueError('Items must contain at least one clip')
        return v
    
    @validator('font_size')
    def validate_font_size(cls, v):
        if v < 12 or v > 120:
            raise ValueError('Font size must be between 12 and 120')
        return v

class VideoResponse(BaseModel):
    task_id: str
    status: str
    message: str
    download_url: Optional[str] = None

class ProcessingStatus(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    message: str
    download_url: Optional[str] = None
    error: Optional[str] = None

class ClipInfo(BaseModel):
    url: str
    timestamp: int
    summary: str
    duration: float
    status: str
