from fastapi import APIRouter, Request, HTTPException
from typing import Optional, Dict, Any
import uuid

router = APIRouter()

# 获取集群管理器单例（延迟导入避免循环）
def get_cluster_manager():
    try:
        from .connection import cluster_manager
        return cluster_manager
    except ImportError:
        return None

# 验证集群Token - 安全增强版，禁止空Token
def verify_cluster_token(request: Request):
    from config import CLUSTER_API_TOKEN
    # 强制Token非空，无配置则直接拒绝所有请求
    if not CLUSTER_API_TOKEN or CLUSTER_API_TOKEN.strip() == "":
        raise HTTPException(status_code=503, detail="集群API未正确配置Token，操作已拒绝")
    token = request.headers.get("X-Cluster-Token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if token == CLUSTER_API_TOKEN:
        return True
    raise HTTPException(status_code=401, detail="Invalid cluster token")

@router.post("/rooms")
async def create_room(request: Request, auth: bool = verify_cluster_token):
    """创建协作房间"""
    data = await request.json()
    name = data.get("name")
    password = data.get("password")  # 可选
    description = data.get("description", "")
    creator = data.get("creator", request.client.host if request.client else "unknown")

    if not name:
        raise HTTPException(status_code=400, detail="缺少房间名称")

    manager = get_cluster_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="集群管理器未初始化")

    try:
        room_id = manager.create_room(name=name, owner=creator)
        if not room_id:
            raise HTTPException(status_code=500, detail="创建房间失败")
        room = manager.get_room(room_id)
        return {"success": True, "room": room}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rooms")
async def list_rooms(request: Request, auth: bool = verify_cluster_token):
    """获取房间列表"""
    manager = get_cluster_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="集群管理器未初始化")

    try:
        rooms = manager.get_rooms() if hasattr(manager, 'get_rooms') else []
        safe_rooms = []
        for r in rooms:
            safe_rooms.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "creator": r.get("creator"),
                "node_count": r.get("node_count", 0),
                "description": r.get("description", "")
            })
        return {"success": True, "rooms": safe_rooms}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rooms/join")
async def join_room(request: Request, auth: bool = verify_cluster_token):
    """加入房间"""
    data = await request.json()
    room_id = data.get("room_id")
    password = data.get("password")
    node_id = data.get("node_id")  # 可选

    if not room_id:
        raise HTTPException(status_code=400, detail="缺少房间ID")

    manager = get_cluster_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="集群管理器未初始化")

    try:
        success = manager.join_room(room_id=room_id, password=password, node_id=node_id)
        if not success:
            raise HTTPException(status_code=400, detail="加入房间失败（可能ID错误或密码错误）")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
