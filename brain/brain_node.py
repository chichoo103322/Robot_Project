import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# 1. 配置你的大模型 API
# 加载 .env 文件中的环境变量
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

api_key = os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    raise EnvironmentError("请先设置环境变量 DASHSCOPE_API_KEY，参考 .env.example 文件")

client = OpenAI(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

def nlp_processor(user_text):
    """
    将自然语言转化为机器人可理解的指令格式
    """
    prompt = f"""
    你是一个人形机器人的高级指令解析器。
    任务：从用户的自然语言中提取 '地点(location)' 和 '物体(item)'。
    规则：
    1. 只返回 JSON 格式。
    2. 如果用户没提到物体，item 设为 "null"。
    3. 可选地点：[厨房, 客厅, 卧室, 阳台]。
    
    用户指令："{user_text}"
    输出格式示例：{{"location": "厨房", "item": "杯子"}}
    """

    try:
        response = client.chat.completions.create(
            model="qwen-plus", # 或者 gpt-4o
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1 # 调低随机性，保证输出稳定
        )
        
        # 提取并解析 JSON
        raw_content = response.choices[0].message.content
        # 简单清理可能存在的 Markdown 标签
        clean_json = raw_content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
        
    except Exception as e:
        print(f"解析失败: {e}")
        return {"location": "未知", "item": "未知"}

if __name__ == "__main__":
    # 测试一下
    test_command = "去房间帮我把被子拿过来"
    result = nlp_processor(test_command)
    print(f"--- 大脑解析结果 ---")
    print(f"目标地点: {result['location']}")
    print(f"目标物体: {result['item']}")
    
    # 这一步是为后面打通 C++ 做准备
    # 使用脚本所在目录的上一级（项目根目录）作为中转文件路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bridge_path = os.path.join(project_root, "task_bridge.json")
    with open(bridge_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
        print(f"\n已将指令写入中转站: {bridge_path}")