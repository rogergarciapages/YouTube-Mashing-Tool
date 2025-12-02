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
# Copilot instructions — YTTool (concise)

This file gives an AI coding agent the minimum, high‑value knowledge to work productively on YTTool.

Key facts (read before editing code)
- Repo: Next.js frontend (frontend/) + FastAPI backend (backend/). Video work happens server‑side in `backend/video_processor.py`.
- Long/complex file: `backend/video_processor.py` is the single biggest implementation area — it downloads with yt-dlp, runs FFmpeg filters, and manages tasks.
- Task flow: frontend -> POST /generate-video -> FastAPI spawns background VideoProcessor.process_video_request(task_id) -> updates stored ProcessingStatus -> frontend polls /status/{task_id}.
- SSL/cert issue: Windows Python often fails TLS verification for YouTube APIs. Workaround: upload browser cookies (extracts authentication) or install certifi-win32 to use Windows CA store.

Quick start (dev)
- Backend (Windows PowerShell):
  & "backend/venv/Scripts/Activate.ps1"; python -m pip install -r backend/requirements.txt; python -m uvicorn main:app --reload
- Frontend:
  cd frontend; npm install; npm run dev

Important files/places to change
- `backend/video_processor.py` — core logic; look for `_download_clip()`, `_overlay_text()`, `_format_video()`, `_stitch_clips()`.
- `backend/models/schemas.py` — Pydantic types (VideoRequest, ClipRequest, DownloadConfig) and validation rules.
- `config/settings.py` — FFmpeg path, temp/output dirs, CLIP_DURATION, CLEANUP_TEMP_FILES. Change runtime defaults here.
- `utils/ai_client.py` — Google Generative AI integration; has graceful fallback to keyword summaries.
- `frontend/components/CookiesUpload.tsx` — cookies file upload UI; sends POST /upload-cookies to backend and stores path in download_config.

Patterns & gotchas (project‑specific)
- Task persistence: tasks stored in memory and saved to disk (see _load_tasks_from_disk/_save_tasks_to_disk). When changing status format, migrate both code paths.
- FFmpeg: Commands are built manually (drawtext filters, cropping); test locally with the exact ffmpeg command logged in the backend logs.
- yt-dlp SSL on Windows: `_download_clip()` now supports cookies file (--cookies flag). If cookies not available, tries unverified SSL fallback. Both methods use subprocess with ssl._create_unverified_context.
- Cookies workflow: frontend uploads file via POST /upload-cookies -> saved to `videos/temp/cookies/` -> path returned in JSON -> frontend includes path in download_config.cookies_file -> backend passes to yt-dlp.
- Large file timeouts: FFmpeg timeouts scale with input size (file_size_mb * 3s). Increase if you change encoding steps.

Debugging tips
- Check backend logs (stdout) for full yt-dlp and ffmpeg stderr when troubleshooting downloads or processing errors.
- To reproduce download behavior locally, run the same subprocess command printed in logs (it uses `sys.executable -m yt_dlp ...`). Use `-v` for verbose yt-dlp output.
- If yt-dlp fails with SSL CERTIFICATE_VERIFY_FAILED and video is public/unblocked: install certifi-win32 in venv (pip install certifi-win32).
- If video is age/region-restricted: user uploads cookies.txt via frontend CookiesUpload; backend passes --cookies file to yt-dlp to authenticate.
- If you modify a long-running process, restart uvicorn (reload is enabled but heavy edits may leave reloader in inconsistent state).

What to update in this file
- Keep this doc short. If you add persistent conventions (new env vars, new task states, or new external services) update the bullet list above and add an example command.

Questions? Ask for the specific backend log snippet (yt-dlp/ffmpeg command + stderr) and I'll point to the exact lines to change.

---
Files referenced: `backend/video_processor.py`, `backend/models/schemas.py`, `config/settings.py`, `utils/ai_client.py`, `frontend/app/page.tsx`, `frontend/components/CookiesUpload.tsx`