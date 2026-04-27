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
        将自然语言转化为严格结构化的任务 JSON。

        输出格式：
        {
            "target_object": "目标物体名称",
            "task_list": [
                {
                    "id": 1,
                    "device": "视觉|底盘|机械臂|机械爪",
                    "action": "动作名称",
                    "target": "目标参数",
                    "condition": "完成条件",
                    "fail_handler": "失败处理策略"
                }
            ]
        }
    """
    prompt = f"""
你是机器人任务分解器。请将用户自然语言严格转换成 JSON 任务清单。

【输出要求】
1. 只能输出 JSON，不要输出任何解释、注释、Markdown 代码块。
2. 必须严格使用以下结构和字段名：
{{
    "target_object": "目标物体名称",
    "task_list": [
        {{
            "id": 1,
            "device": "视觉|底盘|机械臂|机械爪",
            "action": "动作名称",
            "target": "目标参数",
            "condition": "完成条件",
            "fail_handler": "失败处理策略"
        }}
    ]
}}
3. task_list 的 id 必须从 1 开始递增且连续。
4. device 字段必须且只能是：视觉、底盘、机械臂、机械爪。
5. 缺失信息时也要给出合理默认值，不能省略任何字段。

【Few-shot 示例】
用户输入："去拿杯子"
输出：
{{
    "target_object": "杯子",
    "task_list": [
        {{
            "id": 1,
            "device": "视觉",
            "action": "识别目标",
            "target": "杯子",
            "condition": "检测到杯子并返回位姿",
            "fail_handler": "重试识别3次，失败则请求人工协助"
        }},
        {{
            "id": 2,
            "device": "底盘",
            "action": "移动到目标",
            "target": "杯子所在位置",
            "condition": "底盘到达抓取预备点",
            "fail_handler": "重新规划路径并重试，失败则回到安全点"
        }},
        {{
            "id": 3,
            "device": "机械臂",
            "action": "下降到抓取位",
            "target": "杯子抓取位姿",
            "condition": "末端执行器到达抓取高度",
            "fail_handler": "回撤到预备位并重新对位一次"
        }},
        {{
            "id": 4,
            "device": "机械爪",
            "action": "夹紧",
            "target": "杯子",
            "condition": "夹爪闭合并检测到稳定夹持",
            "fail_handler": "松开后微调位置再夹一次，失败则终止任务"
        }}
    ]
}}

现在根据这条用户指令生成 JSON："{user_text}"
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
        # 返回符合协议的默认结果
        default_task = {
            "target_object": "未知目标",
            "task_list": [
                {
                    "id": 1,
                    "device": "视觉",
                    "action": "重新识别目标",
                    "target": "未知目标",
                    "condition": "识别到可执行目标",
                    "fail_handler": "提示用户重述指令"
                }
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