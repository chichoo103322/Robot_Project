# 📋 代码改动总结与快速参考

## 三个主要改动

### 1️⃣ `cerebellum/main.cpp` - C++ 后端改动

**改动重点**：
- ✅ 新增 `VoiceAlert` 节点类（接收 message 参数）
- ✅ 改进 `PickUp` 节点（水杯返回 FAILURE，其他返回 SUCCESS）
- ✅ 注册 `VoiceAlert` 节点到工厂
- ✅ 删除硬编码的 XML
- ✅ 从 JSON 中动态提取 `tree_xml` 字段
- ✅ 使用 `factory.createTreeFromText()` 动态创建树

**关键代码片段**：

```cpp
// 新增 VoiceAlert 类
class VoiceAlert : public SyncActionNode {
public:
    VoiceAlert(const std::string& name, const NodeConfig& config) 
        : SyncActionNode(name, config) {}
    
    static PortsList providedPorts() {
        return { InputPort<std::string>("message") };
    }
    
    NodeStatus tick() override {
        auto msg = getInput<std::string>("message");
        std::cout << "[语音播报] 📢 : " << msg.value() << std::endl;
        return NodeStatus::SUCCESS;
    }
};

// 改进 PickUp 的容错逻辑
class PickUp : public SyncActionNode {
    NodeStatus tick() override {
        auto msg = getInput<std::string>("object_name");
        std::string obj = msg.value();
        
        if (obj.find("水杯") != std::string::npos) {
            std::cout << "[动作] 🦾 尝试抓取: " << obj << " [失败] ❌" << std::endl;
            return NodeStatus::FAILURE;
        }
        
        std::cout << "[动作] 🦾 正在抓取: " << obj << " [成功] ✓" << std::endl;
        return NodeStatus::SUCCESS;
    }
};

// 注册节点
factory.registerNodeType<VoiceAlert>("VoiceAlert");  // ← 新增

// 动态加载 XML
std::string xml_text = data["tree_xml"].get<std::string>();
auto tree = factory.createTreeFromText(xml_text);
```

---

### 2️⃣ `brain/brain_node.py` - Python 前端改动

**改动重点**：
- ✅ 重构 LLM Prompt，让其充当 BehaviorTree.CPP XML 生成器
- ✅ 告诉 LLM 可用的控制节点：Sequence 和 Fallback
- ✅ 告诉 LLM 可用的动作节点：MoveTo, PickUp, VoiceAlert
- ✅ 设定容错规则（水杯失败触发 VoiceAlert）
- ✅ 输出格式必须是 `{"tree_xml": "..."}`
- ✅ 改进默认降级方案（返回 VoiceAlert 而不是 location + item）

**关键代码片段**：

```python
def nlp_processor(user_text):
    """将自然语言转化为 BehaviorTree.CPP 行为树 XML"""
    
    prompt = f"""
你是一个高级的 BehaviorTree.CPP (v4) XML 生成器。

【可用的控制节点】
1. <Sequence>: 顺序执行所有子节点，若有一个失败则整体失败
2. <Fallback>: 依次尝试子节点，直到某个成功则整体成功（容错逻辑）

【可用的动作节点】
1. <MoveTo target_place="地点"/>
2. <PickUp object_name="物体"/>
   - 特别注意：包含"水杯"的物体会抓取失败
   - 应该在 Fallback 中处理
3. <VoiceAlert message="播报内容"/>

【设计规则】
1. 必须使用 <Sequence> 完成主要任务流程
2. 对于容易失败的操作，使用 <Fallback> 提供备选方案
3. 当 PickUp 可能失败时，在 Fallback 中加入 VoiceAlert

【容错示例】
对于"去客厅拿水杯"：
<Fallback>
  <Sequence>
    <MoveTo target_place="客厅"/>
    <PickUp object_name="水杯"/>
  </Sequence>
  <VoiceAlert message="⚠️ 水杯无法抓取，请稍后再试"/>
</Fallback>

【输出格式（必须是严格的 JSON）】
{{
  "tree_xml": "<root BTCPP_format=\\"4\\"><BehaviorTree ID=\\"MainTree\\">...</BehaviorTree></root>"
}}

用户指令："{user_text}"
"""

    response = client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    raw_content = response.choices[0].message.content
    clean_json = raw_content.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_json)
```

---

### 3️⃣ JSON 中转文件格式变更

**旧格式**（已弃用）：
```json
{
  "location": "厨房",
  "item": "杯子"
}
```

