"""
=============================================================================
server.py — 机器人控制中心后端
=============================================================================

【整体架构】
  前端(browser)  ←─────────────────────────────────────────────────────────→  本文件
  C++ 小脑        ←─────────────────────────────────────────────────────────→  本文件
  SQLite (tasks.db)                                                             本文件

【WebSocket 端点说明】
  /ws/frontend   — 网页浏览器连接，用于下发自然语言指令、接收执行状态
  /ws/robot      — C++ 小脑连接，用于接收任务包、上报执行进度

【HTTP 端点说明】
  GET  /          — 返回 index.html 控制页面
  POST /api/execute — 兼容性 HTTP 接口（等价于 /ws/frontend，供无 WS 场景使用）

=============================================================================
   ╔══════════════════  WebSocket 消息协议  ══════════════════════╗
   ║                                                                ║
   ║  ┌─────────────────────── /ws/frontend ──────────────────────┐║
   ║  │ 方向             JSON 字段                                  ││
   ║  │ Server → 前端   {"type":"connected","role":"frontend"}      ││ 连接握手
   ║  │ 前端   → Server 纯文本: "指令" 或 {"text":"指令"}           ││ 发送指令
   ║  │ Server → 前端   {"type":"frontend_status",                  ││
   ║  │                  "status":"PROCESSING","raw_command":"..."}  ││ 解析中通知
   ║  │ Server → 前端   {"type":"task_created","task_id":N,         ││
   ║  │                  "status":"PENDING","task_json":{...}}       ││ 入队成功
   ║  │ Server → 前端   {"type":"dispatch_status","task_id":N,      ││
   ║  │                  "status":"DISPATCHED",                      ││
   ║  │                  "robot_client_count":N}                     ││ 已派发给机器人
   ║  │ Server → 前端   {"type":"robot_step_status","task_id":N,    ││ 机器人步骤进度
   ║  │                  "step_id":N,"status":"RUNNING|SUCCESS|      ││
   ║  │                  FAILURE","detail":"..."}                    ││
   ║  │ Server → 前端   {"type":"robot_status",                      ││
   ║  │                  "status":"ONLINE|OFFLINE",                  ││ 机器人连接变化
   ║  │                  "robot_client_count":N}                     ││
   ║  │ Server → 前端   {"type":"error","message":"..."}             ││ 异常通知
   ║  └────────────────────────────────────────────────────────────┘║
   ║                                                                ║
   ║  ┌─────────────────────── /ws/robot ─────────────────────────┐║
   ║  │ 方向             JSON 字段                                  ││
   ║  │ Server → C++    {"type":"connected","role":"robot"}         ││ 连接握手
   ║  │ Server → C++    {"type":"task_dispatch","task_id":N,        ││
   ║  │                  "raw_command":"...","task_json":{...}}      ││ 下发任务
   ║  │ C++    → Server {"task_id":N,"step_id":N,"device":"...",    ││
   ║  │                  "status":"RUNNING|SUCCESS|FAILURE",         ││ 步骤状态上报
   ║  │                  "detail":"..."}                             ││
   ║  │ C++    → Server {"task_id":N,"status":"SUCCESS",            ││
   ║  │                  "step_id":-1,"detail":"all steps completed"}││ 任务完成
   ║  │ Server → C++    {"type":"ack","task_id":N,"status":"..."}   ││ 确认收到
   ║  │ Server → C++    {"type":"error","message":"..."}             ││ 异常通知
   ║  └────────────────────────────────────────────────────────────┘║
   ╚════════════════════════════════════════════════════════════════╝

【SQLite 数据库 tasks.db】
  表 task_queue:
    id          INTEGER  主键，自增，对应所有消息的 task_id
    raw_command TEXT     原始自然语言指令
    task_json   TEXT     LLM 解析后的结构化 JSON（字符串形式）
    status      TEXT     PENDING → RUNNING → SUCCESS / FAILURE
    created_at  DATETIME 入队时间

【完整数据流】
  1. 前端通过 /ws/frontend 发送自然语言指令
  2. server.py 调用 brain_node.nlp_processor() 解析为 task_json
  3. task_json 写入 SQLite task_queue，返回 task_id
  4. 通过 /ws/robot 将 task_dispatch 消息广播给所有 C++ 小脑
  5. C++ 小脑执行行为树，每步通过 /ws/robot 上报状态
  6. server.py 收到状态后更新 SQLite 并广播给所有前端
=============================================================================
"""

import os
import json
import asyncio
import sqlite3
import datetime
from typing import Any, Dict, Set
import uvicorn
import websockets
from dotenv import load_dotenv

load_dotenv()  # 从项目根目录的 .env 文件加载环境变量
from websockets.exceptions import WebSocketException
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from brain.brain_node import nlp_processor

# 实例化 FastAPI 应用
app = FastAPI(title="机器人控制中心", description="基于大模型和行为树的智能机器人控制系统")

