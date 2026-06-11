from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.api_contract import (
    create_favorite,
    delete_favorite,
    get_api_manifest,
    get_bids,
    get_favorites,
    get_health,
    get_item_detail,
    get_news,
    get_patents,
    get_rnd_announces,
    get_rnd_outcomes,
    get_source_detail_for_item,
    get_trends,
)


class FavoriteCreateRequest(BaseModel):
    item_id: int


app = FastAPI(title="ModularHub API", version="0.1.0")


@app.get("/api")
def api_manifest() -> dict:
    return get_api_manifest()


@app.get("/api/health")
def api_health() -> dict:
    return get_health()


@app.get("/api/bids")
def api_bids(limit: int = 200) -> list[dict]:
    return get_bids(limit=limit)


@app.get("/api/news")
def api_news(limit: int = 200) -> list[dict]:
    return get_news(limit=limit)


@app.get("/api/rnd-announces")
def api_rnd_announces(limit: int = 200) -> list[dict]:
    return get_rnd_announces(limit=limit)


@app.get("/api/rnd-outcomes")
def api_rnd_outcomes(limit: int = 200) -> list[dict]:
    return get_rnd_outcomes(limit=limit)


@app.get("/api/patents")
def api_patents(limit: int = 200) -> list[dict]:
    return get_patents(limit=limit)


@app.get("/api/trends")
def api_trends() -> dict:
    return get_trends()


@app.get("/api/items/{item_id}")
def api_item_detail(item_id: int) -> dict:
    try:
        return get_item_detail(item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/items/{item_id}/source-detail")
def api_item_source_detail(item_id: int) -> dict | None:
    return get_source_detail_for_item(item_id)


@app.get("/api/favorites")
def api_favorites(limit: int = 500) -> list[dict]:
    return get_favorites(limit=limit)


@app.post("/api/favorites")
def api_create_favorite(payload: FavoriteCreateRequest) -> dict:
    if payload.item_id <= 0:
        raise HTTPException(status_code=400, detail="item_id must be positive")
    return create_favorite(payload.item_id)


@app.delete("/api/favorites/{item_id}")
def api_delete_favorite(item_id: int) -> dict:
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="item_id must be positive")
    return delete_favorite(item_id)
