# YouTube Clip Compilation Tool

A web application that allows users to compile multiple YouTube clips with AI-generated summaries, custom styling, and background music into a single video.

## Features

- **Multi-clip Input**: Add multiple YouTube URLs with timestamps
- **AI Summaries**: Generate short descriptions from keywords using Google AI Studio
- **Custom Styling**: Configure font, size, color, and placement of text overlays
- **Background Music**: Add background music to the final compilation
- **Multiple Formats**: Support for YouTube (16:9), Shorts (9:16), and Instagram (1:1)
- **Automated Processing**: Download, process, and stitch clips automatically

## Project Structure

```
youtube-clip-tool/
├─ frontend/                # Next.js application
├─ backend/                 # FastAPI Python backend
├─ docker/                  # Containerization files
└─ README.md               # This file
```

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.8+
- FFmpeg installed on your system
- Google AI Studio API key

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Environment Variables

Create `.env.local` in the frontend directory:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Create `.env` in the backend directory:
```env
GOOGLE_AI_API_KEY=your_api_key_here
```

## API Endpoints

- `POST /generate-video` - Process video compilation request
- `GET /status/{task_id}` - Check processing status
- `GET /download/{filename}` - Download final video

## Technologies Used

- **Frontend**: Next.js, React, Tailwind CSS
- **Backend**: FastAPI, Python
- **Video Processing**: FFmpeg, yt-dlp
- **AI**: Google AI Studio (Gemini Pro)
- **Styling**: Custom font overlays with FFmpeg

## License

MIT