# ─────────────────────────────────────────────────────────────────────────────
# 外部后端上报（ExternalReporter）
# ─────────────────────────────────────────────────────────────────────────────
# 在 .env 中配置：
#   EXTERNAL_WS_URL=ws://your-backend-host:port/robot-events
# 未配置时所有上报静默跳过，不影响本地功能。
#
# ── 上报消息格式（本端 → 外部后端）────────────────────────────────────────
#
#  事件 robot_status（机器人上线/下线）:
#    {"event":"robot_status", "status":"ONLINE|OFFLINE",
#     "timestamp":"2026-04-27T12:00:00Z"}
#
#  事件 command_received（收到用户指令）:
#    {"event":"command_received", "raw_command":"去厨房拿水杯",
#     "timestamp":"..."}
#
#  事件 task_created（LLM 解析完成并入库）:
#    {"event":"task_created", "task_id":42,
#     "raw_command":"...", "task_json":{...},
#     "timestamp":"..."}
#
#  事件 step_status（机器人每步执行状态）:
#    {"event":"step_status", "task_id":42, "step_id":1,
#     "device":"底盘", "status":"RUNNING|SUCCESS|FAILURE",
#     "detail":"...", "timestamp":"..."}
#
#  事件 task_completed（整体任务完成）:
#    {"event":"task_completed", "task_id":42,
#     "status":"SUCCESS|FAILURE", "timestamp":"..."}
#
# ── 外部后端需实现的 WebSocket 服务端 ──────────────────────────────────────
#  外部后端只需监听并接收本端推送的 JSON 文本帧，无需主动发送任何消息。
#  本端不依赖任何回包（单向推送），连接断开后会自动重连（指数退避，最长 60s）。
# ─────────────────────────────────────────────────────────────────────────────

# 外部后端 WebSocket 地址（从环境变量读取）
EXTERNAL_WS_URL: str = os.getenv("EXTERNAL_WS_URL", "")


