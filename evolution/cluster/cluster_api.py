"""集群任务管理 API 路由 - 完整协作增强版，支持跨地区手动指定IP加入"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Set, Optional
import uuid
import asyncio
import json

from .connection import ClusterNode, TaskStatus, ClusterClient
from config import CLUSTER_API_TOKEN, PORT_CLUSTER_MANAGER
from logger import logger

# 全局单例：保存全局客户端实例，支持手动跨地区加入后持久化连接
_global_cluster_client: Optional[ClusterClient] = None

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


@router.post("/rooms/manual-join")
async def manual_join_room(request: Request):
    """
    【核心功能】手动指定房主IP/端口，强制跨地区加入房间
    支持场景：本地显卡电脑 + 远程GPU服务器通过互联网串联协作
    
    请求体参数：
    - host_ip: str      - 房主的IP地址（支持公网IP/域名，例如 "123.45.67.89" 或 "mygpu-server.com"）
    - host_port: int    - 房主的TCP监听端口，默认30001（可选，不传自动用默认值）
    - alias_name: str   - 你的花名/别名，显示在协作房间成员列表中
    - model: str        - 你当前使用的模型名称（例如 qwen2.5:7b 或 llama3.1:8b）
    - role: str         - 你的角色，可选 worker/architect/coder 等（默认 worker）
    - password: str     - 房间密码（可选，无密码留空）
    """
    global _global_cluster_client
    verify_token(request)
    
    data = await request.json()
    
    # 校验必填参数
    host_ip = data.get("host_ip")
    if not host_ip:
        raise HTTPException(status_code=400, detail="缺少必填参数 host_ip - 请输入房主的IP地址或域名")
    
    alias_name = data.get("alias_name")
    if not alias_name:
        raise HTTPException(status_code=400, detail="缺少必填参数 alias_name - 请输入你的花名/别名")
    
    model = data.get("model")
    if not model:
        raise HTTPException(status_code=400, detail="缺少必填参数 model - 请输入你使用的模型名称")
    
    # 可选参数默认值
    host_port = data.get("host_port", PORT_CLUSTER_MANAGER)
    role = data.get("role", "worker")
    password = data.get("password", "")
    
    # 生成唯一节点ID
    import uuid
    node_id = str(uuid.uuid4())[:12]
    
    logger.info(f"🚀 [手动跨地区加入] 用户请求加入: 房主={host_ip}:{host_port}, 别名={alias_name}, 模型={model}, 角色={role}")
    
    # 防止重复加入：先关闭已有连接
    if _global_cluster_client is not None:
        logger.info(f"ℹ️  检测到已有活跃连接，先关闭旧连接")
        _global_cluster_client.close()
    
    # 创建新客户端实例
    from .connection import evaluate_capability_simple
    _global_cluster_client = ClusterClient(timeout=15.0)
    
    node_info = {
        "node_id": node_id,
        "name": alias_name,
        "model": model,
        "role": role,
        "mode": "auto"
    }
    
    # 尝试连接房主
    success, reason = _global_cluster_client.join(
        host=host_ip,
        port=int(host_port),
        node_info=node_info,
        password=password
    )
    
    if success:
        logger.info(f"✅ [手动跨地区加入] 成功！已与房主 {host_ip}:{host_port} 建立稳定连接")
        return {
            "success": True,
            "message": "🎉 成功加入远程协作房间！心跳保活线程和任务监听线程已启动",
            "data": {
                "node_id": node_id,
                "alias_name": alias_name,
                "model": model,
                "remote_host": f"{host_ip}:{host_port}"
            }
        }
    else:
        logger.error(f"❌ [手动跨地区加入] 失败: {reason}")
        raise HTTPException(status_code=400, detail=reason)


@router.post("/rooms/manual-leave")
async def manual_leave_room(request: Request):
    """手动断开手动跨地区加入的远程房主连接"""
    global _global_cluster_client
    verify_token(request)
    
    if _global_cluster_client is not None:
        _global_cluster_client.close()
        _global_cluster_client = None
        logger.info(f"👋 [手动跨地区离开] 连接已完全断开")
        return {"success": True, "message": "已安全离开远程房间，所有资源已释放"}
    else:
        return {"success": True, "message": "当前没有活跃的远程连接"}


@router.get("/discovery/local-rooms")
async def get_local_discovered_rooms(request: Request):
    """获取局域网 UDP 自动发现到的所有房间列表"""
    verify_token(request)
    try:
        from evolution.cluster.connection import cluster_manager
        if cluster_manager and hasattr(cluster_manager, 'discovery') and cluster_manager.discovery:
            rooms = cluster_manager.discovery.get_available_rooms()
            return {"success": True, "rooms": rooms}
        else:
            return {"success": True, "rooms": [], "note": "发现服务未启动，请先创建房间或启动扫描"}
    except Exception as e:
        logger.error(f"获取局域网房间列表失败: {e}")
        return {"success": False, "rooms": [], "error": str(e)}
