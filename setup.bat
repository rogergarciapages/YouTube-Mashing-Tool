@echo off
echo 🚀 Setting up YouTube Clip Compilation Tool...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.8+ first.
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js is not installed. Please install Node.js 18+ first.
    pause
    exit /b 1
)

REM Check if FFmpeg is installed
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  FFmpeg is not installed. Please install FFmpeg manually.
    echo Download from: https://ffmpeg.org/download.html
    echo Add FFmpeg to your system PATH
    pause
)

echo ✅ FFmpeg check completed

REM Create necessary directories
echo 📁 Creating project directories...
if not exist "backend\videos\temp" mkdir "backend\videos\temp"
if not exist "backend\videos\output" mkdir "backend\videos\output"
if not exist "backend\fonts" mkdir "backend\fonts"

REM Setup backend
echo 🐍 Setting up Python backend...
cd backend

REM Create virtual environment
python -m venv venv
call venv\Scripts\activate.bat

REM Install dependencies
pip install -r requirements.txt

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo 📝 Creating .env file...
    copy env.example .env
    echo ⚠️  Please edit backend\.env and add your Google AI API key
)

cd ..

REM Setup frontend
echo ⚛️  Setting up Next.js frontend...
cd frontend

REM Install dependencies
npm install

REM Create .env.local file if it doesn't exist
if not exist ".env.local" (
    echo 📝 Creating .env.local file...
    echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
)

cd ..

echo.
echo 🎉 Setup completed successfully!
echo.
echo 📋 Next steps:
echo 1. Edit backend\.env and add your Google AI Studio API key
echo 2. Start the backend: cd backend ^&^& venv\Scripts\activate ^&^& uvicorn main:app --reload
echo 3. Start the frontend: cd frontend ^&^& npm run dev
echo 4. Open http://localhost:3000 in your browser
echo.
echo 🐳 Or use Docker: docker-compose up --build
echo.
echo 📚 For more information, see README.md
pause
