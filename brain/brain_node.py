import os
import json
from datetime import datetime
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

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
PARSE_LOG_PATH = os.path.join(ROOT_DIR, "parse_failures.log")


def _extract_first_json_object(text):
    """Extract the first balanced JSON object from a text blob."""
    if not text:
        return ""

    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return ""


def _classify_parse_error(exc):
    name = exc.__class__.__name__
    if name in {"APITimeoutError", "APIConnectionError", "TimeoutError", "ConnectionError"}:
        return "NETWORK"
    if name in {"RateLimitError"}:
        return "RATE_LIMIT"
    if name in {"APIStatusError", "AuthenticationError", "PermissionDeniedError", "BadRequestError"}:
        return "API_STATUS"
    if isinstance(exc, json.JSONDecodeError):
        return "JSON_FORMAT"
    return "UNKNOWN"


def _log_parse_failure(user_text, err_type, err_msg, raw_content):
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "error_type": err_type,
        "error": err_msg,
        "input": user_text,
        "raw_preview": (raw_content or "")[:1000],
    }
    with open(PARSE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

def nlp_processor(user_text):
    """
    将自然语言拆分为有序执行步骤列表。

    输出格式：
    {
        "command": "原始指令",
        "steps": [
            {"id": 1, "action": "步骤描述"},
            {"id": 2, "action": "步骤描述"},
            ...
        ]
    }
    """
    prompt = f"""
你是机器人任务规划器。请将用户指令拆分为机器人可按顺序执行的步骤列表。

【输出要求】
1. 只输出 JSON，不要输出任何解释、注释、Markdown 代码块。
2. 严格使用以下格式：
{{
    "command": "用户原始指令",
    "steps": [
        {{"id": 1, "action": "步骤描述"}},
        {{"id": 2, "action": "步骤描述"}}
    ]
}}
3. steps 的 id 从 1 开始递增，每个步骤只填 action 字段（简洁描述动作）。
4. 步骤要具体可执行，不要笼统。

【示例】
输入："去客厅拿个杯子"
输出：
{{
    "command": "去客厅拿个杯子",
    "steps": [
        {{"id": 1, "action": "导航到客厅"}},
        {{"id": 2, "action": "识别杯子位置"}},
        {{"id": 3, "action": "移动到杯子旁边"}},
        {{"id": 4, "action": "伸出机械臂抓取杯子"}},
        {{"id": 5, "action": "返回原位"}}
    ]
}}

输入："去厨房拿瓶水放到桌上"
输出：
{{
    "command": "去厨房拿瓶水放到桌上",
    "steps": [
        {{"id": 1, "action": "导航到厨房"}},
        {{"id": 2, "action": "识别水瓶位置"}},
        {{"id": 3, "action": "移动到水瓶旁边"}},
        {{"id": 4, "action": "抓取水瓶"}},
        {{"id": 5, "action": "导航到桌子旁边"}},
        {{"id": 6, "action": "将水瓶放到桌上"}}
    ]
}}

现在拆分这条指令："{user_text}"
    """

    raw_content = ""
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1  # 调低随机性，保证 JSON 结构稳定
        )
        
        # 提取并解析 JSON
        raw_content = response.choices[0].message.content or ""
        if not isinstance(raw_content, str):
            raw_content = str(raw_content)

        # 先做基础清理，再尝试提取首个平衡 JSON 对象，减少模型多余文本导致的失败
        clean_text = raw_content.replace("```json", "").replace("```", "").strip()
        json_candidate = _extract_first_json_object(clean_text) or clean_text
        return json.loads(json_candidate)
        
    except Exception as e:
        err_type = _classify_parse_error(e)
        _log_parse_failure(user_text=user_text, err_type=err_type, err_msg=str(e), raw_content=raw_content)
        print(f"解析失败[{err_type}]: {e}")
        print(f"失败详情已记录到: {PARSE_LOG_PATH}")
        # 返回符合协议的默认结果（步骤列表格式）
        default_task = {
            "command": user_text,
            "steps": [
                {"id": 1, "action": "重新解析指令（LLM 调用失败，请重试）"}
            ]
        }
        return default_task

if __name__ == "__main__":
    # 测试一下
    test_command = "去客厅拿本书"
    print(f"[输入指令] {test_command}")
    print()
    
    result = nlp_processor(test_command)
    print(f"--- 大脑解析结果 ---")
    print(f"生成的任务 JSON:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()