class ExternalReporter:
    """向外部后端单向推送机器人事件的 WebSocket 客户端。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running: bool = False

    @staticmethod
    def _now() -> str:
        return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def report(self, event: str, payload: Dict[str, Any]) -> None:
        """非阻塞上报：把事件放入队列由后台发送，调用方不需要 await。"""
        if not EXTERNAL_WS_URL:
            return
        data = dict(payload)
        data["event"] = event
        data["timestamp"] = self._now()
        self._queue.put_nowait(json.dumps(data, ensure_ascii=False))

    async def _send_loop(self) -> None:
        """后台循环：维护到外部后端的 WebSocket 连接，断线自动重连（指数退避）。"""
        retry_delay = 2
        while self._running:
            try:
                async with websockets.connect(EXTERNAL_WS_URL) as ws:
                    retry_delay = 2  # 连接成功后重置退避计时
                    print(f"[外部上报] 已连接外部后端: {EXTERNAL_WS_URL}")
                    while self._running:
                        msg = await self._queue.get()
                        await ws.send(msg)
            except (WebSocketException, OSError, Exception) as exc:
                print(f"[外部上报] 连接失败: {exc}，{retry_delay}s 后重试")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def start(self) -> None:
        if not EXTERNAL_WS_URL:
            print("[外部上报] EXTERNAL_WS_URL 未配置，上报功能已禁用")
            return
        self._running = True
        asyncio.create_task(self._send_loop())


ext_reporter = ExternalReporter()


class ExecuteRequest(BaseModel):
    text: str

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
    ext_reporter.start()  # 启动外部后端上报客户端

# GET 接口：返回前端页面
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    """读取并返回 index.html 页面"""
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.websocket("/ws/frontend")
async def ws_frontend(websocket: WebSocket):
    """
    前端 WebSocket 通道。

    接收：
      - 纯文本指令，如 "去厨房拿水杯"
      - 或 JSON：{"text": "去厨房拿水杯"}

    推送（广播给所有前端）：
      - {"type": "frontend_status", "status": "PROCESSING", "raw_command": "..."}
          → 告知前端指令已收到，正在 LLM 解析
      - {"type": "task_created", "task_id": N, "status": "PENDING", "task_json": {...}}
          → 解析完成，task_id 为 SQLite 主键，可用于后续状态追踪
      - {"type": "dispatch_status", "task_id": N, "status": "DISPATCHED", "robot_client_count": N}
          → 任务已广播给 C++ 小脑，robot_client_count 为当前在线机器人数
      - {"type": "robot_step_status", ...}  — 机器人执行进度（见 /ws/robot）
      - {"type": "robot_status", ...}       — 机器人上下线通知
      - {"type": "error", "message": "..."}  — 处理失败原因
    """
    await hub.connect_frontend(websocket)
    # 握手确认：告知客户端角色身份
    await websocket.send_json({"type": "connected", "role": "frontend"})

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                # 兼容纯文本和 {"text":"..."} 两种格式
                command = parse_frontend_command(raw_message)

                # 通知所有前端：指令正在解析
                await hub.broadcast_frontend(
                    {
                        "type": "frontend_status",
                        "status": "PROCESSING",
                        "raw_command": command,
                    }
                )

                # nlp_processor 为同步调用，放到线程池以避免阻塞事件循环
                task_json = await asyncio.to_thread(nlp_processor, command)
                # 写入 SQLite，返回的 task_id 贯穿后续所有消息
                task_id = insert_task(command, task_json)

                # ── 上报给外部后端 ──
                ext_reporter.report("command_received", {"raw_command": command})
                ext_reporter.report("task_created", {
                    "task_id": task_id,
                    "raw_command": command,
                    "task_json": task_json,
                })

                # 通知前端：任务已入队（status=PENDING）
                await hub.broadcast_frontend(
                    {
                        "type": "task_created",
                        "task_id": task_id,
                        "status": "PENDING",
                        "task_json": task_json,
                    }
                )

                # 通过 /ws/robot 将任务派发给所有 C++ 小脑
                # C++ 端收到 type=="task_dispatch" 后开始执行行为树
                await hub.broadcast_robot(
                    {
                        "type": "task_dispatch",
                        "task_id": task_id,
                        "raw_command": command,
                        "task_json": task_json,
                    }
                )

                # 通知前端：派发完成，告知当前在线机器人数量
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
    """
    C++ 小脑 WebSocket 通道。

    服务端 → C++（下发）：
      - {"type": "connected", "role": "robot"}
          → 握手确认
      - {"type": "task_dispatch", "task_id": N, "raw_command": "...", "task_json": {...}}
          → 任务下发包；C++ 端判断 type=="task_dispatch" 后开始构造并执行行为树
          → task_json 结构：
              {
                "target_object": "杯子",
                "task_list": [
                  {"id":1, "device":"视觉|底盘|机械臂|机械爪",
                   "action":"...", "target":"...",
                   "condition":"...", "fail_handler":"..."}
                ]
              }
      - {"type": "ack", "task_id": N, "status": "..."}
          → 收到 C++ 状态上报后的确认回执
      - {"type": "error", "message": "..."}
          → 消息处理失败通知

    C++ → 服务端（上报）：
      - 步骤状态：{"task_id":N, "step_id":N, "device":"...",
                   "status":"RUNNING|SUCCESS|FAILURE", "detail":"..."}
      - 任务完成：{"task_id":N, "status":"SUCCESS",
                   "step_id":-1, "detail":"all steps completed"}

    状态变化会实时更新 SQLite task_queue.status 并广播给所有前端。
    """
    await hub.connect_robot(websocket)
    # 握手确认：告知 C++ 端已连接成功
    await websocket.send_json({"type": "connected", "role": "robot"})
    # 通知所有前端：有新机器人上线
    await hub.broadcast_frontend(
        {
            "type": "robot_status",
            "status": "ONLINE",
            "robot_client_count": len(hub.robot_clients),
        }
    )
    # ── 上报给外部后端 ──
    ext_reporter.report("robot_status", {"status": "ONLINE"})

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                robot_msg = json.loads(raw_message)
                task_id = int(robot_msg["task_id"])
                status = str(robot_msg.get("status", "RUNNING"))
                step_id = robot_msg.get("step_id")  # -1 表示整体任务完成

                # 同步更新 SQLite 记录的执行状态
                update_task_status(task_id, status)

                # 将机器人执行进度广播给所有前端（实时显示）
                await hub.broadcast_frontend(
                    {
                        "type": "robot_step_status",
                        "task_id": task_id,
                        "step_id": step_id,
                        "status": status,
                        "detail": robot_msg.get("detail", ""),
                    }
                )

                # ── 上报给外部后端 ──
                ext_reporter.report("step_status", {
                    "task_id": task_id,
                    "step_id": step_id,
                    "device": robot_msg.get("device", ""),
                    "status": status,
                    "detail": robot_msg.get("detail", ""),
                })
                # step_id == -1 代表整体任务完成
                if step_id == -1 or step_id is None and status in ("SUCCESS", "FAILURE"):
                    ext_reporter.report("task_completed", {
                        "task_id": task_id,
                        "status": status,
                    })

                # 回执 ack，让 C++ 端知道状态已被服务端处理
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
        # 通知所有前端：机器人已断开
        await hub.broadcast_frontend(
            {
                "type": "robot_status",
                "status": "OFFLINE",
                "robot_client_count": len(hub.robot_clients),
            }
        )
        # ── 上报给外部后端 ──
        ext_reporter.report("robot_status", {"status": "OFFLINE"})


@app.post("/api/execute")
async def api_execute(req: ExecuteRequest):
    """HTTP 接口：接收前端指令，调用大脑解析后写入队列并下发给机器人。"""
    command = req.text.strip()
    if not command:
        return {"success": False, "message": "指令为空"}

    try:
        task_json = await asyncio.to_thread(nlp_processor, command)
        task_id = insert_task(command, task_json)

        await hub.broadcast_robot(
            {
                "type": "task_dispatch",
                "task_id": task_id,
                "raw_command": command,
                "task_json": task_json,
            }
        )

        return {
            "success": True,
            "message": f"任务已解析并下发 (ID: {task_id})",
            "data": task_json,
        }
    except Exception as e:
        return {"success": False, "message": f"处理失败: {str(e)}"}


# 启动 FastAPI 应用
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
