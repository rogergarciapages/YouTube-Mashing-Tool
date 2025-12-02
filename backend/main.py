from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import uuid
from typing import List
import logging
import shutil

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

# Global processor instance
video_processor = VideoProcessor()

@app.on_event("shutdown")
async def shutdown_event():
    """
    Save all tasks to disk before shutting down
    """
    try:
        video_processor._save_tasks_to_disk()
        logger.info("All tasks saved to disk before shutdown")
    except Exception as e:
        logger.error(f"Error saving tasks during shutdown: {e}")

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
    file_path = os.path.join("videos/output", filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="video/mp4"
    )

@app.post("/recover-tasks")
async def recover_tasks():
    """
    Recover tasks from disk and check for completed videos
    """
    try:
        # Reload tasks from disk
        video_processor._load_tasks_from_disk()
        
        # Check for completed videos in output directory
        output_dir = "videos/output"
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                if filename.startswith("compilation_") and filename.endswith(".mp4"):
                    task_id = filename.replace("compilation_", "").replace(".mp4", "")
                    
                    # If task exists but doesn't have download_url, update it
                    if task_id in video_processor.tasks:
                        task = video_processor.tasks[task_id]
                        if not task.download_url and task.status == "completed":
                            task.download_url = f"/download/{filename}"
                            logger.info(f"Recovered download URL for task {task_id}")
        
        # Save updated tasks
        video_processor._save_tasks_to_disk()
        
        recovered_count = len(video_processor.tasks)
        return {"message": f"Recovered {recovered_count} tasks", "tasks": list(video_processor.tasks.keys())}
        
    except Exception as e:
        logger.error(f"Error recovering tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/retry-task/{task_id}")
async def retry_task(task_id: str):
    """
    Retry a failed task by resetting its status
    """
    try:
        if task_id in video_processor.tasks:
            task = video_processor.tasks[task_id]
            if task.status == "error":
                # Reset task to processing status
                task.status = "processing"
                task.progress = 0
                task.message = "Retrying video processing..."
                task.error = None
                
                # Save updated task
                video_processor._save_tasks_to_disk()
                
                logger.info(f"Reset task {task_id} for retry")
                return {"message": f"Task {task_id} reset for retry", "status": "processing"}
            else:
                raise HTTPException(status_code=400, detail="Task is not in error status")
        else:
            raise HTTPException(status_code=404, detail="Task not found")
            
    except Exception as e:
        logger.error(f"Error retrying task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-cookies")
async def upload_cookies(file: UploadFile = File(...)):
    """
    Upload a cookies.txt file to be used for video downloads.
    Returns the path where the cookies file will be stored.
    The frontend should include this path in the DownloadConfig.cookies_file field.
    """
    try:
        # Create a temporary cookies directory if it doesn't exist
        cookies_dir = os.path.join("videos", "temp", "cookies")
        os.makedirs(cookies_dir, exist_ok=True)
        
        # Generate a unique filename for the cookies file
        cookies_filename = f"cookies_{uuid.uuid4()}.txt"
        cookies_path = os.path.join(cookies_dir, cookies_filename)
        
        # Save the uploaded file
        with open(cookies_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Cookies file uploaded: {cookies_path}")
        
        return {
            "message": "Cookies file uploaded successfully",
            "cookies_file": cookies_path,
            "filename": cookies_filename
        }
        
    except Exception as e:
        logger.error(f"Error uploading cookies file: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading cookies file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
