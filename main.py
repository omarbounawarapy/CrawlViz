"""FastAPI entry point for the CrawlViz control API.

Run from the repository root with:
    uvicorn main:app --reload

Running from the repo root is what makes the top-level packages
(config, core, events, ...) importable without a src layout or an
installed package.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_HOSTS, CORS_ORIGIN_REGEX, CORS_ORIGINS
from routes.request_guards import RequestGuardMiddleware
from routes.templates import router as templates_router
from routes.run import router as run_router
from routes.validation import router as validation_router
from routes.config import router as config_router
from routes.benchmark import router as benchmark_router

app = FastAPI(title="CrawlViz Control API")

# The last middleware added is the outermost. The guards sit inside CORS so that a refusal
# still carries the CORS headers and the UI can show its message.
app.add_middleware(
    RequestGuardMiddleware,
    allowed_hosts=ALLOWED_HOSTS,
    allowed_origins=CORS_ORIGINS,
    allowed_origin_pattern=CORS_ORIGIN_REGEX,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates_router)
app.include_router(run_router)
app.include_router(validation_router)
app.include_router(config_router)
app.include_router(benchmark_router)
