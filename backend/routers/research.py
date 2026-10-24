"""Deep-research endpoints: plan sub-queries, fetch sources, write notes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.schemas import ResearchRequest
from backend.services import tools as tools_service

router = APIRouter()


@router.post("/api/research")
async def api_research(req: ResearchRequest):
    """Run the research pipeline for a question and persist the note."""
    result = await tools_service.deep_research(req.query)
    return JSONResponse(result)
