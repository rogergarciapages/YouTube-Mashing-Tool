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

class VideoRequest(BaseModel):
    clips: List[ClipRequest]
    font: str = "Arial"
    font_size: int = 36
    font_color: str = "white"
    placement: TextPlacement = TextPlacement.bottom
    music: Optional[str] = None
    format: VideoFormat = VideoFormat.youtube
    
    @validator('clips')
    def validate_clips(cls, v):
        if not v:
            raise ValueError('At least one clip must be provided')
        if len(v) > 20:
            raise ValueError('Maximum 20 clips allowed')
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
