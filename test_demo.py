import sys
sys.path.insert(0, '/Users/jzxzhou/code/Robot_Project')
from brain.brain_node import nlp_processor

result = nlp_processor("去厨房拿水杯")
with open("task_bridge.json", "w") as f:
    import json
    json.dump(result, f, ensure_ascii=False, indent=2)
