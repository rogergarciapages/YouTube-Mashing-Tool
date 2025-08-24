from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import uuid
from typing import List
import logging

from models.schemas import VideoRequest, VideoResponse, ProcessingStatus
from video_processor import VideoProcessor
from config.settings import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube Clip Compilation Tool",
    description="API for processing YouTube clips with AI summaries and custom styling",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for video downloads
app.mount("/videos", StaticFiles(directory="videos"), name="videos")

# Global processor instance
video_processor = VideoProcessor()

@app.get("/")
async def root():
    return {"message": "YouTube Clip Compilation Tool API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/generate-video", response_model=VideoResponse)
async def generate_video(request: VideoRequest, background_tasks: BackgroundTasks):
    """
    Generate a compiled video from multiple YouTube clips
    """
    try:
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Add video processing to background tasks
        background_tasks.add_task(
            video_processor.process_video_request,
            request,
            task_id
        )
        
        logger.info(f"Started video processing task: {task_id}")
        
        return VideoResponse(
            task_id=task_id,
            status="processing",
            message="Video processing started"
        )
        
    except Exception as e:
        logger.error(f"Error starting video processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{task_id}", response_model=ProcessingStatus)
async def get_status(task_id: str):
    """
    Get the processing status of a video generation task
    """
    try:
        status = video_processor.get_task_status(task_id)
        return status
    except Exception as e:
        logger.error(f"Error getting status for task {task_id}: {e}")
        raise HTTPException(status_code=404, detail="Task not found")

@app.get("/download/{filename}")
async def download_video(filename: str):
    """
    Download the final compiled video
    """
    file_path = f"videos/{filename}"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="video/mp4"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
