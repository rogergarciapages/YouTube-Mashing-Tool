@echo off
echo 🚀 Starting YouTube Clip Compilation Tool...

echo 🐍 Starting Backend (FastAPI)...
start "YTTool Backend" cmd /k "cd backend && venv\Scripts\activate && uvicorn main:app --reload"

echo ⚛️  Starting Frontend (Next.js)...
start "YTTool Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ✅ Services started in separate windows.
echo 🌍 Backend: http://localhost:8000/docs
echo 🌍 Frontend: http://localhost:3000
echo.
pause
