"""ASGI entry point for the call-to-task application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.datastructures import Headers
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from backend.router import router


app = FastAPI(title="Kulikov call tasks", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)},
        headers=exc.headers,
    )


@app.api_route(
    "/api/{api_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
def unknown_api_route(api_path: str) -> None:
    raise HTTPException(
        status_code=404,
        detail=f"API route /api/{api_path} not found",
    )


class SpaStaticFiles(StaticFiles):
    """Serve real assets and fall back to index.html for browser navigation."""

    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._is_navigation(scope):
                raise
        else:
            if response.status_code != 404 or not self._is_navigation(scope):
                return response
        return await super().get_response("index.html", scope)

    @staticmethod
    def _is_navigation(scope: dict) -> bool:
        if scope.get("method") not in {"GET", "HEAD"}:
            return False
        accept = Headers(scope=scope).get("accept", "")
        return "text/html" in accept


frontend_dist = Path(__file__).parents[1] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount(
        "/",
        SpaStaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )


__all__ = ["app"]
