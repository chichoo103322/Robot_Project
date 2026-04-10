# Robot_Project 🤖

一个基于**大语言模型 + 行为树 + 前后端分离 Web 架构**的人形机器人控制框架。

用自然语言下达指令 → Python 大脑解析意图 → C++ 小脑执行动作，并通过现代化 Web 界面进行交互。

---

## ✨ 核心特性

- 🧠 **自然语言处理**：集成阿里通义千问或 OpenAI API，实时理解用户指令
- 🌳 **行为树架构**：基于 BehaviorTree.CPP v4，灵活可扩展的行为控制系统
- 🌐 **Web 可视化交互**：FastAPI 后端 + 原生 HTML/JS/CSS 前端，为未来扩展预留
- 🎨 **多种部署方式**：支持 FastAPI 服务、Streamlit 快速开发、终端命令三种方式
- 📱 **响应式设计**：前端支持桌面和移动设备

---

## 项目架构

### 系统流程图

```
┌─────────────────────────────────────────────────────┐
│         🖥️ Web 前端 (HTML/JS/CSS)                   │
│       - 现代化控制中心界面                             │
│       - 自然语言输入框                               │
│       - 实时结果展示                                 │
│       - 为行为树可视化预留                           │
└──────────────┬──────────────────────────────────────┘
               │ HTTP POST /api/execute
   📦 环境依赖

### Python（大脑 + Web 服务）

- Python 3.8+
- FastAPI、Uvicorn、Pydantic（后端服务）
- OpenAI SDK（LLM 调用）
- python-dotenv（环境变量管理）

### C++（小脑）

- CMake 3.10+
- BehaviorTree.CPP v4：`brew install behaviortree.cpp`
- nlohmann/json：`brew install nlohmann-json`
- macOS / Linux（已验证）

---

## 🚀 快速开始

### 步骤 1：克隆和初始化

```bash
git clone <your-repo-url>
cd Robot_Project

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# 或 .venv\Scripts\activate  # Windows
```

### 步骤 2：配置 API Key

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key
export DASHSCOPE_API_KEY=your_api_key_here
```

### 步骤 3：安装 Python 依赖

```bash
pip install -r brain/requirements.txt
```

### 步骤 4：编译 C++ 控制器（可选）

```bash
cd cerebellum
mkdir -p build && cd build
cmake ..
cmake --build . -j
cd /path/to/Robot_Project
```

---

## 💻 三种使用方式

### 🌐 方式 1：Web UI（推荐 - FastAPI）

**启动后端服务：**
```bash
cd /path/to/Robot_Project
.venv/bin/python server.py
```

**输出：**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**在浏览器打开：**
```
http://localhost:8000
```

**特点：**
- ✅ 现代化 Web 界面
- ✅ 前后端分离架构
- ✅ 为未来的行为树可视化预留空间
- ✅ 支持 2D 地图交互扩展

---

### 📊 方式 2：Streamlit（快速开发）

**启动 Streamlit 应用：**
```bash
.venv/bin/streamlit run web_ui.py
```

**在浏览器打开：**
```
http://localhost:8501
```

**特点：**
- ✅ 开发速度快
- ✅ 无需编写前端代码
- ✅ 适合数据展示和快速原型

---

### 🖥️ 方式 3：命令行（开发调试）

**Python 终端启动：**
```bash
.venv/bin/python brain/brain_node.py
```

**输出：**
```
--- 大脑解析结果 ---
目标地点: 客厅
目标物体: 书

已将指令写入中转站: /path/to/Robot_Project/task_bridge.json
```

**C++ 控制器执行：**
```bash
./cerebellum/build/robot_brain
```

输出：
```
>>> 机器人控制器已启动，等待指令... (按 Ctrl+C 退出)
[检测到新任务！]
[动作] 🤖 正在前往: 客厅
[动作] 🦾 正在抓取: 书
>>> 任务完成，继续等待...
```

**特点：**
- ✅ 零开销，直接调用
- ✅ 易于调试
- ✅ 适合集成测试 2. 编译 C++ 控制器

```bash
cd cerebellum/build
cmake ..
cmake --build . -j
```

### 3. 启动 C++ 控制器（在项目根目录运行）

```bash
cd /path/to/Robot_Project
./cerebellum/build/robot_brain
```

输出：
```
>>> 机器人控制器已启动，等待指令... (按 Ctrl+C 退出)
```

### 4. 下达自然语言指令

新开终端，在项目根目录运行：

```bash
python3 brain/brain_node.py
```

C++ 控制器自动执行并输出：
```
[检测到新任务！]
[动作] 🤖 正在前往: 客厅
[动作] 🦾 正在抓取: 书
>>> 任务完成，继续等待...
```

---

## 🔧 工作原理

### 数据流程

1. **用户输入**：在 Web 界面输入自然语言指令（如"去客厅拿本书"）
2. **前端请求**：JavaScript 发送 POST 请求到 `/api/execute`
3. **后端处理**：FastAPI 接收请求，调用 `nlp_processor()`
4. **LLM 解析**：通义千问或 GPT 解析自然语言，提取 `location` 和 `item`
5. 📁 目录结构

