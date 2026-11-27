"""FastAPI 应用入口。

开发：  uvicorn sixiang.api.app:app --reload --port 8000（前端用 Vite 代理 /api）
生产：  先构建前端（frontend/dist），本服务同时提供静态页面与 /api。
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import Settings, load_settings
from ..auth.db import make_engine
from ..auth.deps import current_user
from ..auth.service import AuthService
from ..data.scheduler import DailySync
from ..data.store import MarketStore
from ..research.jobs import JobManager
from ..research.library_store import UserLibrary
from ..judgments import Judgments
from ..watchlist import Watchlist
from ..room import llm as room_llm
from ..room.registry import PersonaRegistry
from ..room.service import RoomService
from ..room.store import RoomStore
from ..picks.service import PickSchedule, PickService, PoolSchedule
from ..picks.store import PickStore
from .routes import admin, admin_personas, ask, auth, judgments, market, patterns, picks, rooms, watchlist


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    market_store = MarketStore(settings.market_dir)
    jobs = JobManager(settings.data_dir / "research" / "jobs", market_store)

    scheduler = DailySync(settings.market_dir, os.environ["SIXIANG_SYNC_AT"]) if os.environ.get("SIXIANG_SYNC_AT") else None

    engine = make_engine(settings.db_url())
    pick_service = PickService(PickStore(engine), market_store)
    # 选股名单：设了 SIXIANG_PICKS_AT（如 09:25:40）才会每天自动去取
    # 文哥选股 09:26:30 出（开盘价要等 09:25 集合竞价结束），候选池每周五收盘后算下一周的
    pick_schedules = [PickSchedule(pick_service, os.environ["SIXIANG_PICKS_AT"], ["sjm"]),
                      PickSchedule(pick_service, os.environ.get("SIXIANG_WENGE_AT", "09:26:30"), ["wenge"]),
                      PoolSchedule(pick_service, os.environ.get("SIXIANG_WENGE_POOL_AT", "16:30"))] if os.environ.get("SIXIANG_PICKS_AT") else []

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if scheduler:
            scheduler.start()
        for job in pick_schedules:
            job.start()
        yield
        if scheduler:
            scheduler.stop()
        for job in pick_schedules:
            job.stop()
        jobs.shutdown()

    app = FastAPI(title="四象智投", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
    app.state.settings = settings
    app.state.market = market_store
    app.state.jobs = jobs
    app.state.picks = pick_service
    app.state.auth = AuthService(engine)
    app.state.library = UserLibrary(engine)
    app.state.judgments = Judgments(engine)
    app.state.watchlist = Watchlist(engine)
    # 群聊：没配模型密钥时 model 为空，群聊入口不显示，其他功能不受影响
    app.state.rooms = RoomService(RoomStore(engine), PersonaRegistry(engine), market_store, settings.data_dir / "research" / "jobs", room_llm.from_env())
    app.state.rooms.picks = pick_service

    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok"}

    # 除健康检查与登录注册外，所有接口需要登录
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(admin_personas.router)
    app.include_router(market.router, dependencies=[Depends(current_user)])
    app.include_router(patterns.router, dependencies=[Depends(current_user)])
    app.include_router(ask.router, dependencies=[Depends(current_user)])
    app.include_router(judgments.router, dependencies=[Depends(current_user)])
    app.include_router(watchlist.router, dependencies=[Depends(current_user)])
    app.include_router(rooms.router, dependencies=[Depends(current_user)])
    app.include_router(picks.router, dependencies=[Depends(current_user)])

    dist = settings.frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "接口不存在")
            file = (dist / path).resolve()
            if path and file.is_file() and dist in file.parents:
                return FileResponse(file)
            # 入口页不缓存，发布后用户立刻拿到新版本；带哈希的静态资源可长期缓存
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
