"""Public entry points used to register the local Bitrix24 application."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse


router = APIRouter()

_FRONTEND_INDEX = Path(__file__).parents[1] / "frontend" / "dist" / "index.html"

_INSTALL_PAGE = """<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Установка приложения</title>
    <script src="https://api.bitrix24.com/api/v1/"></script>
    <style>
      body { font: 16px/1.5 system-ui, sans-serif; margin: 2rem; color: #263238; }
      .status { max-width: 42rem; padding: 1rem 1.25rem; border-radius: 12px;
        background: #f1f8e9; }
    </style>
  </head>
  <body>
    <div class="status" id="status">Завершаем установку приложения…</div>
    <script>
      const statusNode = document.getElementById("status");
      if (!window.BX24) {
        statusNode.textContent = "Не удалось загрузить SDK Bitrix24.";
      } else {
        BX24.init(function () {
          try {
            BX24.installFinish();
            statusNode.textContent = "Приложение установлено. Можно закрыть это окно.";
          } catch (error) {
            statusNode.textContent = "Не удалось завершить установку: " + String(error);
          }
        });
      }
    </script>
  </body>
</html>
"""


@router.api_route(
    "/handler",
    methods=["GET", "POST"],
    include_in_schema=False,
)
def bitrix_handler() -> FileResponse:
    """Serve the application shell when Bitrix24 opens the local app."""

    if not _FRONTEND_INDEX.is_file():
        raise HTTPException(
            status_code=503,
            detail="Frontend build is unavailable",
        )
    return FileResponse(
        _FRONTEND_INDEX,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.api_route(
    "/install",
    methods=["GET", "POST"],
    include_in_schema=False,
)
def bitrix_install() -> HTMLResponse:
    """Finish interactive installation from inside the Bitrix24 iframe."""

    return HTMLResponse(
        _INSTALL_PAGE,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; "
                "script-src https://api.bitrix24.com 'unsafe-inline'; "
                "style-src 'unsafe-inline'; "
                "frame-ancestors https://bitrix.kulikov.com "
                "https://*.bitrix24.ru https://*.bitrix24.com"
            ),
        },
    )


__all__ = ["router"]
