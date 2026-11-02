from pathlib import Path


INDEX_HTML = Path(__file__).parents[1] / "app" / "static" / "index.html"


def test_analysis_panel_can_expand_and_collapse():
    page = INDEX_HTML.read_text(encoding="utf-8")

    assert "id='expandAnalysis'" in page
    assert "analysis-expanded" in page
    assert "event.key==='Escape'" in page
    assert "aria-expanded" in page
    assert "展开分析区" in page
    assert "收起分析区" in page
    assert "position:'fixed'" in page
    assert "top:'78px'" in page
    assert "right:'18px'" in page
    assert 'M14 3h7v7M10 21H3v-7' in page
    assert 'M21 10h-7V3M3 14h7v7' in page
    assert "rankingText=hasRanking" in page
    assert ":'不排序'" in page
    assert "dataSourceSelect" in page
    assert "data_source_id:selectedSource" in page


def test_columns_have_an_accessible_resizable_divider():
    page = INDEX_HTML.read_text(encoding="utf-8")

    assert "id='columnResizeHandle'" in page
    assert "role','separator'" in page
    assert "cursor:col-resize" in page
    assert "pointerdown" in page
    assert "dblclick" in page
    assert "ArrowLeft" in page and "ArrowRight" in page
    assert "sqlpilot-chat-ratio" in page


def test_query_results_include_insight_and_adaptive_chart_ui():
    page = INDEX_HTML.read_text(encoding="utf-8")

    assert "renderInsight(r.insight)" in page
    assert "renderVisualization(r.visualization)" in page
    assert "AI 数据解读" in page
    assert "仅依据本次实际查询结果生成" in page
    assert "spec.type==='line'" in page
    assert "完整结果请查看下方表格" in page


def test_network_failures_are_explained_and_can_be_retried():
    page = INDEX_HTML.read_text(encoding="utf-8")

    assert "暂时无法连接查询服务，请检查服务状态后重试。" in page
    assert "error.code='NETWORK_ERROR'" in page
    assert "retry.textContent='重新发送'" in page
    assert "retry.onclick=()=>sendMessage(text)" in page


def test_new_query_and_history_list_are_available():
    page = INDEX_HTML.read_text(encoding="utf-8")

    assert "新建查询" in page
    assert "历史查询" in page
    assert "startNewQuery" in page
    assert "openHistory" in page
    assert "loadHistory" in page
    assert "completed.result||" in page
    assert "这条历史查询还没有成功执行的结果" in page
    assert "/admin/memory" in page
    assert "/api/v1/conversations?limit=50" in page
    assert "当前记录会保留在历史列表中" in page


def test_memory_admin_has_governance_controls():
    page = (Path("app") / "static" / "memory-admin.html").read_text(encoding="utf-8")
    assert "只有标记为“已认证”的业务记忆" in page
    assert "/api/v1/memory/preferences" in page
    assert "/api/v1/memory/business" in page


def test_schema_admin_page_has_catalog_maintenance_flow():
    page = (INDEX_HTML.parent / "schema-admin.html").read_text(encoding="utf-8")

    assert "/api/v1/schema/catalog" in page
    assert "业务中文名" in page
    assert "业务别名" in page
    assert "允许RAG检索" in page
    assert "允许用于SQL生成" in page


def test_data_source_page_exposes_automatic_knowledge_setup():
    page = (INDEX_HTML.parent / "data-sources.html").read_text(encoding="utf-8")

    assert "/api/v1/data-sources" in page
    assert "构建知识库" in page
    assert "测试连接" in page
    assert "测试检索" in page
    assert "应用密钥加密保存" in page
    assert "测试Schema RAG检索" in page
    assert "检测到相近的业务口径" in page
    assert "技术匹配详情" in page
    assert "runSchemaSearch" in page
    assert "rag-search-bar" in page
    assert "rag-item" in page
    assert "aria-labelledby=\"ragTitle\"" in page
    assert "共召回" in page


def test_semantic_layer_admin_separates_certification_and_observations():
    page = (INDEX_HTML.parent / "semantic-layer.html").read_text(encoding="utf-8")

    assert "认证定义优先于模型和RAG" in page
    assert "确认历史只用于审核参考" in page
    assert "/semantic-definitions" in page
    assert "/semantic-observations" in page
    assert "/semantic-layer/compiler-capabilities" in page
    assert "指标管理" in page
    assert "维度与时间" in page
    assert "码值字典" in page
    assert "数据规则" in page
    assert "表关系" in page
    assert "对账用例" in page
    assert "buildDefinition" in page
    assert "原始 JSON" not in page
