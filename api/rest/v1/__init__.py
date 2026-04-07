"""REST API v1 endpoints - combine all module routers."""

from fastapi import APIRouter

from apps.autocomplete.router import router as autocomplete_router
from apps.result.router import router as result_router
from apps.scraper.router import router as scraper_router
from apps.submit.router import router as submit_router
from apps.user.router import router as user_router
from apps.vote_data.router import router as vote_data_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(submit_router)
api_router.include_router(user_router)
api_router.include_router(vote_data_router)
api_router.include_router(result_router)
api_router.include_router(scraper_router)
api_router.include_router(autocomplete_router)
