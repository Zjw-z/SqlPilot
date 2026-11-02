from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from app.api_v1.schemas import BusinessMemoryRequest, ChangePasswordRequest, ConfirmRequest, CreateConversationRequest, CreateDataSourceRequest, CreateUserRequest, ExecuteRequest, FeedbackReviewRequest, LoginRequest, MessageRequest, QueryFeedbackRequest, SchemaCatalogUpdateRequest, SemanticDefinitionRequest, UpdateDataSourceRulesRequest, UpdateUserRequest, UserPreferenceRequest, envelope
from app.auth import Actor, actor_from_request
from app.conversation.service import ConversationService

router = APIRouter(prefix="/api/v1")
def service_from_request(request: Request) -> ConversationService:
    return request.app.state.conversation_service

@router.get("/health")
async def health(request: Request):
    return envelope({"status": "ready" if request.app.state.planner_configured else "configuration_required", "planner": "bailian"}, request.state.request_id)

@router.post("/auth/login")
async def login(payload: LoginRequest, response: Response, request: Request):
    token, actor = await request.app.state.auth_service.login(payload.username, payload.password)
    response.set_cookie("sqlpilot_session", token, httponly=True, samesite="lax", secure=request.app.state.settings.environment == "production", max_age=request.app.state.settings.auth_token_ttl_seconds, path="/")
    return envelope(actor.__dict__, request.state.request_id)

@router.post("/auth/logout")
async def logout(response: Response, request: Request):
    response.delete_cookie("sqlpilot_session", path="/")
    return envelope({"logged_out": True}, request.state.request_id)

@router.get("/auth/me")
async def current_user(request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(actor.__dict__, request.state.request_id)

@router.post("/auth/change-password")
async def change_password(payload: ChangePasswordRequest, response: Response, request: Request, actor: Actor = Depends(actor_from_request)):
    await request.app.state.auth_service.change_password(actor, payload.current_password, payload.new_password)
    response.delete_cookie("sqlpilot_session", path="/")
    return envelope({"changed": True, "login_required": True}, request.state.request_id)

@router.get("/users")
async def list_users(request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.auth_service.list_users(actor), request.state.request_id)

@router.post("/users")
async def create_user(payload: CreateUserRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.auth_service.create_user(actor, payload.model_dump()), request.state.request_id)

@router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UpdateUserRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.auth_service.update_user(actor, user_id, payload.model_dump()), request.state.request_id)

@router.post("/conversations")
async def create_conversation(payload: CreateConversationRequest, request: Request, service: ConversationService = Depends(service_from_request), actor: Actor = Depends(actor_from_request)):
    return envelope(await service.create(actor.tenant_id, actor.user_id, payload.title), request.state.request_id)

@router.get("/conversations")
async def list_conversations(request: Request, limit: int = 50, service: ConversationService = Depends(service_from_request), actor: Actor = Depends(actor_from_request)):
    return envelope(await service.list(actor.tenant_id, actor.user_id, limit), request.state.request_id)

@router.get("/conversations/{conversation_id}")
async def conversation_detail(conversation_id: str, request: Request, service: ConversationService = Depends(service_from_request), actor: Actor = Depends(actor_from_request)):
    return envelope(await service.detail(conversation_id, actor.tenant_id, actor.user_id), request.state.request_id)

@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, payload: MessageRequest, request: Request, service: ConversationService = Depends(service_from_request), actor: Actor = Depends(actor_from_request)):
    return envelope(await service.send_message(conversation_id, payload.content, payload.base_plan_version, actor.tenant_id, actor.user_id, payload.data_source_id), request.state.request_id)

@router.post("/conversations/{conversation_id}/confirm")
async def confirm_plan(conversation_id: str, payload: ConfirmRequest, request: Request, service: ConversationService = Depends(service_from_request), actor: Actor = Depends(actor_from_request)):
    return envelope(await service.confirm(conversation_id, payload.plan_version, payload.plan_hash, actor.tenant_id, actor.user_id), request.state.request_id)

@router.post("/conversations/{conversation_id}/execute")
async def execute_plan(conversation_id: str, payload: ExecuteRequest, request: Request, service: ConversationService = Depends(service_from_request), actor: Actor = Depends(actor_from_request)):
    return envelope(await service.execute(conversation_id, payload.plan_version, actor.tenant_id, actor.user_id), request.state.request_id)

@router.get("/schema/catalog")
async def schema_catalog(request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.schema_catalog.list_catalog(actor.tenant_id), request.state.request_id)

@router.put("/schema/catalog")
async def update_schema_catalog(payload: SchemaCatalogUpdateRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.schema_catalog.upsert(actor.tenant_id, payload.model_dump()), request.state.request_id)

@router.get("/data-sources")
async def list_data_sources(request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.list(actor.tenant_id), request.state.request_id)

@router.post("/data-sources")
async def create_data_source(payload: CreateDataSourceRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.create(actor.tenant_id, payload.model_dump()), request.state.request_id)

@router.post("/data-sources/{source_id}/test")
async def test_data_source(source_id: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.test(actor.tenant_id, source_id), request.state.request_id)

