"""Vercel entry point for the FastAPI backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import accounts, auth, dashboard, health

app = FastAPI(
    title="Vấn Đạo Mini API",
    version="0.1.0",
    description="Backend API for the Vấn Đạo Mini dashboard.",
)

# Same-origin deployment is the default. Configure explicit origins if the FE
# is hosted separately; do not combine wildcard origins with credentialed cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(accounts.router, prefix="/api/v1/accounts", tags=["accounts"])
app.include_router(dashboard.router, prefix="/api/v1", tags=["dashboard"])
