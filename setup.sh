#!/bin/bash

echo "🚀 Setting up YouTube Clip Compilation Tool..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

# Check if FFmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg is not installed. Installing FFmpeg..."
    
    # Detect OS and install FFmpeg
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y ffmpeg
        elif command -v yum &> /dev/null; then
            sudo yum install -y ffmpeg
        else
            echo "❌ Please install FFmpeg manually for your Linux distribution"
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install ffmpeg
        else
            echo "❌ Please install Homebrew first, then run: brew install ffmpeg"
            exit 1
        fi
    else
        echo "❌ Please install FFmpeg manually for your operating system"
        exit 1
    fi
fi

echo "✅ FFmpeg is installed"

# Create necessary directories
echo "📁 Creating project directories..."
mkdir -p backend/videos/temp backend/videos/output backend/fonts

# Setup backend
echo "🐍 Setting up Python backend..."
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp env.example .env
    echo "⚠️  Please edit backend/.env and add your Google AI API key"
fi

cd ..

# Setup frontend
echo "⚛️  Setting up Next.js frontend..."
cd frontend

# Install dependencies
npm install

# Create .env.local file if it doesn't exist
if [ ! -f .env.local ]; then
    echo "📝 Creating .env.local file..."
    echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
fi

cd ..

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Edit backend/.env and add your Google AI Studio API key"
echo "2. Start the backend: cd backend && source venv/bin/activate && uvicorn main:app --reload"
echo "3. Start the frontend: cd frontend && npm run dev"
echo "4. Open http://localhost:3000 in your browser"
echo ""
echo "🐳 Or use Docker: docker-compose up --build"
echo ""
echo "📚 For more information, see README.md"
