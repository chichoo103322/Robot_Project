import os
import json
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from brain.brain_node import nlp_processor

# 实例化 FastAPI 应用
app = FastAPI(title="机器人控制中心", description="基于大模型和行为树的智能机器人控制系统")

# Pydantic 模型：接收前端传来的指令
class CommandRequest(BaseModel):
    text: str

# GET 接口：返回前端页面
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    """读取并返回 index.html 页面"""
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

# POST 接口：处理自然语言指令
@app.post("/api/execute")
async def execute_command(request: CommandRequest):
    """
    接收用户自然语言指令并处理
    1. 调用 NLP 模块解析指令
    2. 写入 task_bridge.json
    3. 返回解析结果
    """
    try:
        # 调用 NLP 处理器
        result = nlp_processor(request.text)
        
        # 将结果写入 task_bridge.json
        project_root = os.path.dirname(os.path.abspath(__file__))
        bridge_path = os.path.join(project_root, "task_bridge.json")
        with open(bridge_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 返回解析结果给前端
        return {
            "success": True,
            "message": "任务已成功下发给 C++ 控制器",
            "data": result,
            "bridge_file": bridge_path
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"处理失败：{str(e)}",
            "data": None
        }

# 启动 FastAPI 应用
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