**新格式**（当前）：
```json
{
  "tree_xml": "<root BTCPP_format=\"4\"><BehaviorTree ID=\"MainTree\"><Sequence><MoveTo target_place=\"厨房\"/><PickUp object_name=\"杯子\"/></Sequence></BehaviorTree></root>"
}
```

---

## 数据流示意

```
【用户指令】"去客厅拿水杯"
     ↓
【Python LLM】
  ├─ 分析指令
  ├─ 识别可能失败（水杯）
  └─ 生成带 Fallback 的 XML
     ↓
【task_bridge.json】
{
  "tree_xml": "<root BTCPP_format=\"4\"><BehaviorTree ID=\"MainTree\">
    <Fallback>
      <Sequence>
        <MoveTo target_place=\"客厅\"/>
        <PickUp object_name=\"水杯\"/>
      </Sequence>
      <VoiceAlert message=\"未能拿到水杯\"/>
    </Fallback>
  </BehaviorTree></root>"
}
     ↓
【C++ 工厂】
  ├─ 读取 JSON
  ├─ 提取 tree_xml
  ├─ 工厂解析 XML
  └─ 动态创建行为树
     ↓
【行为树执行】
  ├─ 尝试 Fallback 第一项：Sequence
  │   ├─ MoveTo 客厅 → SUCCESS
  │   └─ PickUp 水杯 → FAILURE
  ├─ Sequence 返回 FAILURE
  ├─ Fallback 转而执行第二项：VoiceAlert
  │   └─ VoiceAlert 播报 → SUCCESS
  └─ Fallback 返回 SUCCESS
     ↓
【完成】任务结束
```

---

## 编译和测试

### 编译 C++
```bash
cd /Users/jzxzhou/code/Robot_Project/cerebellum/build
cmake --build . -j
```

### 测试 Python
```bash
cd /Users/jzxzhou/code/Robot_Project
.venv/bin/python brain/brain_node.py
```

### 运行演示
```bash
bash demo.sh
```

### 完整集成测试

**终端 1：启动 C++ 控制器**
```bash
cd /Users/jzxzhou/code/Robot_Project
./cerebellum/build/robot_brain
```

**终端 2：发送任务**
```bash
cd /Users/jzxzhou/code/Robot_Project
.venv/bin/python brain/brain_node.py
```

---

## 关键特性对照表

| 特性 | 旧设计 | 新设计 |
|------|--------|--------|
| **XML 来源** | 硬编码在 C++ 中 | LLM 动态生成 |
| **容错机制** | ❌ 无 | ✅ Fallback 完整支持 |
| **节点定制** | 需要修改 C++ 代码 | LLM 自动选择 |
| **中转文件** | location + item | tree_xml |
| **可扩展性** | 低（需改 XML） | 高（LLM 自适应） |
| **错误处理** | 基础 | 🆕 VoiceAlert 播报 |
| **灵活性** | 单一流程 | 多分支容错流程 |

---

## 故障排查

### 问题 1：C++ 编译失败

**可能原因**：
- BehaviorTree.CPP 或 nlohmann/json 未安装
- CMake 版本过低

**解决**：
```bash
brew install behaviortree.cpp nlohmann-json cmake
cd cerebellum/build
cmake ..
cmake --build . -j
```

### 问题 2：JSON 解析错误

**可能原因**：
- `tree_xml` 字段缺失
- XML 格式非法

**解决**：
```bash
cat task_bridge.json  # 检查格式
```

### 问题 3：行为树不执行

**可能原因**：
- `robot_brain` 未从项目根目录启动
- `task_bridge.json` 权限不足
- 节点未正确注册

**解决**：
```bash
cd /Users/jzxzhou/code/Robot_Project
chmod 644 task_bridge.json
./cerebellum/build/robot_brain
```

---

## 下一步扩展方向

1. **状态反馈**：C++ 将执行结果写回 JSON
2. **WebSocket 实时推送**：替代轮询机制
3. **行为树可视化**：前端实时渲染执行中的节点
4. **动态计划生成**：更复杂的多步骤任务规划
5. **条件判断节点**：引入环境感知的决策

---

## 文件修改清单

- ✅ `cerebellum/main.cpp` - 新增节点、动态 XML 加载
- ✅ `brain/brain_node.py` - LLM Prompt 重构
- ✅ `task_bridge.json` - 中转文件格式更新
- ✅ `DYNAMIC_TREE_GUIDE.md` - 完整技术文档
- ✅ `CHANGES_SUMMARY.md` - 本文件

---

**🎉 所有改动已就绪，系统已支持动态行为树生成与容错机制！**
