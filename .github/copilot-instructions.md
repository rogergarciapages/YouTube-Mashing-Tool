# Copilot Instructions for YouTube Clip Compilation Tool

## Project Overview
YTTool is a full-stack web application that compiles multiple YouTube clips with AI-generated summaries, custom text overlays, and background music into a single video. It uses a Next.js frontend and FastAPI backend, with FFmpeg for video processing and Google Generative AI for summaries.

## Architecture

### Core Data Flow
1. **Frontend** (Next.js) → User submits video compilation request with clips, styling, and music
2. **API** (FastAPI) → Receives request, creates task ID, starts background job
3. **VideoProcessor** → Downloads clips via yt-dlp, generates AI summaries, processes each clip with FFmpeg overlays
4. **Output** → Combines intro + processed clips + outro + background music → final MP4

### Key Components

**Backend Structure:**
- `main.py` - FastAPI app, CORS setup, endpoints: `/generate-video`, `/status/{task_id}`, `/download/{filename}`
- `video_processor.py` (1520 lines) - Core orchestrator: clip downloading, FFmpeg text overlays, stitching, music mixing
- `config/settings.py` - Configuration: FFmpeg path detection, directories, Google AI key
- `models/schemas.py` - Pydantic models: VideoRequest/VideoResponse, VideoFormat (youtube/shorts/instagram), TextPlacement
- `utils/ai_client.py` - Google Generative AI client with fallback to simple keyword summaries
- `utils/video_utils.py` - Helper methods for video manipulation

**Frontend Structure:**
- `app/page.tsx` - Main UI, polling task status, displaying progress
- `components/ClipForm.tsx` - Input form for YouTube URLs, timestamps, keywords
- `components/ClipList.tsx` - Manage list of clips
- `components/Settings.tsx` - Video format, font, color, placement config
- `components/ProgressBar.tsx` - Real-time progress display

## Critical Workflows

### Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate.bat (Windows) or source venv/bin/activate (Unix)
pip install -r requirements.txt
```

### Running Services
```bash
# Backend: FastAPI with auto-reload
cd backend && uvicorn main:app --reload

# Frontend: Next.js dev server
cd frontend && npm install && npm run dev

# Or use Docker
docker-compose -f docker/docker-compose.yml up
```

### Environment Variables Required
- **Backend** `.env`: `GOOGLE_AI_API_KEY=<your-key>`
- **Frontend** `.env.local`: `NEXT_PUBLIC_API_URL=http://localhost:8000`

### FFmpeg Requirements
FFmpeg MUST be installed and in PATH. `settings.py` auto-detects common installation paths (Windows, macOS, Linux). If auto-detection fails, service logs will show FFmpeg validation errors.

## Project-Specific Patterns

### Task Management
- Backend uses in-memory `tasks` dict + disk persistence (`_load_tasks_from_disk()`, `_save_tasks_to_disk()`)
- Frontend polls `/status/{task_id}` to get progress, status, error messages
- Task status values: "processing", "completed", "error"
- Progress is incremented: 0% → 70% (clip processing) → 75% (intro) → 77% (outro) → 80% (stitching) → 90% (music) → 100%

### Video Formats & Dimensions
```python
VideoFormat.youtube   # 1920x1080 (16:9)
VideoFormat.shorts    # 1080x1920 (9:16)
VideoFormat.instagram # 1080x1080 (1:1)
```
Scaling applied in `video_processor.py` before overlay rendering.

### Text Overlays & Styling
- TextPlacement: "top", "center", "bottom" - controls subtitle position
- Font files stored in `backend/fonts/` - `KOMIKAX_.ttf` used as default
- FFmpeg `drawtext` filter applies font, size, color, positioning
- AI summaries capped at 60 characters; fallback to keyword extraction if AI unavailable

### File Organization
- Downloaded clips: `backend/videos/temp/` (cleaned after processing)
- Final outputs: `backend/videos/output/` (named `compilation_{task_id}.mp4`)
- Intro/outro templates: `backend/videos/intro/`, `backend/videos/outro/`
- Fonts: `backend/fonts/`

## Integration Points

### Google Generative AI (Gemini)
- Used in `ai_client.py` for 1-sentence clip summaries
- Graceful degradation: if API key missing or call fails, falls back to keyword extraction
- Model: `gemini-1.5-flash` (fast, low-cost)

### yt-dlp Video Download
- Downloads YouTube clips with specified timestamps
- `video_processor.py` uses custom format selection for best quality
- Handles age-restricted/private videos with error logging

### FFmpeg Operations
- Text overlay: `drawtext` filter
- Audio mixing: background music mixed with clip audio
- Format conversion: all clips normalized to target VideoFormat
- Concatenation: demuxer-based stitching of intro+clips+outro+music

## Development Conventions

**Error Handling:**
- Backend catches exceptions per-clip; updates task status to "error" with descriptive message
- Frontend displays error in UI via task status polling
- Logging: INFO for major operations, DEBUG for detailed processing steps

**API Response Format:**
```python
# VideoResponse (initial submission)
{"task_id": "uuid", "status": "processing"}

# ProcessingStatus (polling)
{"task_id": "uuid", "status": "processing|completed|error", 
 "progress": 0-100, "message": "Human-readable status"}
```

**Validation:**
- Pydantic validators in `schemas.py`: clip count (1-20), font size (12-120), timestamp >= 0
- Frontend prevents invalid submissions; backend validates on ingestion

## Common Implementation Tasks

**Adding new text styling options:** Update `TextPlacement` enum + `VideoRequest` fields in `schemas.py`, then adjust FFmpeg `drawtext` parameters in `video_processor.py`.

**Changing default fonts:** Add `.ttf` files to `backend/fonts/`, update default in frontend settings component, ensure `video_processor.py` references correct path.

**Modifying video processing flow:** Core logic is in `VideoProcessor.process_video_request()` → `_process_clip()` → FFmpeg command assembly. Progress updates use `_update_task_status()`.

**Frontend status updates:** `useEffect` polls `/status/{task_id}` with exponential backoff; updates `progress`, `status`, `downloadUrl` state variables.
