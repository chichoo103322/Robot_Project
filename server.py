import os
import json
import asyncio
import sqlite3
from typing import Any, Dict, Set
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from brain.brain_node import nlp_processor

# 实例化 FastAPI 应用
app = FastAPI(title="机器人控制中心", description="基于大模型和行为树的智能机器人控制系统")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tasks.db")


class ConnectionHub:
    def __init__(self) -> None:
        self.frontend_clients: Set[WebSocket] = set()
        self.robot_clients: Set[WebSocket] = set()

    async def connect_frontend(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.frontend_clients.add(websocket)

    async def connect_robot(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.robot_clients.add(websocket)

    def disconnect_frontend(self, websocket: WebSocket) -> None:
        self.frontend_clients.discard(websocket)

    def disconnect_robot(self, websocket: WebSocket) -> None:
        self.robot_clients.discard(websocket)

    async def broadcast_frontend(self, payload: Dict[str, Any]) -> None:
        dead_sockets = []
        data = json.dumps(payload, ensure_ascii=False)
        for ws in self.frontend_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            self.frontend_clients.discard(ws)

    async def broadcast_robot(self, payload: Dict[str, Any]) -> None:
        dead_sockets = []
        data = json.dumps(payload, ensure_ascii=False)
        for ws in self.robot_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            self.robot_clients.discard(ws)


hub = ConnectionHub()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_command TEXT NOT NULL,
                task_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def insert_task(raw_command: str, task_data: Dict[str, Any]) -> int:
    task_json_text = json.dumps(task_data, ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO task_queue (raw_command, task_json, status)
            VALUES (?, ?, 'PENDING')
            """,
            (raw_command, task_json_text),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_task_status(task_id: int, status: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE task_queue SET status = ? WHERE id = ?",
            (status, task_id),
        )
        conn.commit()


def parse_frontend_command(raw_text: str) -> str:
    stripped = raw_text.strip()
    if not stripped:
        raise ValueError("指令为空")
    try:
        data = json.loads(stripped)
        if isinstance(data, dict) and "text" in data:
            text = str(data["text"]).strip()
            if text:
                return text
            raise ValueError("text 字段为空")
    except json.JSONDecodeError:
        pass
    return stripped


@app.on_event("startup")
async def on_startup() -> None:
    init_db()

# GET 接口：返回前端页面
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    """读取并返回 index.html 页面"""
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.websocket("/ws/frontend")
async def ws_frontend(websocket: WebSocket):
    await hub.connect_frontend(websocket)
    await websocket.send_json({"type": "connected", "role": "frontend"})

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                command = parse_frontend_command(raw_message)
                await hub.broadcast_frontend(
                    {
                        "type": "frontend_status",
                        "status": "PROCESSING",
                        "raw_command": command,
                    }
                )

                # nlp_processor 为同步调用，放到线程池以避免阻塞事件循环
                task_json = await asyncio.to_thread(nlp_processor, command)
                task_id = insert_task(command, task_json)

                await hub.broadcast_frontend(
                    {
                        "type": "task_created",
                        "task_id": task_id,
                        "status": "PENDING",
                        "task_json": task_json,
                    }
                )

                await hub.broadcast_robot(
                    {
                        "type": "task_dispatch",
                        "task_id": task_id,
                        "raw_command": command,
                        "task_json": task_json,
                    }
                )

                await hub.broadcast_frontend(
                    {
                        "type": "dispatch_status",
                        "task_id": task_id,
                        "status": "DISPATCHED",
                        "robot_client_count": len(hub.robot_clients),
                    }
                )

            except Exception as e:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"指令处理失败: {str(e)}",
                    }
                )

    except WebSocketDisconnect:
        hub.disconnect_frontend(websocket)


@app.websocket("/ws/robot")
async def ws_robot(websocket: WebSocket):
    await hub.connect_robot(websocket)
    await websocket.send_json({"type": "connected", "role": "robot"})
    await hub.broadcast_frontend(
        {
            "type": "robot_status",
            "status": "ONLINE",
            "robot_client_count": len(hub.robot_clients),
        }
    )

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                robot_msg = json.loads(raw_message)
                task_id = int(robot_msg["task_id"])
                status = str(robot_msg.get("status", "RUNNING"))
                step_id = robot_msg.get("step_id")

                update_task_status(task_id, status)

                await hub.broadcast_frontend(
                    {
                        "type": "robot_step_status",
                        "task_id": task_id,
                        "step_id": step_id,
                        "status": status,
                        "detail": robot_msg.get("detail", ""),
                    }
                )

                await websocket.send_json(
                    {
                        "type": "ack",
                        "task_id": task_id,
                        "status": status,
                    }
                )
            except Exception as e:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"机器人状态消息处理失败: {str(e)}",
                    }
                )

    except WebSocketDisconnect:
        hub.disconnect_robot(websocket)
        await hub.broadcast_frontend(
            {
                "type": "robot_status",
                "status": "OFFLINE",
                "robot_client_count": len(hub.robot_clients),
            }
        )

# 启动 FastAPI 应用
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
