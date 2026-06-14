from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, auth, billing, jobs, notifications, parser_meta, results, support, users


api_router = APIRouter()
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(parser_meta.router, prefix="/parser-meta", tags=["parser-meta"])
api_router.include_router(results.router, prefix="/results", tags=["results"])
api_router.include_router(support.router, prefix="/support", tags=["support"])
