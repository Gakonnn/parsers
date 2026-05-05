from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User
from app.services.parsers_hub import ParsersHubError, get_parser_meta
from app.services.parser_meta_fallback import ParserMetaFallbackError, get_fallback_meta


router = APIRouter()


def _proxy_meta(path: str) -> dict:
    try:
        return get_parser_meta(path)
    except ParsersHubError as exc:
        try:
            return get_fallback_meta(path)
        except ParserMetaFallbackError as fallback_exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from fallback_exc


@router.get("/config")
def get_config(_: User = Depends(get_current_user)) -> dict:
    return _proxy_meta("/api/config")


@router.get("/2gis/rubrics")
def get_2gis_rubrics(_: User = Depends(get_current_user)) -> dict:
    return _proxy_meta("/api/2gis/rubrics")


@router.get("/2gis/cities")
def get_2gis_cities(_: User = Depends(get_current_user)) -> dict:
    return _proxy_meta("/api/2gis/cities")


@router.get("/olx/categories")
def get_olx_categories(_: User = Depends(get_current_user)) -> dict:
    return _proxy_meta("/api/olx/categories")
