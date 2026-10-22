"""RL training endpoints: corpus, judge, run, day-day stats."""

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.schemas import TrainingJudgeRequest
from backend.services import llm as llm_service
from backend.services import training as training_service

router = APIRouter()


@router.get("/api/training/corpus")
async def api_training_corpus():
    return JSONResponse(
        {"count": len(training_service.TRAINING_CORPUS), "corpus": training_service.TRAINING_CORPUS}
    )


@router.post("/api/training/judge")
async def api_training_judge(req: TrainingJudgeRequest):
    """Judge any question/answer pair and store it as a scored training pair."""
    verdict = await training_service._judge_answer(
        req.q,
        req.a,
        ["Accuracy", "Technical depth", "Clarity", "No boilerplate or hedging"],
    )
    entry = training_service._record_training_pair(
        req.q,
        req.a,
        verdict["score"],
        verdict["critique"],
        req.category,
        llm_service.LLM_STATE.get("model", ""),
        verdict.get("judge", ""),
    )
    return JSONResponse({"ok": True, "entry": entry})


@router.post("/api/training/run")
async def api_training_run(n: int = 3):
    """Answer + judge n not-yet-scored hard questions from the corpus."""
    target = max(1, min(n, len(training_service.TRAINING_CORPUS)))
    scored_qs = {p.get("q") for p in training_service.RL_STATE["pairs"]}
    done = []
    for item in training_service.TRAINING_CORPUS:
        if len(done) >= target:
            break
        if item["q"] in scored_qs:
            continue
        answer, _r = await llm_service._call_llm(
            "You are J.A.R.V.I.S. Answer precisely and technically. Address the "
            "user as 'sir'. At most 8 sentences; no preamble or meta talk.",
            [{"role": "user", "content": item["q"]}],
        )
        if not (answer or "").strip():
            continue
        verdict = await training_service._judge_answer(item["q"], answer, item["rubric"])
        entry = training_service._record_training_pair(
            item["q"],
            answer,
            verdict["score"],
            verdict["critique"],
            item["category"],
            llm_service.LLM_STATE.get("model", ""),
            verdict.get("judge", ""),
        )
        done.append({"id": item["id"], "score": entry["score"], "critique": entry["critique"][:160]})
    return JSONResponse({"ok": True, "trained": len(done), "results": done})


@router.get("/api/training/stats")
async def api_training_stats():
    """Day-day progression: total pairs, per-day averages, category averages."""
    pairs = training_service.RL_STATE["pairs"]
    daily = [
        {
            "date": day,
            "count": v["count"],
            "avg_score": round(v["score_sum"] / max(v["count"], 1), 2),
        }
        for day, v in sorted(training_service.RL_STATE["daily"].items())
    ]
    by_cat: dict[str, list[float]] = {}
    for p in pairs:
        by_cat.setdefault(p.get("category", "custom"), []).append(p.get("score", 0))
    categories = {c: {"count": len(v), "avg": round(sum(v) / len(v), 2)} for c, v in by_cat.items()}
    best = sorted(pairs, key=lambda p: p.get("score", 0), reverse=True)[:5]
    return JSONResponse(
        {
            "total_pairs": len(pairs),
            "avg_score": round(sum(p.get("score", 0) for p in pairs) / max(len(pairs), 1), 2),
            "daily": daily,
            "categories": categories,
            "best_exemplars": [{"q": p["q"][:80], "score": p["score"]} for p in best],
        }
    )


_TRAINING_TASK: asyncio.Task | None = None


async def _daily_training_loop():
    """Day-day training: answer + judge fresh corpus questions every 24h."""
    await asyncio.sleep(45)  # let the app finish booting
    while True:
        try:
            await api_training_run(3)
        except Exception:
            pass
        await asyncio.sleep(24 * 3600)