```
Robot_Project/
├── 🌐 前端和后端
│   ├── index.html              # Web 前端（HTML/JS/CSS）
│   ├── server.py               # FastAPI 后端服务
│   └── web_ui.py               # Streamlit 快速开发版本
│
├── 🧠 Python 大脑
│   ├── brain/
│   │   ├── brain_node.py       # NLP 大脑核心模块
│   │   └── requirements.txt    # Python 依赖列表
│   └── task_bridge.json        # 中转文件（运行时生成，不纳入 git）
│
├── 🤖 C++ 小脑
│   ├── cerebellum/
│   │   ├── main.cpp            # C++ 行为树控制器
│   │   ├── CMakeLists.txt      # CMake 配置
│   │   └── build/              # 编译输出目录（不纳入 git）
│   │       ├── robot_brain     # 编译生成的可执行文件
│   │       ├── Makefile        # 编译脚本
│   │       └── ...
│   └── nodes                   # 行为树节点定义（预留）
│
├── 🔐 配置文件
│   ├── .env                    # API Key 配置（本地，不纳入 git）
│   ├── .env.example            # API Key 模板
│   ├── .gitignore              # Git 忽略规则
│   └── .vscode/                # VS Code 配置
│
├── 📚 文档
│   ├── README.md               # 本文件
│   └── task_bridge.json        # 中转 JSON 样例
│
└── 🔧 虚拟环境
    └── .venv/                  # Python 虚拟环境（不纳入 git）
```

---

## ⚙️ 配置说明

### `.env` 文件

```bash
# 复制 .env.example 为 .env，然后填入你的 API Key
DASHSCOPE_API_KEY=sk-your-api-key-here
```

### 支持的 LLM 模型

当前默认使用阿里通义千问（qwen-plus），也可改为 OpenAI 的 gpt-4o：

```python
# 在 brain/brain_node.py 中修改
response = client.chat.completions.create(
    model="gpt-4o",  # 改为 gpt-4o 使用 OpenAI
    messages=[...],
)
```

---

## 📊 API 接口说明

### POST /api/execute

**请求：**
```json
{
  "text": "去客厅拿本书"
}
```

**成功响应：**
```json
{
  "success": true,
  "message": "任务已成功下发给 C++ 控制器",
  "data": {
    "location": "客厅",
    "item": "书"
  },
  "bridge_file": "/path/to/Robot_Project/task_bridge.json"
}
```

**失败响应：**
```json
{
  "success": false,
  "message": "处理失败：错误信息",
  "data": null
}
```

---

## 🐛 常见问题

### Q1：API Key 如何获取？

**通义千问：** 访问 https://dashscope.aliyun.com/，注册并创建 API Key

**OpenAI：** 访问 https://platform.openai.com/api-keys

### Q2：如何在两个 LLM 之间切换？

编辑 `brain/brain_node.py`：
```python
# 方式 1：使用通义千问（默认）
base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
model="qwen-plus"

# 方式 2：使用 OpenAI
base_url="https://api.openai.com/v1"
model="gpt-4o"
```

### Q3：为什么 C++ 控制器检测不到任务？

- 确保 `robot_brain` 从项目根目录启动
- 检查 `.env` 文件是否正确配置
- 运行 `python brain/brain_node.py` 验证 Python 端是否正常生成 `task_bridge.json`
- 查看是否有权限问题（用 `ls -la` 检查文件权限）

### Q4：如何在本地调试行为树？

编辑 `cerebellum/main.cpp`，修改行为树结构，然后重新编译：
```bash
cd cerebellum/build
cmake --build . -j
```

---

## 🚀 扩展计划

- [ ] 🗺️ **2D 走廊地图**：Web 前端集成动态地图，实时高亮机器人位置
- [ ] 🎯 **行为树可视化**：前端实时展示正在执行的行为树节点
- [ ] 💾 **任务队列**：支持多个指令排队执行
- [ ] 📡 **WebSocket 推送**：实时推送 C++ 执行状态到前端
- [ ] 🎙️ **语音输入**：集成语音识别模块
- [ ] 🔄 **状态同步**：前端显示机器人实时运动状态

---

## 📝 注意事项

⚠️ **安全性：**
- `.env` 包含 API Key，**绝不要提交到 git**
- 已在 `.gitignore` 中排除，但请再次确认

⚠️ **文件权限：**
- `robot_brain` 必须从**项目根目录**启动
- C++ 控制器需要写权限来操作 `task_bridge.json`

⚠️ **依赖版本：**
- Python 3.8+ 推荐
- BehaviorTree.CPP v4.x（vs 3.x 有 API 差异）
- CMake 3.10+

---

## 🤝 贡献指南

欢迎 Pull Request！请确保：
1. 代码符合项目风格
2. 更新相关文档
3. 本地测试通过

---

## 📄 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

---

## 👉 联系方式

如有问题，欢迎提交 Issue 或 Discussion！

**Happy Coding! 🎉**
├── .vscode/                # VS Code 配置
├── .env.example            # 环境变量模板
├── .gitignore
└── README.md
```

---

## 注意事项

- `.env` 含密钥，已被 `.gitignore` 排除，**请勿提交到 git**
- `robot_brain` 必须从**项目根目录**启动，才能正确读写 `task_bridge.json`
- `task_bridge.json` 为运行时临时文件，已被 `.gitignore` 排除
