#!/bin/bash
# local-agent macOS Setup Script
echo "Starting local-agent adaptation for macOS..."

# 1. Create Virtual Environment
python3 -m venv venv
source venv/bin/activate

# 2. Install Dependencies
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "requirements.txt not found, installing core dependencies..."
    pip install requests beautifulsoup4 lxml duckduckgo-search
fi

# 3. Setup Data Directory
mkdir -p data

# 4. Set Environment Variables
export PROJECT_ROOT=$(pwd)
export MEMORY_DB_PATH="$PROJECT_ROOT/data/memory.db"

echo "Setup complete. To start the agent, use:"
echo "source venv/bin/activate && python3 launcher.py"
