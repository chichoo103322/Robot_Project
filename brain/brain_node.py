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
    将自然语言转化为 BehaviorTree.CPP 行为树 XML
    
    LLM 将生成一个包含 Sequence（顺序执行）和 Fallback（容错）的行为树。
    输出 JSON 格式：{"tree_xml": "<root>...</root>"}
    """
    prompt = f"""
你是一个高级的 BehaviorTree.CPP (v4) XML 生成器。你的任务是将用户的自然语言指令转化为结构化的行为树 XML。

【可用的控制节点】
1. <Sequence>: 顺序执行所有子节点，若有一个失败则整体失败
2. <Fallback>: 依次尝试子节点，直到某个成功则整体成功（容错逻辑）

【可用的动作节点】
1. <MoveTo target_place="地点"/>
   - 参数 target_place: 机器人要去的地点（如"厨房", "客厅", "卧室", "阳台"）

2. <PickUp object_name="物体"/>
   - 参数 object_name: 要抓取的物体名称
   - 特别注意：包含"水杯"的物体会抓取失败，应该在 Fallback 中处理

3. <VoiceAlert message="播报内容"/>
   - 参数 message: 要播报的文本内容
   - 用途：播报抓取失败等错误信息

【设计规则】
1. 必须使用 <Sequence> 完成主要任务流程
2. 对于容易失败的操作（如抓取易碎品），使用 <Fallback> 提供备选方案
3. 当 PickUp 可能失败时，在 Fallback 中加入 VoiceAlert 来播报失败原因

【容错示例】
对于用户指令 "去客厅拿水杯"：
- 直接用 Sequence 会失败（因为水杯无法抓取）
- 应该用 Fallback: 先尝试 Sequence(MoveTo + PickUp)，失败后触发 VoiceAlert 播报提示

【输出格式（必须是严格的 JSON）】
{{
  "tree_xml": "<root BTCPP_format=\"4\"><BehaviorTree ID=\"MainTree\">...</BehaviorTree></root>"
}}

【重要提醒】
1. XML 必须使用转义引号 \" 而不是 "
2. 整个 XML 必须在一行内或正确转义换行
3. 只输出 JSON，不要有其他文本
4. BehaviorTree ID 必须是 "MainTree"

用户指令："{user_text}"

现在生成对应的行为树 XML。如果用户指令涉及到"水杯"等易失败物体，请在 Fallback 中设计容错方案。
    """

    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1  # 调低随机性，保证 XML 格式稳定
        )
        
        # 提取并解析 JSON
        raw_content = response.choices[0].message.content
        # 简单清理可能存在的 Markdown 标签
        clean_json = raw_content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
        
    except Exception as e:
        print(f"解析失败: {e}")
        # 返回一个默认的容错行为树
        default_tree = {
            "tree_xml": """<root BTCPP_format="4"><BehaviorTree ID="MainTree"><VoiceAlert message="指令解析失败，请重试" /></BehaviorTree></root>"""
        }
        return default_tree

if __name__ == "__main__":
    # 测试一下
    test_command = "去客厅拿本书"
    print(f"[输入指令] {test_command}")
    print()
    
    result = nlp_processor(test_command)
    print(f"--- 大脑解析结果 ---")
    print(f"生成的行为树 XML:")
    print(result.get('tree_xml', '无法生成'))
    print()
    
    # 这一步是为后面打通 C++ 做准备
    # 使用脚本所在目录的上一级（项目根目录）作为中转文件路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bridge_path = os.path.join(project_root, "task_bridge.json")
    with open(bridge_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n已将行为树写入中转站: {bridge_path}")
        print(f"\nJSON 内容预览：")
        print(json.dumps(result, ensure_ascii=False, indent=2))