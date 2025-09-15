#!/bin/bash

# AggLayer Python Dashboard Startup Script

echo "🚀 Starting AggLayer Python Dashboard..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+"
    exit 1
fi

# Check if pip is installed  
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip3"
    exit 1
fi

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
else
    echo "❌ requirements.txt not found"
    exit 1
fi

# Check if config.json exists
if [ ! -f "config.json" ]; then
    echo "❌ config.json not found. Please create your configuration file."
    exit 1
fi

echo "✅ Configuration found"

# Optional: Run configuration test
if [ "$1" = "--test" ] || [ "$1" = "-t" ]; then
    echo "🧪 Running configuration test..."
    python3 test_config.py
    if [ $? -ne 0 ]; then
        echo "❌ Configuration test failed. Please check your settings."
        exit 1
    fi
    echo ""
elif [ "$1" = "--debug" ] || [ "$1" = "-d" ]; then
    echo "🐛 Running debug startup test..."
    python3 debug_startup.py
    if [ $? -ne 0 ]; then
        echo "❌ Debug test failed. Please check your settings."
        exit 1
    fi
    echo ""
    echo "🚀 Debug test passed! Starting server..."
    echo ""
fi
echo "🌐 Starting server on http://localhost:8000"
echo "📊 Access the dashboard at: http://localhost:8000"
echo "📋 View rollups at: http://localhost:8000/rollups"
echo "📋 API documentation at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the FastAPI application
python3 app.py
