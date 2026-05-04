"""集群任务管理 API 路由"""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any
import uuid
import asyncio

from .connection import ClusterNode, TaskStatus
from config import CLUSTER_API_TOKEN

router = APIRouter(prefix="/cluster", tags=["Cluster"])

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
async def receive_task(request: Request, node: ClusterNode = Depends(get_cluster_node)):
    verify_token(request)
    data = await request.json()
    required = ["task_type", "description"]
    if not all(k in data for k in required):
        raise HTTPException(status_code=400, detail="Missing required fields")
    task_id = data.get("task_id") or str(uuid.uuid4())
    task_type = data["task_type"]
    description = data["description"]
    parameters = data.get("parameters", {})
    tid = node.create_task(task_type, description, parameters)
    return {"success": True, "task_id": tid, "status": "accepted"}

@router.post("/tasks/batch")
async def receive_task_batch(request: Request, node: ClusterNode = Depends(get_cluster_node)):
    verify_token(request)
    data = await request.json()
    tasks = data.get("tasks", [])
    results = []
    for task in tasks:
        if "task_type" not in task or "description" not in task:
            results.append({"status": "error", "error": "missing fields"})
            continue
        task_id = task.get("task_id") or str(uuid.uuid4())
        tid = node.create_task(task["task_type"], task["description"], task.get("parameters", {}))
        results.append({"task_id": tid, "status": "accepted"})
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
async def ws_updates(websocket: WebSocket, node: ClusterNode = Depends(get_cluster_node)):
    await websocket.accept()
    node.ws_connections.append(websocket)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        if websocket in node.ws_connections:
            node.ws_connections.remove(websocket)
