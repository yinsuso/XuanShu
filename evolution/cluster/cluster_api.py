"""集群任务管理 API 路由"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any
import uuid
import asyncio

from .connection import ClusterNode, TaskStatus
from config import CLUSTER_API_TOKEN

router = APIRouter(tags=["Cluster"])

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
    """WebSocket 更新推送（支持 standalone 模式）"""
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


@router.post("/tasks/{task_id}/approve")
async def approve_task(request: Request, task_id: str, node: ClusterNode = Depends(get_cluster_node)):
    """手动批准任务（用于 manual 模式）"""
    verify_token(request)
    if node.approve_task(task_id):
        return {"success": True, "message": "任务已批准"}
    else:
        raise HTTPException(status_code=404, detail="任务未找到或无法批准")
