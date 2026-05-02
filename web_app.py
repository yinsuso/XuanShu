import sys
import os
from pathlib import Path

# Ensure project root is in sys.path for script-mode execution
# This allows absolute imports to work even when running as a script
_current_root = Path(__file__).resolve().parent
if str(_current_root) not in sys.path:
    sys.path.insert(0, str(_current_root))


import os
import sys
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import List, Optional
import logging
import sqlite3

from config import WEB_HOST, WEB_PORT, PROJECT_ROOT
from agent import UniversalAgent
from skills import registry, list_skills
from model_providers import config_manager, ModelConfig, ProviderType
from conversation_manager import conversation_manager
from logger import logger
from evolution.cluster.discovery import ClusterDiscovery

# 初始化 Agent
agent = UniversalAgent(enable_evolution=True)

app = FastAPI(title="Local Agent v5.0", version="5.0.0")

# 集群协作发现实例
discovery = ClusterDiscovery()

# 静态文件与模板
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "templates")
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "static")

if not os.path.isdir(templates_dir):
    raise FileNotFoundError(f"模板目录不存在：{templates_dir}")

templates = Jinja2Templates(directory=templates_dir)

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 挂载媒体缓存目录，解决 Web 端无法显示本地图片/音频问题
cache_dir = os.path.join(PROJECT_ROOT, "data", "cache")
os.makedirs(cache_dir, exist_ok=True)
if os.path.exists(cache_dir):
    app.mount("/media", StaticFiles(directory=cache_dir), name="media")

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"全局异常：{exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"服务器内部错误：{str(exc)}"}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": f"参数验证失败：{exc.errors()}"}
    )

# 数据模型
class ChatMessage(BaseModel):
    message: str
    mode: str = "simple"

class MemoryRequest(BaseModel):
    key: Optional[str] = None

class EvolutionRequest(BaseModel):
    limit: int = 10

