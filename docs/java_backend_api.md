# 机器人控制中心 → Java 后端 接口文档

机器人控制中心（`server.py`，默认运行在 `http://localhost:8090`）通过两种方式向 Java 后端推送数据：

| 方式 | 地址 | 说明 |
|------|------|------|
| **WebSocket 长连接** | `ws://robot-host:8090/ws/llm` | Java 主动连接，双向通信 |
| **HTTP POST 回调** | 由 Java 侧提供 URL，写在机器人 `.env` 中 | 任务完成/失败时单次触发 |

---

## 一、WebSocket 接口 `/ws/llm`

### 连接方式

Java 后端作为 **WebSocket 客户端**主动连接：

```
ws://robot-host:8090/ws/llm
```

连接成功后，服务端会立即发送握手消息：

```json
{"type": "connected", "role": "llm_service"}
```

---

### 1.1 Java → 机器人端（主动请求 LLM 解析）

Java 发送自然语言指令，请求解析为步骤列表：

```json
{
  "action": "parse_natural_language",
  "instruction": "去客厅拿个杯子"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | string | 固定为 `"parse_natural_language"` |
| `instruction` | string | 用户下达的自然语言指令 |

---

### 1.2 机器人端 → Java（LLM 解析结果回复）

**成功时：**

```json
{
  "success": true,
  "action": "parse_result",
  "command": "去客厅拿个杯子",
  "steps": [
    {"id": 1, "action": "导航到客厅"},
    {"id": 2, "action": "识别杯子位置"},
    {"id": 3, "action": "移动到杯子旁边"},
    {"id": 4, "action": "伸出机械臂抓取杯子"},
    {"id": 5, "action": "返回原位"}
  ]
}
```

**失败时：**

```json
{
  "success": false,
  "error": "instruction 字段为空"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否解析成功 |
| `action` | string | 固定为 `"parse_result"` |
| `command` | string | 原始指令原文 |
| `steps` | array | 有序步骤列表，见下表 |
| `error` | string | 失败时的错误描述 |

**steps 数组元素：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | integer | 步骤编号，从 1 开始递增 |
| `action` | string | 该步骤的具体动作描述 |

---

### 1.3 机器人端 → Java（任务计划主动推送）

用户通过前端页面下达指令后，任务规划完成时，服务端会**主动推送**给所有已连接的 Java 后端：

```json
{
  "event": "task_planned",
  "task_id": 42,
  "command": "去客厅拿个杯子",
  "steps": [
    {"id": 1, "action": "导航到客厅"},
    {"id": 2, "action": "识别杯子位置"},
    {"id": 3, "action": "移动到杯子旁边"},
    {"id": 4, "action": "伸出机械臂抓取杯子"},
    {"id": 5, "action": "返回原位"}
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `event` | string | 固定为 `"task_planned"` |
| `task_id` | integer | 任务唯一 ID（SQLite 主键，全局自增） |
| `command` | string | 用户原始指令 |
| `steps` | array | 有序步骤列表（同上） |

> **注意**：此消息是服务端主动推送，Java 后端只需监听即可，无需发送任何回复。

---

### 1.4 机器人端 → Java（机器人逐步执行状态推送）

机器人每执行完一个步骤，服务端实时推送进度：

```json
{
  "action": "behavior_tree_status",
  "taskId": 42,
  "stepId": 2,
  "status": "已完成",
  "detail": "识别杯子位置 completed"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | string | 固定为 `"behavior_tree_status"` |
| `taskId` | integer | 任务 ID |
| `stepId` | integer | 当前步骤编号；`-1` 表示整体任务结束 |
| `status` | string | `"RUNNING"` / `"已完成"` / `"执行失败"` |
| `detail` | string | 执行细节或失败原因 |

**status 取值说明：**

| 值 | 含义 |
|----|------|
| `RUNNING` | 步骤正在执行中 |
| `已完成` | 步骤执行成功 |
| `执行失败` | 步骤执行失败 |

---

## 二、HTTP 回调接口

任务**整体完成**或发生**步骤失败**时，机器人端向 Java 后端发送 HTTP POST 回调。

### 配置方式

在机器人端 `.env` 文件中配置：

```env
JAVA_BACKEND_CALLBACK_URL=http://172.16.25.79:8080/api/v1/scheduler/robot/callback
ROBOT_ID=r001
```

### 请求格式

```
POST {JAVA_BACKEND_CALLBACK_URL}
Content-Type: application/json
```

**请求体：**

```json
{
  "robotId": "r001",
  "taskId": "42",
  "status": "已完成",
  "reason": "all steps completed"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `robotId` | string | 机器人唯一标识，来自 `.env` 中 `ROBOT_ID` |
| `taskId` | string | 任务 ID（字符串形式） |
| `status` | string | `"已完成"` 或 `"执行失败"` |
| `reason` | string | 完成/失败的详细描述 |

**触发时机：**

| 情况 | status 值 |
|------|-----------|
| 任务所有步骤全部执行成功 | `"已完成"` |
| 任意步骤执行失败 | `"执行失败"` |

> 机器人端对 HTTP 响应状态码不做强依赖，超时时间为 5 秒，失败时仅打印日志，不影响主流程。

---

## 三、完整交互时序

```
Java后端                    机器人控制中心(server.py)           机器人(C++小脑)
   │                                │                                │
   │── WS连接 /ws/llm ─────────────>│                                │
   │<─ {"type":"connected",...} ────│                                │
   │                                │                                │
   │  [方式A: Java主动下发指令]      │                                │
   │── parse_natural_language ──────>│                                │
   │<─ parse_result (steps列表) ────│                                │
   │                                │                                │
   │  [方式B: 前端用户下达指令]      │                                │
   │                         用户输入"去客厅拿杯子"                    │
   │<─ task_planned (steps列表) ────│                                │
   │                                │── task_dispatch ──────────────>│
   │                                │                         开始执行步骤1
   │<─ behavior_tree_status (step1 RUNNING) ─────────────────────────│
   │<─ behavior_tree_status (step1 已完成) ──────────────────────────│
   │<─ behavior_tree_status (step2 RUNNING) ─────────────────────────│
   │       ...                      │                    逐步执行...  │
   │<─ behavior_tree_status (stepN 已完成) ──────────────────────────│
   │                                │                                │
   │  HTTP POST 回调 ───────────────────────────────────────────────>Java HTTP接口
   │  {"status":"已完成",...}        │                                │
```

---

## 四、快速接入示例（Java 伪代码）

```java
// 1. 连接 WebSocket
WebSocketClient client = new WebSocketClient("ws://robot-host:8090/ws/llm");

// 2. 监听推送消息
client.onMessage(message -> {
    JSONObject json = JSON.parseObject(message);
    String event = json.getString("event");
    String action = json.getString("action");

    if ("task_planned".equals(event)) {
        // 收到任务步骤计划
        int taskId = json.getIntValue("task_id");
        String command = json.getString("command");
        JSONArray steps = json.getJSONArray("steps");
        // 处理步骤列表...

    } else if ("behavior_tree_status".equals(action)) {
        // 收到机器人执行进度
        int taskId = json.getIntValue("taskId");
        int stepId = json.getIntValue("stepId");
        String status = json.getString("status");
        String detail = json.getString("detail");
        // 更新任务状态...
    }
});

// 3. 主动请求 LLM 解析（可选）
JSONObject req = new JSONObject();
req.put("action", "parse_natural_language");
req.put("instruction", "去客厅拿个杯子");
client.send(req.toJSONString());

// 4. 处理 LLM 解析回复
client.onMessage(message -> {
    JSONObject json = JSON.parseObject(message);
    if (json.getBooleanValue("success") && "parse_result".equals(json.getString("action"))) {
        JSONArray steps = json.getJSONArray("steps");
        // steps: [{"id":1,"action":"导航到客厅"}, ...]
    }
});
```
