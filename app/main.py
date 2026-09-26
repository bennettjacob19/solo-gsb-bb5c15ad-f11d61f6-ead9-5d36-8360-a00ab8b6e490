"""串联稀释配液计算器 —— FastAPI 入口。"""

from pathlib import Path
from typing import Any, List

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .dilution import DilutionInputError, compute_plan

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="串联稀释配液计算器", version="1.0.0")


class TubeIn(BaseModel):
    concentration: Any
    retain_volume: Any
    loss_volume: Any = "0"


class PlanRequest(BaseModel):
    stock_concentration: Any
    pipette_min: Any
    tubes: List[TubeIn]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/plan")
def create_plan(req: PlanRequest):
    """计算串联稀释方案；输入不合法时返回 400 与中文错误信息。"""
    try:
        return compute_plan(
            stock_concentration=req.stock_concentration,
            pipette_min=req.pipette_min,
            tubes=[t.model_dump() for t in req.tubes],
        )
    except DilutionInputError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


# 静态页面（index.html 及 assets），挂载在最后，不影响 /api 路由
app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
