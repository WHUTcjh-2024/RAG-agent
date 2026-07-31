import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.commerce import router as commerce_router
from app.api.products import router as products_router
from app.api.search import router as search_router
from app.core.agent.errors import AgentException, invalid_input
from app.core.request_id import RequestIdMiddleware, create_request_id


APP_LOG_LEVEL = getattr(
    logging,
    os.getenv("APP_LOG_LEVEL", "INFO").upper(),
    logging.INFO,
)
app_logger = logging.getLogger("app")
app_logger.setLevel(APP_LOG_LEVEL)
if not app_logger.handlers:
    app_handler = logging.StreamHandler()
    app_handler.setLevel(APP_LOG_LEVEL)
    app_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    app_logger.addHandler(app_handler)

app = FastAPI(
    title="RAG Multimodal Shopping Agent",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-Agent-Task-Id"],
)
app.add_middleware(RequestIdMiddleware)
app.include_router(search_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(commerce_router, prefix="/api")

IMAGE_DIR = Path(__file__).resolve().parents[1] / "data" / "sample" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=IMAGE_DIR), name="media")


def request_id_from(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    return request_id or create_request_id()


@app.exception_handler(AgentException)
async def agent_exception_handler(
    request: Request,
    error: AgentException,
) -> JSONResponse:
    envelope = error.to_envelope(request_id_from(request))
    return JSONResponse(
        status_code=error.status_code,
        content=envelope.model_dump(mode="json"),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    agent_paths = {"/api/chat", "/api/chat/stream", "/api/session", "/api/compare"}
    if request.url.path in agent_paths:
        classified = invalid_input(
            "Agent request validation failed.",
            details={"errors": jsonable_encoder(error.errors())},
        )
        envelope = classified.to_envelope(request_id_from(request))
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(mode="json"),
        )
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(error.errors())})


@app.get("/health")
def health() -> dict:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    checks = {
        "catalog": (data_dir / "sqlite" / "app.db").is_file(),
        "text_index": (data_dir / "vector_store" / "text" / "embeddings.npy").is_file(),
        "image_index": (data_dir / "vector_store" / "image" / "embeddings.npy").is_file(),
    }
    return {
        "status": "ready" if all(checks.values()) else "degraded",
        "version": app.version,
        "checks": checks,
    }
