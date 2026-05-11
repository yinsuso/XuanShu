"""集群任务管理 API 路由 - 完整协作增强版"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Set
import uuid
import asyncio
import json

from .connection import ClusterNode, TaskStatus
from config import CLUSTER_API_TOKEN
from logger import logger

router = APIRouter(tags=["Cluster"])

# WebSocket 连接池 - 用于向所有浏览器广播事件
connected_ws_clients: Set[WebSocket] = set()

def verify_token(request: Request):
    if CLUSTER_API_TOKEN:
        token = request.headers.get("X-Cluster-Token")
        if token != CLUSTER_API_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized")

def get_cluster_node(request: Request) -> ClusterNode:
    node = getattr(request.app.state, "cluster_node", None)
    if not node:
        raise HTTPException(status_code=503, detail="Cluster node not initialized")
    return node

async def broadcast_to_all_clients(event: Dict[str, Any]):
    """向所有连接的浏览器WebSocket客户端广播事件（终极修复版，不会遗漏任何客户端）"""
    disconnected = set()
    logger.debug(f"[WebSocket 广播] 正在推送事件类型: {event.get('type')}, 客户端数: {len(connected_ws_clients)}")
    for ws in connected_ws_clients:
        try:
            await ws.send_json(event)
            logger.debug(f"[WebSocket 广播成功] 已推送")
        except Exception as e:
            logger.warning(f"广播WebSocket客户端失败: {e}")
            disconnected.add(ws)
    for ws in disconnected:
        connected_ws_clients.discard(ws)
    logger.debug(f"[WebSocket 广播完成] 剩余客户端数: {len(connected_ws_clients)}")
    return len(connected_ws_clients) - len(disconnected)

@router.post("/tasks")
async def receive_task(request: Request):
    verify_token(request)
    data = await request.json()
    required = ["task_type", "description"]
    if not all(k in data for k in required):
        raise HTTPException(status_code=400, detail="Missing required fields")
    task_type = data["task_type"]
    description = data["description"]
    parameters = data.get("parameters", {})
    manager = request.app.state.cluster_manager
    if not manager:
        raise HTTPException(status_code=503, detail="Cluster manager not available")
    task_id = manager.assign_task(task_type, description, parameters)
    if task_id:
        return {"success": True, "task_id": task_id, "status": "assigned"}
    else:
        raise HTTPException(status_code=503, detail="无可用节点接受任务")

@router.post("/tasks/batch")
async def receive_task_batch(request: Request):
    verify_token(request)
    data = await request.json()
    tasks = data.get("tasks", [])
    results = []
    manager = request.app.state.cluster_manager
    if not manager:
        raise HTTPException(status_code=503, detail="Cluster manager not available")
    for task in tasks:
        if "task_type" not in task or "description" not in task:
            results.append({"status": "error", "error": "missing fields"})
            continue
        task_type = task["task_type"]
        description = task["description"]
        parameters = task.get("parameters", {})
        task_id = manager.assign_task(task_type, description, parameters)
        if task_id:
            results.append({"task_id": task_id, "status": "assigned"})
        else:
            results.append({"status": "error", "error": "no available node"})
    return {"results": results}

@router.get("/status")
async def cluster_status(request: Request, node: ClusterNode = Depends(get_cluster_node)):
    verify_token(request)
    busy = False
    with node._task_lock:
        for t in node.tasks.values():
            if t["status"] in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value):
                busy = True
                break
    return {
        "node_id": node.node_id,
        "role": node.role,
        "capability_score": node.capability_score,
        "last_heartbeat": node.last_heartbeat,
        "state": "busy" if busy else "idle",
        "tasks_count": {
            "total": len(node.tasks),
            "pending": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.PENDING.value),
            "running": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.RUNNING.value),
            "completed": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.COMPLETED.value),
            "failed": sum(1 for t in node.tasks.values() if t["status"] == TaskStatus.FAILED.value),
        }
    }

@router.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket):
    """WebSocket 更新推送 - 完整协作增强版，支持心跳和事件双向同步"""
    await websocket.accept()
    connected_ws_clients.add(websocket)
    logger.info(f"[WebSocket] 新客户端连接，当前共 {len(connected_ws_clients)} 个连接")
    
    app_state = websocket.scope.get("app", None)
    manager = None
    if app_state:
        manager = getattr(app_state.state, "cluster_manager", None)
    
    if manager and hasattr(manager, 'own_node') and manager.own_node:
        if not hasattr(manager.own_node, 'ws_connections'):
            manager.own_node.ws_connections = []
        manager.own_node.ws_connections.append(websocket)
    
    # 向新连接的客户端发送一个初始确认包，确认连接成功
    try:
        await websocket.send_json({
            "type": "welcome",
            "message": "WebSocket 连接已建立，协作模式就绪",
            "timestamp": asyncio.get_event_loop().time()
        })
        logger.info("[WebSocket] 欢迎包已发送")
    except Exception as e:
        logger.warning(f"[WebSocket 欢迎包发送失败: {e}]")
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    logger.debug(f"[WebSocket] 收到消息: {msg}")
                    
                    # 响应客户端心跳包
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong", "pong": True})
                except Exception as parse_err:
                    logger.debug(f"[WebSocket] 消息解析失败: {parse_err}")
            except WebSocketDisconnect:
                break
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        logger.info("[WebSocket] 客户端断开连接")
    finally:
        connected_ws_clients.discard(websocket)
        if manager and hasattr(manager, 'own_node') and manager.own_node:
            if hasattr(manager.own_node, 'ws_connections'):
                try:
                    manager.own_node.ws_connections.remove(websocket)
                except ValueError:
                    pass
        logger.info(f"[WebSocket] 清理后剩余客户端数: {len(connected_ws_clients)}")


@router.post("/tasks/{task_id}/approve")
async def approve_task(request: Request, task_id: str, node: ClusterNode = Depends(get_cluster_node)):
    """手动批准任务（用于 manual 模式）"""
    verify_token(request)
    if node.approve_task(task_id):
        return {"success": True, "message": "任务已批准"}
    else:
        raise HTTPException(status_code=404, detail="任务未找到或无法批准")
