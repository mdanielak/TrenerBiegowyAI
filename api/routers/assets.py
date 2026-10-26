# -*- coding: utf-8 -*-
"""Asset serving router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.assets import ASSET_MEDIA_TYPE, resolve_asset


def get_assets_router(asset_manifest: dict) -> APIRouter:
    router = APIRouter()

    @router.get("/assets/{category}/{name}")
    def asset(category: str, name: str) -> FileResponse:
        """Wydaj obraz wyłącznie z białej listy zbudowanej przy starcie aplikacji."""
        asset_path = resolve_asset(f"{category}/{name}", asset_manifest)
        if asset_path is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono obrazu.")
        return FileResponse(
            asset_path,
            media_type=ASSET_MEDIA_TYPE,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return router
