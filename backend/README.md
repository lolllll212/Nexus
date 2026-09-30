# NEXUS AI — Backend Cortex & API Services

Dedicated backend service architecture for the NEXUS AI Autonomous Cognitive Operating System.

## Architecture & Capabilities
- **FastAPI Core**: RESTful API endpoints for graphs, agent orchestration, audio STT/TTS, NVIDIA NIM inference, coding assistant, and research.
- **Cognitive Cortex**: ReAct conscious loop with multi-step reasoning, goal tracking, and dynamic tool invocation.
- **Subcortex Dreaming**: Autonomous background synthesis, Fourier grid cell spatial memory consolidation, and episodic memory pruning.
- **Hexagonal Architecture**: Fully decoupled Domain, Application, and Infrastructure layers with in-memory fallbacks and production persistence (Neo4j, Qdrant, Redis).

## Quick Start
```bash
# Run backend directly
python3 backend/main.py

# Or run with uvicorn
NEXUS_INFRA_BACKEND=memory PYTHONPATH=src python3 -m uvicorn nexus.infrastructure.api.main:app --host 0.0.0.0 --port 8000
```
