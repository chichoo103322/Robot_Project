#!/bin/bash
# 演示脚本：展示动态行为树生成与容错功能

echo "======================================"
echo "🤖 机器人行为树动态生成与容错演示"
echo "======================================"
echo ""

# 测试用例 1：正常任务（拿书）
echo "【测试 1】正常任务：去客厅拿本书"
echo "---"
cat > test_demo.py << 'EOF'
import sys
sys.path.insert(0, '/Users/jzxzhou/code/Robot_Project')
from brain.brain_node import nlp_processor

result = nlp_processor("去客厅拿本书")
with open("task_bridge.json", "w") as f:
    import json
    json.dump(result, f, ensure_ascii=False, indent=2)
EOF

python3 test_demo.py
echo "✓ task_bridge.json 已生成"
echo ""

echo "【测试 2】容错任务：去厨房拿水杯（预期失败，触发容错）"
echo "---"
cat > test_demo.py << 'EOF'
import sys
sys.path.insert(0, '/Users/jzxzhou/code/Robot_Project')
from brain.brain_node import nlp_processor

result = nlp_processor("去厨房拿水杯")
with open("task_bridge.json", "w") as f:
    import json
    json.dump(result, f, ensure_ascii=False, indent=2)
EOF

python3 test_demo.py
echo "✓ task_bridge.json 已生成（包含容错逻辑）"
echo ""

# 显示生成的 XML
echo "【生成的行为树 XML 结构】"
echo "---"
python3 << 'EOF'
import json
with open("task_bridge.json") as f:
    data = json.load(f)
# 格式化输出 XML
xml = data["tree_xml"]
# 简单的 XML 美化（为了可读性）
xml = xml.replace("><", ">\n<")
print(xml)
EOF

echo ""
echo "======================================"
echo "✓ 演示完成！"
echo "======================================"
echo ""
echo "现在可以运行 C++ 控制器来执行这个行为树："
echo "  cd /Users/jzxzhou/code/Robot_Project && ./cerebellum/build/robot_brain"
echo ""
