# Robot_Project 🤖

一个基于**大语言模型 + 行为树**的人形机器人控制框架。

用自然语言下达指令 → Python 大脑解析意图 → C++ 小脑执行动作。

---

## 项目架构

```
用户自然语言指令
       │
       ▼
┌──────────────────┐
│  brain (Python)  │  ← 调用 LLM API 解析意图，生成 task_bridge.json
└────────┬─────────┘
         │ task_bridge.json（中转文件）
         ▼
┌──────────────────────┐
│  cerebellum (C++)    │  ← BehaviorTree.CPP 轮询并执行行为树动作
└──────────────────────┘
```

| 模块 | 语言 | 说明 |
|------|------|------|
| `brain/` | Python | 调用通义千问/GPT，将自然语言解析为结构化指令 |
| `cerebellum/` | C++ | 基于 BehaviorTree.CPP v4，轮询中转文件并执行动作 |

---

## 环境依赖

### Python（brain）

- Python 3.8+

```bash
pip install -r brain/requirements.txt
```

### C++（cerebellum）

- CMake 3.10+
- BehaviorTree.CPP v4：`brew install behaviortree.cpp`
- nlohmann/json：`brew install nlohmann-json`

---

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
export DASHSCOPE_API_KEY=你的通义千问密钥
```

### 2. 编译 C++ 控制器

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

## 工作原理

1. `brain_node.py` 调用 LLM，从自然语言中提取 `location` 和 `item`，写入项目根目录的 `task_bridge.json`
2. `robot_brain` 每 500ms 扫描一次，发现文件后立即读取并执行行为树
3. 执行完成后删除 `task_bridge.json`，回到待命状态

---

## 目录结构

```
Robot_Project/
├── brain/
│   ├── brain_node.py       # Python NLP 大脑
│   └── requirements.txt
├── cerebellum/
│   ├── main.cpp            # C++ 行为树控制器
│   ├── CMakeLists.txt
│   └── build/              # 编译输出（不纳入 git）
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
