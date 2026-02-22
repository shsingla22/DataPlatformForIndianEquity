"""FastAPI application — inference layer entry point.

Serves the REST API (for both human users and AI agents) and the static
UI assets.  Start with:

    python run_app.py

or directly:

    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.config import UI_DIR
from api.routers import companies, financials, query, compare
from api import database as db
from api.schemas import HealthResponse, StatsResponse

app = FastAPI(
    title="Indian Equity Financial Data Platform",
    description=(
        "Query financial profiles of 500+ NSE/BSE-listed Indian companies. "
        "Supports structured REST endpoints **and** a natural-language query "
        "interface for both human users and AI agents."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the UI (and any AI agent) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API routes ---
app.include_router(companies.router, prefix="/api")
app.include_router(financials.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(compare.router, prefix="/api")


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Health check — verifies the database is accessible."""
    stats = db.get_database_stats()
    return HealthResponse(
        status="healthy",
        database="connected",
        total_companies=stats["total_companies"],
        total_records=(
            stats["profit_loss_records"]
            + stats["balance_sheet_records"]
            + stats["cash_flow_records"]
        ),
    )


@app.get("/api/stats", response_model=StatsResponse, tags=["System"])
def database_stats():
    """Database summary statistics."""
    stats = db.get_database_stats()
    years = db.get_available_fiscal_years()
    return StatsResponse(**stats, fiscal_years=years)


# --- Serve UI static files ---
app.mount("/static", StaticFiles(directory=UI_DIR), name="ui")


@app.get("/", include_in_schema=False)
def serve_ui():
    """Serve the main UI page."""
    return FileResponse(f"{UI_DIR}/index.html")
