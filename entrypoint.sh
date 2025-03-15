#!/bin/bash
# Start Ollama in the background
ollama serve &

# Start Flask app in the foreground
exec python /app/y_social.py --host 0.0.0.0 --port 5000