# 首页
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# API: 对话
@app.post("/api/chat")
async def chat(request: Request):
    try:
        # 尝试获取表单数据（兼容前端 FormData）
        form = await request.form()
        message = form.get("message", "")
        # session_id 暂时 unused，但保留以防后续需要
        # session_id = form.get("session_id", "")

        if not message:
            return {"success": False, "error": "消息不能为空"}

        # 🔍 【调试】打印当前实际使用的模型配置
        current_cfg = config_manager.current_config
        if current_cfg:
            logger.info(f"🔥 [Chat Request] 当前模型：{current_cfg.name}")
            logger.info(f" ├─ Provider: {current_cfg.provider.value}")
            logger.info(f" ├─ Model Name: {current_cfg.model_name}")
            logger.info(f" ├─ API Base: {current_cfg.api_base}")
            logger.info(f" └─ API Key: {'✅ 存在' if current_cfg.api_key else '❌ 缺失！'}")
        else:
            logger.warning("⚠️ [Chat Request] 当前配置为 None！将使用默认配置。")

        response = agent.process_adaptive(message)
        # 路径转化：将本地缓存路径转化为 Web 可访问的 /media/ 路径
        # 这样前端收到路径后即可直接通过 <img src="/media/xxx.png"> 显示
        web_response = response.replace(os.path.join(PROJECT_ROOT, "data", "cache"), "/media")
        return {"success": True, "response": web_response}
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# API: 删除模型
@app.post("/api/delete_model")
async def delete_model(request: Request):
    try:
        data = await request.json()
        name = data.get("name")
        if not name:
            return {"success": False, "error": "未指定模型名称"}

        if config_manager.delete_config(name):
            return {"success": True, "message": f"已删除模型：{name}"}
        else:
            return {"success": False, "error": f"删除失败：模型不存在或无法删除"}
    except Exception as e:
        logger.error(f"删除模型失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 获取对话历史
@app.get("/api/conversations")
async def get_conversations():
    try:
        conversations = conversation_manager.list_conversations(limit=50)
        return {"success": True, "conversations": conversations}
    except Exception as e:
        logger.error(f"获取对话历史失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 加载对话
@app.post("/api/load_conversation")
async def load_conversation(request: Request):
    try:
        data = await request.json()
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return {"success": False, "error": "未指定对话 ID"}

        if conversation_manager.load_conversation(conversation_id):
            return {"success": True, "message": f"已加载对话：{conversation_id}"}
        else:
            return {"success": False, "error": f"加载失败：对话不存在"}
    except Exception as e:
        logger.error(f"加载对话失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 删除对话
@app.post("/api/delete_conversation")
async def delete_conversation(request: Request):
    try:
        data = await request.json()
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return {"success": False, "error": "未指定对话 ID"}

        conversation_manager.delete_conversation(conversation_id)
        return {"success": True, "message": f"已删除对话：{conversation_id}"}
    except Exception as e:
        logger.error(f"删除对话失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 新建对话（清空当前）
@app.post("/api/new_conversation")
async def new_conversation():
    try:
        new_id = conversation_manager.clear_conversation()
        if new_id:
            return {"success": True, "conversation_id": new_id, "message": "已创建新对话"}
        else:
            return {"success": False, "error": "无法创建新对话"}
    except Exception as e:
        logger.error(f"创建新对话失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 模型列表
@app.get("/api/models")
async def get_models():
    try:
        models = config_manager.list_configs()
        return {"success": True, "models": models}
    except Exception as e:
        logger.error(f"获取模型列表失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 当前状态
@app.get("/api/status")
async def get_status():
    try:
        current_model = config_manager.current_config
        if current_model:
            return {"success": True, "config_name": current_model.name, "model_name": current_model.model_name}
        else:
            return {"success": True, "config_name": "未配置", "model_name": ""}
    except Exception as e:
        logger.error(f"获取状态失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 切换模型
@app.post("/api/switch_model")
async def switch_model(request: Request):
    try:
        form = await request.form()
        name = form.get("name")
        if not name:
            return {"success": False, "error": "未指定模型名称"}

        if config_manager.set_current(name):
            return {"success": True, "message": f"已切换到模型：{name}"}
        else:
            return {"success": False, "error": f"模型不存在：{name}"}
    except Exception as e:
        logger.error(f"切换模型失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 保存模型
@app.post("/api/save_model")
async def save_model(request: Request):
    try:
        form = await request.form()
        name = form.get("name")
        provider = form.get("provider")
        model_name = form.get("model_name")
        api_base = form.get("api_base")
        api_key = form.get("api_key", "")

        if not all([name, provider, model_name, api_base]):
            return {"success": False, "error": "缺少必要参数"}

        provider_enum = ProviderType(provider)
        config = ModelConfig(
            provider=provider_enum,
            name=name,
            model_name=model_name,
            api_base=api_base,
            api_key=api_key
        )

        # 检查是否已存在
        existing = config_manager.get_config(name)
        if existing:
            # 更新
            config_manager.update_config(config)
            return {"success": True, "message": "模型配置已更新"}
        else:
            # 新增
            config_manager.add_config(config)
            return {"success": True, "message": "模型配置已保存"}
    except Exception as e:
        logger.error(f"保存模型失败：{e}", exc_info=True)
        return {"success": False, "error": str(e)}

# API: 技能列表
@app.get("/api/skills")
async def get_skills():
    try:
        skills_list = registry.list_skills()
        return {"success": True, "skills": skills_list}
    except Exception as e:
        return {"success": False, "error": str(e)}

# API: 核心记忆
@app.get("/api/memory")
async def get_memory(key: Optional[str] = None):
    try:
        if key:
            value = agent.memory.get_core_memory(key)
            return {"success": True, "key": key, "value": value}
        else:
            all_memories = agent.memory.get_all_core_memory()
            return {"success": True, "memories": all_memories}
    except Exception as e:
        return {"success": False, "error": str(e)}

# API: 导出当前对话
@app.get("/api/export")
async def export_conversation():
 try:
  # 获取当前会话历史
  history = conversation_manager.get_current_conversation()
  if not history:
   return JSONResponse(status_code=404, content={"success": False, "error": "当前没有可导出的对话历史"})
  
  # 转换为 Markdown 格式
  md_content = "# Local Agent 对话记录\n\n"
  md_content += f"导出时间：{os.popen('date').read().strip()}\n"
  md_content += f"模型：{config_manager.current_config.model_name if config_manager.current_config else 'Unknown'}\n\n---\n\n"
  
  for msg in history:
   role = "👤 用户" if msg['role'] == 'user' else "🤖 Agent"
   content = msg['content']
   md_content += f"### {role}\n{content}\n\n"
   md_content += "---\n\n"
  
  # 保存为临时文件
  export_path = os.path.join(PROJECT_ROOT, "data", "current_export.md")
  os.makedirs(os.path.dirname(export_path), exist_ok=True)
  with open(export_path, "w", encoding="utf-8") as f:
   f.write(md_content)
  
  return FileResponse(
   path=export_path, 
   filename="agent_conversation_export.md", 
   media_type='text/markdown'
  )
 except Exception as e:
  logger.error(f"导出对话失败：{e}", exc_info=True)
  return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# API: Token 统计
@app.get("/api/token-stats")
async def get_token_stats():
 try:
  db_path = os.path.join(PROJECT_ROOT, "data", "token_stats.db.bak")
  if not os.path.exists(db_path):
   # 尝试 .db 版本
   db_path = os.path.join(PROJECT_ROOT, "data", "token_stats.db")
  
  if not os.path.exists(db_path):
   return {"success": True, "data": {"total": 0, "by_model": [], "by_date": []}}
  
  conn = sqlite3.connect(db_path)
  cursor = conn.cursor()
  
  # 总统计
  cursor.execute("SELECT SUM(total_tokens), SUM(prompt_tokens), SUM(completion_tokens) FROM token_usage")
  total_row = cursor.fetchone()
  total_stats = {
   "total_tokens": total_row[0] or 0,
   "prompt_tokens": total_row[1] or 0,
   "completion_tokens": total_row[2] or 0
  }
  
  # 按模型统计
  cursor.execute("SELECT model_name, SUM(total_tokens), COUNT(*) FROM token_usage GROUP BY model_name ORDER BY SUM(total_tokens) DESC")
  by_model = [{"model": row[0], "total": row[1], "count": row[2]} for row in cursor.fetchall()]
  
  # 按日期统计 (最近 7 天)
  cursor.execute("""
   SELECT date(timestamp), SUM(total_tokens) 
   FROM token_usage 
   WHERE date(timestamp) >= date('now', '-7 days')
   GROUP BY date(timestamp) 
   ORDER BY date(timestamp)
  """)
  by_date = [{"date": row[0], "total": row[1]} for row in cursor.fetchall()]
  
  conn.close()
  
  return {
   "success": True,
   "data": {
    "total": total_stats,
    "by_model": by_model,
    "by_date": by_date
   }
  }
 except Exception as e:
  logger.error(f"获取 Token 统计失败：{e}", exc_info=True)
  return {"success": False, "error": str(e)}

# API: 进化记录
@app.get("/api/evolution")
async def get_evolution(limit: int = 10):
    try:
        reflections = agent.memory.get_recent_reflections(limit=limit)
        return {"success": True, "reflections": reflections}
    except Exception as e:
        return {"success": False, "error": str(e)}

# WebSocket: 实时对话（可选，支持流式输出）
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # 简单处理：直接调用 process_simple
            response = agent.process_simple(data)
            await websocket.send_text(response)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")

# 启动脚本
if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 启动 Web 界面：http://{WEB_HOST}:{WEB_PORT}")
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)

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