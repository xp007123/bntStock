"""FastAPI 应用入口。

开发：  uvicorn sixiang.api.app:app --reload --port 8000（前端用 Vite 代理 /api）
生产：  先构建前端（frontend/dist），本服务同时提供静态页面与 /api。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import Settings, load_settings
from ..data.store import MarketStore
from .routes import market


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="四象智投", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.market = MarketStore(settings.market_dir)

    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok"}

    app.include_router(market.router)

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
            return FileResponse(dist / "index.html")

    return app


app = create_app()
