from __future__ import annotations
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from app.api_v1.routes import router
from app.conversation.repository import ConversationRepository
from app.conversation.service import ConversationService
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ConfigurationError
from app.data_sources import DataSourceService
from app.engine import TrustworthyQueryEngine
from app.infrastructure.database import Database
from app.knowledge_store import PgVectorKnowledgeStore
from app.planning.bailian import BailianQueryPlanner
from app.planning.base import QueryPlanner
from app.schema_catalog import SchemaCatalogService
from app.text_to_sql.engine import PostgresTextToSqlEngine
from app.text_to_sql.schema import PostgresSchemaRetriever
from app.semantic_layer import SemanticLayerService
from app.benchmark_dashboard import available_benchmark_runs, benchmark_dashboard_payload, benchmark_report_path
from app.memory import MemoryService
from app.context_learning import ContextLearningService
from app.auth import AuthService

def create_app(settings: Settings | None = None, planner: QueryPlanner | None = None) -> FastAPI:
    settings = settings or get_settings()
    database = Database(settings)
    planner_error: AppError | None = None
    if planner is None:
        try:
            planner = BailianQueryPlanner(settings)
        except ConfigurationError as exc:
            planner_error = exc
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_create_schema:
            await database.initialize()
        await app.state.auth_service.bootstrap_admin(
            settings.bootstrap_admin_username, settings.bootstrap_admin_password
        )
        await app.state.data_sources.bootstrap_current()
        yield
        await database.close()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.auth_service = AuthService(database.sessions, settings.secret_encryption_key, settings.auth_token_ttl_seconds)
    repository = ConversationRepository(database.sessions)
    schema_retriever = PostgresSchemaRetriever(settings) if settings.business_database_configured else None
    schema_catalog = SchemaCatalogService(schema_retriever, database.sessions) if schema_retriever else None
    if schema_retriever and schema_catalog:
        schema_retriever.set_override_loader(schema_catalog.load_overrides)
    query_engine = PostgresTextToSqlEngine(settings, schema_retriever) if schema_retriever else TrustworthyQueryEngine()
    app.state.schema_catalog = schema_catalog
    knowledge_store = PgVectorKnowledgeStore(settings) if settings.business_database_configured else None
    app.state.data_sources = DataSourceService(settings, database.sessions, knowledge_store)
    app.state.semantic_layer = SemanticLayerService(database.sessions)
    app.state.memory_service = MemoryService(database.sessions)
    app.state.context_learning = ContextLearningService(database.sessions)
    app.state.data_sources.context_learning = app.state.context_learning
    active_data_sources = app.state.data_sources if settings.business_database_configured else None
    app.state.conversation_service = ConversationService(
        repository, planner, query_engine, active_data_sources, app.state.semantic_layer,
        app.state.memory_service, app.state.context_learning
    ) if planner else None
    app.state.planner_configured = planner is not None
    app.state.planner_error = planner_error
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        if request.url.path.startswith("/api/v1/conversations") and app.state.conversation_service is None:
            error = app.state.planner_error or ConfigurationError("需求分析模型未配置")
            return JSONResponse(status_code=error.status_code, content={"request_id": request.state.request_id, "data": None, "error": {"code": error.code, "message": error.message, "retryable": error.retryable, "details": error.details}, "meta": {}})
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"request_id": request.state.request_id, "data": None, "error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable, "details": exc.details}, "meta": {}})
    app.include_router(router)
    @app.get("/")
    async def index():
        return FileResponse(Path(__file__).parent / "static" / "index.html")
    @app.get("/login")
    async def login_page():
        return FileResponse(Path(__file__).parent / "static" / "login.html")
    @app.get("/admin/users")
    async def users_admin():
        return FileResponse(Path(__file__).parent / "static" / "users-admin.html")
    @app.get("/admin/schema")
    async def schema_admin():
        return FileResponse(Path(__file__).parent / "static" / "schema-admin.html")
    @app.get("/admin/data-sources")
    async def data_source_admin():
        return FileResponse(Path(__file__).parent / "static" / "data-sources.html")
    @app.get("/admin/semantic-layer")
    async def semantic_layer_admin():
        return FileResponse(Path(__file__).parent / "static" / "semantic-layer.html")
    @app.get("/admin/benchmarks")
    async def benchmark_admin():
        return FileResponse(Path(__file__).parent / "static" / "benchmark-dashboard.html")
    @app.get("/admin/memory")
    async def memory_admin():
        return FileResponse(Path(__file__).parent / "static" / "learning-admin.html")
    @app.get("/admin/memory/legacy")
    async def memory_legacy_admin():
        return FileResponse(Path(__file__).parent / "static" / "memory-admin.html")
    @app.get("/api/v1/benchmarks/spider/runs")
    async def spider_benchmark_runs():
        return {"data": available_benchmark_runs(), "error": None}
    @app.get("/api/v1/benchmarks/spider/current")
    async def current_spider_benchmark(run: str = "baseline"):
        try:
            return {"data": benchmark_dashboard_payload(benchmark_report_path(run)), "error": None}
        except KeyError:
            return JSONResponse(status_code=404, content={"data": None, "error": {"code": "RUN_NOT_FOUND", "message": "评测批次不存在", "retryable": False}})
        except RuntimeError as exc:
            return JSONResponse(status_code=503, content={"data": None, "error": {"code": "REPORT_BUSY", "message": str(exc), "retryable": True}})
    return app

app = create_app()
