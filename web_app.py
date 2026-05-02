     1|import sys
     2|import os
     3|from pathlib import Path
     4|
     5|# Ensure project root is in sys.path for script-mode execution
     6|# This allows absolute imports to work even when running as a script
     7|_current_root = Path(__file__).resolve().parent
     8|if str(_current_root) not in sys.path:
     9|    sys.path.insert(0, str(_current_root))
    10|
    11|
    12|import os
    13|import sys
    14|from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
    15|from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    16|from fastapi.staticfiles import StaticFiles
    17|from fastapi.templating import Jinja2Templates
    18|from fastapi.exceptions import RequestValidationError
    19|from pydantic import BaseModel
    20|from typing import List, Optional
    21|import logging
    22|
    23|from config import WEB_HOST, WEB_PORT, PROJECT_ROOT
    24|from agent import UniversalAgent
    25|from skills import registry, list_skills
    26|from model_providers import config_manager, ModelConfig, ProviderType
    27|from conversation_manager import conversation_manager
    28|from logger import logger
    29|from evolution.cluster.discovery import ClusterDiscovery
    30|
    31|# 初始化 Agent
    32|agent = UniversalAgent(enable_evolution=True)
    33|
    34|app = FastAPI(title="Local Agent v5.0", version="5.0.0")
    35|
    36|# 集群协作发现实例
    37|discovery = ClusterDiscovery()
    38|
    39|# 静态文件与模板
    40|templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "templates")
    41|static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "static")
    42|
    43|if not os.path.isdir(templates_dir):
    44|    raise FileNotFoundError(f"模板目录不存在：{templates_dir}")
    45|
    46|templates = Jinja2Templates(directory=templates_dir)
    47|
    48|if os.path.exists(static_dir):
    49|    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    50|
    51|# 挂载媒体缓存目录，解决 Web 端无法显示本地图片/音频问题
    52|cache_dir = os.path.join(PROJECT_ROOT, "data", "cache")
    53|os.makedirs(cache_dir, exist_ok=True)
    54|if os.path.exists(cache_dir):
    55|    app.mount("/media", StaticFiles(directory=cache_dir), name="media")
    56|
    57|# 全局异常处理
    58|@app.exception_handler(Exception)
    59|async def global_exception_handler(request: Request, exc: Exception):
    60|    logger.error(f"全局异常：{exc}", exc_info=True)
    61|    return JSONResponse(
    62|        status_code=500,
    63|        content={"success": False, "error": f"服务器内部错误：{str(exc)}"}
    64|    )
    65|
    66|@app.exception_handler(RequestValidationError)
    67|async def validation_exception_handler(request: Request, exc: RequestValidationError):
    68|    return JSONResponse(
    69|        status_code=422,
    70|        content={"success": False, "error": f"参数验证失败：{exc.errors()}"}
    71|    )
    72|
    73|# 数据模型
    74|class ChatMessage(BaseModel):
    75|    message: str
    76|    mode: str = "simple"
    77|
    78|class MemoryRequest(BaseModel):
    79|    key: Optional[str] = None
    80|
    81|class EvolutionRequest(BaseModel):
    82|    limit: int = 10
    83|
    84|# 首页
    85|@app.get("/", response_class=HTMLResponse)
    86|async def index(request: Request):
    87|    return templates.TemplateResponse("index.html", {"request": request})
    88|
    89|# API: 对话
    90|@app.post("/api/chat")
    91|async def chat(request: Request):
    92|    try:
    93|        # 尝试获取表单数据（兼容前端 FormData）
    94|        form = await request.form()
    95|        message = form.get("message", "")
    96|        # session_id 暂时 unused，但保留以防后续需要
    97|        # session_id = form.get("session_id", "")
    98|
    99|        if not message:
   100|            return {"success": False, "error": "消息不能为空"}
   101|
   102|        # 🔍 【调试】打印当前实际使用的模型配置
   103|        current_cfg = config_manager.current_config
   104|        if current_cfg:
   105|            logger.info(f"🔥 [Chat Request] 当前模型：{current_cfg.name}")
   106|            logger.info(f" ├─ Provider: {current_cfg.provider.value}")
   107|            logger.info(f" ├─ Model Name: {current_cfg.model_name}")
   108|            logger.info(f" ├─ API Base: {current_cfg.api_base}")
   109|            logger.info(f" └─ API Key: {'✅ 存在' if current_cfg.api_key else '❌ 缺失！'}")
   110|        else:
   111|            logger.warning("⚠️ [Chat Request] 当前配置为 None！将使用默认配置。")
   112|
   113|        response = agent.process_simple(message)
   114|        # 路径转化：将本地缓存路径转化为 Web 可访问的 /media/ 路径
   115|        # 这样前端收到路径后即可直接通过 <img src="/media/xxx.png"> 显示
   116|        web_response = response.replace(os.path.join(PROJECT_ROOT, "data", "cache"), "/media")
   117|        return {"success": True, "response": web_response}
   118|    except Exception as e:
   119|        logger.error(f"Chat error: {e}", exc_info=True)
   120|        raise HTTPException(status_code=500, detail=str(e))
   121|
   122|# API: 删除模型
   123|@app.post("/api/delete_model")
   124|async def delete_model(request: Request):
   125|    try:
   126|        data = await request.json()
   127|        name = data.get("name")
   128|        if not name:
   129|            return {"success": False, "error": "未指定模型名称"}
   130|
   131|        if config_manager.delete_config(name):
   132|            return {"success": True, "message": f"已删除模型：{name}"}
   133|        else:
   134|            return {"success": False, "error": f"删除失败：模型不存在或无法删除"}
   135|    except Exception as e:
   136|        logger.error(f"删除模型失败：{e}", exc_info=True)
   137|        return {"success": False, "error": str(e)}
   138|
   139|# API: 获取对话历史
   140|@app.get("/api/conversations")
   141|async def get_conversations():
   142|    try:
   143|        conversations = conversation_manager.list_conversations(limit=50)
   144|        return {"success": True, "conversations": conversations}
   145|    except Exception as e:
   146|        logger.error(f"获取对话历史失败：{e}", exc_info=True)
   147|        return {"success": False, "error": str(e)}
   148|
   149|# API: 加载对话
   150|@app.post("/api/load_conversation")
   151|async def load_conversation(request: Request):
   152|    try:
   153|        data = await request.json()
   154|        conversation_id = data.get("conversation_id")
   155|        if not conversation_id:
   156|            return {"success": False, "error": "未指定对话 ID"}
   157|
   158|        if conversation_manager.load_conversation(conversation_id):
   159|            return {"success": True, "message": f"已加载对话：{conversation_id}"}
   160|        else:
   161|            return {"success": False, "error": f"加载失败：对话不存在"}
   162|    except Exception as e:
   163|        logger.error(f"加载对话失败：{e}", exc_info=True)
   164|        return {"success": False, "error": str(e)}
   165|
   166|# API: 删除对话
   167|@app.post("/api/delete_conversation")
   168|async def delete_conversation(request: Request):
   169|    try:
   170|        data = await request.json()
   171|        conversation_id = data.get("conversation_id")
   172|        if not conversation_id:
   173|            return {"success": False, "error": "未指定对话 ID"}
   174|
   175|        conversation_manager.delete_conversation(conversation_id)
   176|        return {"success": True, "message": f"已删除对话：{conversation_id}"}
   177|    except Exception as e:
   178|        logger.error(f"删除对话失败：{e}", exc_info=True)
   179|        return {"success": False, "error": str(e)}
   180|
   181|# API: 新建对话（清空当前）
   182|@app.post("/api/new_conversation")
   183|async def new_conversation():
   184|    try:
   185|        new_id = conversation_manager.clear_conversation()
   186|        if new_id:
   187|            return {"success": True, "conversation_id": new_id, "message": "已创建新对话"}
   188|        else:
   189|            return {"success": False, "error": "无法创建新对话"}
   190|    except Exception as e:
   191|        logger.error(f"创建新对话失败：{e}", exc_info=True)
   192|        return {"success": False, "error": str(e)}
   193|
   194|# API: 模型列表
   195|@app.get("/api/models")
   196|async def get_models():
   197|    try:
   198|        models = config_manager.list_configs()
   199|        return {"success": True, "models": models}
   200|    except Exception as e:
   201|        logger.error(f"获取模型列表失败：{e}", exc_info=True)
   202|        return {"success": False, "error": str(e)}
   203|
   204|# API: 当前状态
   205|@app.get("/api/status")
   206|async def get_status():
   207|    try:
   208|        current_model = config_manager.current_config
   209|        if current_model:
   210|            return {"success": True, "config_name": current_model.name, "model_name": current_model.model_name}
   211|        else:
   212|            return {"success": True, "config_name": "未配置", "model_name": ""}
   213|    except Exception as e:
   214|        logger.error(f"获取状态失败：{e}", exc_info=True)
   215|        return {"success": False, "error": str(e)}
   216|
   217|# API: 切换模型
   218|@app.post("/api/switch_model")
   219|async def switch_model(request: Request):
   220|    try:
   221|        form = await request.form()
   222|        name = form.get("name")
   223|        if not name:
   224|            return {"success": False, "error": "未指定模型名称"}
   225|
   226|        if config_manager.set_current(name):
   227|            return {"success": True, "message": f"已切换到模型：{name}"}
   228|        else:
   229|            return {"success": False, "error": f"模型不存在：{name}"}
   230|    except Exception as e:
   231|        logger.error(f"切换模型失败：{e}", exc_info=True)
   232|        return {"success": False, "error": str(e)}
   233|
   234|# API: 保存模型
   235|@app.post("/api/save_model")
   236|async def save_model(request: Request):
   237|    try:
   238|        form = await request.form()
   239|        name = form.get("name")
   240|        provider = form.get("provider")
   241|        model_name = form.get("model_name")
   242|        api_base = form.get("api_base")
   243|        api_key = form.get("api_key", "")
   244|
   245|        if not all([name, provider, model_name, api_base]):
   246|            return {"success": False, "error": "缺少必要参数"}
   247|
   248|        provider_enum = ProviderType(provider)
   249|        config = ModelConfig(
   250|            provider=provider_enum,
   251|            name=name,
   252|            model_name=model_name,
   253|            api_base=api_base,
   254|            api_key=api_key
   255|        )
   256|
   257|        # 检查是否已存在
   258|        existing = config_manager.get_config(name)
   259|        if existing:
   260|            # 更新
   261|            config_manager.update_config(config)
   262|            return {"success": True, "message": "模型配置已更新"}
   263|        else:
   264|            # 新增
   265|            config_manager.add_config(config)
   266|            return {"success": True, "message": "模型配置已保存"}
   267|    except Exception as e:
   268|        logger.error(f"保存模型失败：{e}", exc_info=True)
   269|        return {"success": False, "error": str(e)}
   270|
   271|# API: 技能列表
   272|@app.get("/api/skills")
   273|async def get_skills():
   274|    try:
   275|        skills_list = registry.list_skills()
   276|        return {"success": True, "skills": skills_list}
   277|    except Exception as e:
   278|        return {"success": False, "error": str(e)}
   279|
   280|# API: 核心记忆
   281|@app.get("/api/memory")
   282|async def get_memory(key: Optional[str] = None):
   283|    try:
   284|        if key:
   285|            value = agent.memory.get_core_memory(key)
   286|            return {"success": True, "key": key, "value": value}
   287|        else:
   288|            all_memories = agent.memory.get_all_core_memory()
   289|            return {"success": True, "memories": all_memories}
   290|    except Exception as e:
   291|        return {"success": False, "error": str(e)}
   292|
   293|# API: 导出当前对话
   294|@app.get("/api/export")
   295|async def export_conversation():
   296|    try:
   297|        # 获取当前会话历史
   298|        history = conversation_manager.get_current_conversation()
   299|        if not history:
   300|            return JSONResponse(status_code=404, content={"success": False, "error": "当前没有可导出的对话历史"})
   301|        
   302|        # 转换为 Markdown 格式
   303|        md_content = "# Local Agent 对话记录\n\n"
   304|        md_content += f"导出时间: {os.popen('date').read().strip()}\n"
   305|        md_content += f"模型: {config_manager.current_config.model_name if config_manager.current_config else 'Unknown'}\n\n---\n\n"
   306|        
   307|        for msg in history:
   308|            role = "👤 用户" if msg['role'] == 'user' else "🤖 Agent"
   309|            content = msg['content']
   310|            md_content += f"### {role}\n{content}\n\n"
   311|            md_content += "---\n\n"
   312|        
   313|        # 保存为临时文件
   314|        export_path = os.path.join(PROJECT_ROOT, "data", "current_export.md")
   315|        os.makedirs(os.path.dirname(export_path), exist_ok=True)
   316|        with open(export_path, "w", encoding="utf-8") as f:
   317|            f.write(md_content)
   318|        
   319|        return FileResponse(
   320|            path=export_path, 
   321|            filename="agent_conversation_export.md", 
   322|            media_type='text/markdown'
   323|        )
   324|    except Exception as e:
   325|        logger.error(f"导出对话失败: {e}", exc_info=True)
   326|        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
   327|
   328|# API: 进化记录
   329|@app.get("/api/evolution")
   330|async def get_evolution(limit: int = 10):
   331|    try:
   332|        reflections = agent.memory.get_recent_reflections(limit=limit)
   333|        return {"success": True, "reflections": reflections}
   334|    except Exception as e:
   335|        return {"success": False, "error": str(e)}
   336|
   337|# WebSocket: 实时对话（可选，支持流式输出）
   338|@app.websocket("/ws/chat")
   339|async def websocket_chat(websocket: WebSocket):
   340|    await websocket.accept()
   341|    try:
   342|        while True:
   343|            data = await websocket.receive_text()
   344|            # 简单处理：直接调用 process_simple
   345|            response = agent.process_simple(data)
   346|            await websocket.send_text(response)
   347|    except WebSocketDisconnect:
   348|        logger.info("WebSocket client disconnected")
   349|
   350|# 启动脚本
   351|if __name__ == "__main__":
   352|    import uvicorn
   353|    logger.info(f"🚀 启动 Web 界面：http://{WEB_HOST}:{WEB_PORT}")
   354|    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)

# API: 集群协作 - 创建房间
@app.post("/api/cluster/create")
async def create_cluster(request: Request):
    try:
        data = await request.json()
        room_name = data.get("room_name", "Default-Agent-Room")
        discovery.room_name = room_name
        discovery.start_hosting()
        return {"success": True, "message": f"已创建协作房间：{room_name}", "is_hosting": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# API: 集群协作 - 加入房间
@app.post("/api/cluster/join")
async def join_cluster(request: Request):
    try:
        # 触发扫描并尝试加入
        discovery.scan_and_join() 
        return {"success": True, "message": "正在搜索并尝试加入局域网协作房间...", "found_rooms": discovery.found_rooms}
    except Exception as e:
        return {"success": False, "error": str(e)}

# API: 集群协作 - 状态查询
@app.get("/api/cluster/status")
async def get_cluster_status():
    return {
        "success": True, 
        "is_hosting": discovery.running, 
        "room_name": discovery.room_name,
        "found_rooms": discovery.found_rooms
    }