@router.put("/data-sources/{source_id}/business-rules")
async def update_source_rules(source_id: str, payload: UpdateDataSourceRulesRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.update_business_rules(
        actor.tenant_id, source_id, payload.business_rules
    ), request.state.request_id)

@router.post("/data-sources/{source_id}/sync")
async def sync_data_source(source_id: str, background_tasks: BackgroundTasks, request: Request, actor: Actor = Depends(actor_from_request)):
    job = await request.app.state.data_sources.queue_sync(actor.tenant_id, source_id)
    if not job.get("duplicate"):
        background_tasks.add_task(
            request.app.state.data_sources.sync,
            actor.tenant_id,
            source_id,
            job["job_id"],
        )
    return envelope(job, request.state.request_id)

@router.get("/data-sources/{source_id}/sync/latest")
async def latest_sync(source_id: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.latest_job(actor.tenant_id, source_id), request.state.request_id)

@router.get("/data-sources/{source_id}/knowledge/search")
async def search_knowledge(source_id: str, q: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.search(actor.tenant_id, source_id, q), request.state.request_id)

@router.get("/data-sources/{source_id}/schema/tables")
async def source_schema_tables(source_id: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.schema_tables(actor.tenant_id, source_id), request.state.request_id)

@router.get("/data-sources/{source_id}/schema/table-detail")
async def source_table_detail(source_id: str, schema_name: str, table_name: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.table_detail(actor.tenant_id, source_id, schema_name, table_name), request.state.request_id)

@router.get("/data-sources/{source_id}/schema/dimension-values")
async def source_dimension_values(source_id: str, schema_name: str, table_name: str, column_name: str, request: Request, limit: int = 50, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.data_sources.dimension_values(actor.tenant_id, source_id, schema_name, table_name, column_name, limit), request.state.request_id)

@router.get("/data-sources/{source_id}/semantic-definitions")
async def semantic_definitions(source_id: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.semantic_layer.list_definitions(actor.tenant_id, source_id), request.state.request_id)

@router.put("/data-sources/{source_id}/semantic-definitions")
async def upsert_semantic_definition(source_id: str, payload: SemanticDefinitionRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.semantic_layer.upsert_definition(
        actor.tenant_id, source_id, payload.model_dump()
    ), request.state.request_id)

@router.get("/data-sources/{source_id}/semantic-observations")
async def semantic_observations(source_id: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.semantic_layer.observations(actor.tenant_id, source_id), request.state.request_id)

@router.get("/semantic-layer/compiler-capabilities")
async def compiler_capabilities(request: Request):
    return envelope(request.app.state.semantic_layer.compiler_capabilities(), request.state.request_id)

@router.get("/memory/preferences")
async def memory_preferences(request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.memory_service.list_preferences(actor.tenant_id, actor.user_id), request.state.request_id)

@router.put("/memory/preferences")
async def put_memory_preference(payload: UserPreferenceRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.memory_service.put_preference(actor.tenant_id, actor.user_id, payload.model_dump()), request.state.request_id)

@router.get("/memory/business")
async def business_memories(request: Request, source_id: str | None = None, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.memory_service.list_business(actor.tenant_id, source_id), request.state.request_id)

@router.put("/memory/business")
async def put_business_memory(payload: BusinessMemoryRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    data = payload.model_dump()
    if data["expires_at"]:
        from datetime import datetime
        data["expires_at"] = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    return envelope(await request.app.state.memory_service.put_business(actor.tenant_id, data), request.state.request_id)

@router.delete("/memory/business/{memory_id}")
async def delete_business_memory(memory_id: str, request: Request, actor: Actor = Depends(actor_from_request)):
    await request.app.state.memory_service.delete_business(actor.tenant_id, memory_id)
    return envelope({"deleted": True}, request.state.request_id)

@router.post("/query-executions/{execution_id}/feedback")
async def submit_query_feedback(execution_id: str, payload: QueryFeedbackRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.context_learning.submit_feedback(
        actor.tenant_id, actor.user_id, execution_id, payload.model_dump()
    ), request.state.request_id)

@router.get("/learning/feedback")
async def learning_feedback(request: Request, status: str | None = None, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.context_learning.list_feedback(actor.tenant_id, status), request.state.request_id)

@router.post("/learning/feedback/{feedback_id}/review")
async def review_learning_feedback(feedback_id: str, payload: FeedbackReviewRequest, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.context_learning.review_feedback(
        actor.tenant_id, feedback_id, actor.user_id, payload.model_dump()
    ), request.state.request_id)

@router.get("/learning/query-paths")
async def verified_query_paths(request: Request, source_id: str | None = None, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.context_learning.list_paths(actor.tenant_id, source_id), request.state.request_id)

@router.get("/data-sources/{source_id}/knowledge/dependency-graph")
async def knowledge_dependency_graph(source_id: str, request: Request, actor: Actor = Depends(actor_from_request)):
    return envelope(await request.app.state.context_learning.dependency_graph(
        actor.tenant_id, source_id
    ), request.state.request_id)
