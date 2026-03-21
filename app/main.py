"""
Money Manager V2 - FastAPI Application Entry Point.
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.error_handler import register_error_handlers
from app.middleware.logging import RequestLoggingMiddleware
from app.routes.accounts import router as accounts_router
from app.routes.auth import router as auth_router
from app.routes.categories import router as categories_router
from app.routes.debug import router as debug_router
from app.routes.reports import router as reports_router
from app.routes.sms import router as sms_router
from app.routes.budgets import router as budgets_router
from app.routes.transactions import router as transactions_router

# Structured logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("money_manager")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Money Manager V2 API",
        description="Personal finance API with automatic Indian bank SMS parsing.",
        version="0.1.0",
    )

    # CORS - allow Flutter app
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging
    app.add_middleware(RequestLoggingMiddleware)

    # Error handlers
    register_error_handlers(app)

    # Routes
    app.include_router(auth_router)
    app.include_router(transactions_router)
    app.include_router(categories_router)
    app.include_router(accounts_router)
    app.include_router(sms_router)
    app.include_router(budgets_router)
    app.include_router(reports_router)
    app.include_router(debug_router)

    @app.get("/")
    async def root() -> dict:
        return {
            "success": True,
            "data": {
                "app": "Money Manager V2 API",
                "docs": "/docs",
            },
        }

    logger.info("Money Manager V2 API started | env=%s", "loading")

    return app


app = create_app()
