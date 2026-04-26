# Robot_Project

基于大模型任务分解 + BehaviorTree.CPP 执行的小型机器人控制项目。

当前版本采用前后端 WebSocket 协作：
- Python 端负责自然语言解析、任务入队、状态广播
- C++ 端负责接收任务并按行为树逐步执行

## 功能概览

- 自然语言指令解析（`brain/brain_node.py`，DashScope 兼容 OpenAI SDK）
- FastAPI 服务 + Web 前端页面（`server.py` + `index.html`）
- WebSocket 双通道：
  - `/ws/frontend`：网页客户端
  - `/ws/robot`：C++ 控制器
- SQLite 任务队列（自动创建 `tasks.db`）
- C++ 小脑动态构造并执行行为树（`cerebellum/main.cpp`）

## 目录结构

```text
Robot_Project/
├── server.py                 # FastAPI + WebSocket 后端
├── index.html                # 控制页面
├── web_ui.py                 # Streamlit 备用界面
├── task_bridge.json          # 调试中转文件（历史方案保留）
├── brain/
│   ├── brain_node.py         # LLM 指令解析
│   └── requirements.txt      # Python 依赖
└── cerebellum/
    ├── CMakeLists.txt
    └── main.cpp              # C++ 机器人执行端
```

## 环境要求

- Python 3.9+
- CMake 3.16+
- C++17 编译器（macOS 下可用 clang++）
- Homebrew 安装依赖：

```bash
brew install behaviortree.cpp nlohmann-json
```

## 快速开始

### 1. Python 环境与依赖

```bash
cd Robot_Project
python3 -m venv .venv
source .venv/bin/activate
pip install -r brain/requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填写 DASHSCOPE_API_KEY
```

`.env` 示例：

```env
DASHSCOPE_API_KEY=your_api_key_here
```

### 3. 编译 C++ 小脑

```bash
cd cerebellum
mkdir -p build
cd build
cmake ..
cmake --build . -j
```

如果你在 VS Code 中使用任务，可直接执行：`CMake: Build robot_brain`。

## 运行方式（推荐）

### 终端 1：启动后端

```bash
cd Robot_Project
source .venv/bin/activate
python server.py
```

服务默认监听：`http://127.0.0.1:8000`

### 终端 2：启动 C++ 控制器

```bash
cd Robot_Project
./cerebellum/build/robot_brain
```

### 浏览器：打开控制页面

访问：`http://127.0.0.1:8000`

输入自然语言指令后，流程如下：
1. 前端通过 `/ws/frontend` 提交指令
2. Python 调用 `nlp_processor` 生成结构化 `task_json`
3. 后端写入 SQLite `task_queue`，并通过 `/ws/robot` 派发
4. C++ 动态生成行为树并执行
5. 执行状态经 WebSocket 回传并实时展示

## 可选运行方式

### Streamlit（快速调试）

```bash
cd Robot_Project
source .venv/bin/activate
streamlit run web_ui.py
```

## 常见问题

### 1) 启动时报 `DASHSCOPE_API_KEY` 未设置

请检查：
- 是否已创建 `.env`
- `.env` 中变量名是否为 `DASHSCOPE_API_KEY`

### 2) C++ 端无法连接 WebSocket

请确认：
- `server.py` 已在 `127.0.0.1:8000` 运行
- 本机端口未被占用

### 3) 行为树执行失败

请优先查看：
- 后端日志（任务解析是否成功）
- C++ 控制台日志（节点执行失败位置）

## 开发说明

- `server.py` 中 `ConnectionHub` 管理前端与机器人客户端连接
- SQLite 文件默认为项目根目录 `tasks.db`
- C++ 端在 `main.cpp` 中将 `task_json.task_list` 转为 BT XML 并执行

后续可扩展方向：
- 任务持久化查询接口
- 行为树执行可视化
- 多机器人并发调度
