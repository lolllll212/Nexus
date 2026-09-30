"""NEXUS AI Backend Entrypoint — Python FastApi & Cognitive Cortex Subsystem."""
import os
import sys
from pathlib import Path

# Ensure project root and src/ are in sys.path
backend_dir = Path(__file__).resolve().parent
root_dir = backend_dir.parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(backend_dir))

import uvicorn
from nexus.infrastructure.api.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("nexus.infrastructure.api.main:app", host=host, port=port, reload=False)
