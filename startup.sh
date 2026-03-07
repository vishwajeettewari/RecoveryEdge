#!/bin/bash
# Install dependencies if not already installed
pip install --no-cache-dir -r requirements.txt

# Azure App Service sets PORT env var (default 8000).
# Use uvicorn directly for WebSocket support (gunicorn default does not support WS).
export API_PORT="${PORT:-8000}"

# Start the application
python -c "from web_app import main; main()"
