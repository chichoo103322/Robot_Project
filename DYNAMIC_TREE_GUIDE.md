# 🤖 C++ 行为树动态生成与容错功能文档

## 概述

本功能实现了 BehaviorTree.CPP 的**动态 XML 生成**与**容错机制**，使得 Python 大脑端可以通过 LLM 直接生成行为树，而 C++ 控制端动态加载并执行。

---

## 架构变更

### 之前的设计（硬编码 XML）
```
用户输入 → Python NLP → 提取 location + item → 写入 JSON → C++ 读取 JSON → 黑板注入 → 硬编码树执行
```

### 现在的设计（动态 XML 生成）
```
用户输入 → LLM 生成行为树 XML → Python 将 XML 装入 JSON → 写入 task_bridge.json 
→ C++ 读取 JSON 提取 tree_xml → 工厂动态创建树 → 直接执行
```

---

## 核心改动说明

### 1️⃣ C++ 端改动 (`cerebellum/main.cpp`)

#### 新增：VoiceAlert 节点类
```cpp
class VoiceAlert : public SyncActionNode {
    NodeStatus tick() override {
        auto msg = getInput<std::string>("message");
        std::cout << "[语音播报] 📢 : " << msg.value() << std::endl;
        return NodeStatus::SUCCESS;
    }
};
```

**用途**：在容错逻辑中播报错误或提示信息。

#### 改进：PickUp 节点容错逻辑
```cpp
NodeStatus tick() override {
    auto msg = getInput<std::string>("object_name");
    std::string obj = msg.value();
    
    // 模拟容错：水杯无法抓取
    if (obj.find("水杯") != std::string::npos) {
        std::cout << "[动作] 🦾 尝试抓取: " << obj << " [失败] ❌" << std::endl;
        return NodeStatus::FAILURE;  // ← 返回失败，触发 Fallback
    }
    
    std::cout << "[动作] 🦾 正在抓取: " << obj << " [成功] ✓" << std::endl;
    return NodeStatus::SUCCESS;
}
```

#### 关键改动：动态 XML 加载
```cpp
// 旧方式：硬编码 XML + 黑板注入
const std::string xml_text = R"(...)";
auto tree = factory.createTreeFromText(xml_text);
tree.rootBlackboard()->set("location", data["location"]);

// 新方式：从 JSON 提取动态 XML
std::string xml_text = data["tree_xml"].get<std::string>();
auto tree = factory.createTreeFromText(xml_text);  // 直接执行
```

#### 节点注册
```cpp
factory.registerNodeType<MoveTo>("MoveTo");
factory.registerNodeType<PickUp>("PickUp");
factory.registerNodeType<VoiceAlert>("VoiceAlert");  // ← 新增
```

---

### 2️⃣ Python 端改动 (`brain/brain_node.py`)

#### 核心：LLM Prompt 重构

LLM 现在充当 **BehaviorTree.CPP XML 生成器**，而非简单的信息提取器。

**关键 Prompt 指令**：
```
你是一个高级的 BehaviorTree.CPP (v4) XML 生成器。

【可用的控制节点】
- <Sequence>: 顺序执行，有一个失败则整体失败
- <Fallback>: 依次尝试，直到某个成功则整体成功（容错逻辑）

【可用的动作节点】
- <MoveTo target_place="地点"/>
- <PickUp object_name="物体"/>
- <VoiceAlert message="播报内容"/>

【设计规则】
1. 对于容易失败的操作，使用 <Fallback> 提供备选方案
2. 当 PickUp 包含"水杯"时，设计容错：先尝试 Sequence，失败后触发 VoiceAlert
```

#### 输出格式
LLM 必须返回严格的 JSON：
```json
{
  "tree_xml": "<root BTCPP_format=\"4\"><BehaviorTree ID=\"MainTree\">...</BehaviorTree></root>"
}
```

#### 容错示例生成

用户输入：`"去厨房拿水杯"`

LLM 生成：
```xml
<root BTCPP_format="4">
  <BehaviorTree ID="MainTree">
    <Fallback>
      <Sequence>
        <MoveTo target_place="厨房"/>
        <PickUp object_name="水杯"/>
      </Sequence>
      <VoiceAlert message="⚠️ 水杯无法抓取，请稍后再试"/>
    </Fallback>
  </BehaviorTree>
</root>
```

执行流程：
1. 执行 Fallback 的第一个子节点 Sequence
2. Sequence 先执行 MoveTo → 成功
3. Sequence 再执行 PickUp("水杯") → **失败**（因为水杯无法抓取）
4. Sequence 返回失败，Fallback 转而执行第二个子节点
5. VoiceAlert 播报提示信息 → 成功
6. Fallback 返回成功，整个任务完成

---

## JSON 中转文件格式

### 旧格式（已弃用）
```json
{
  "location": "厨房",
  "item": "杯子"
}
```

### 新格式（current）
```json
{
  "tree_xml": "<root BTCPP_format=\"4\"><BehaviorTree ID=\"MainTree\">...</BehaviorTree></root>"
}
```

---

## 使用示例

### 示例 1：正常任务（无容错）
**用户指令**：去客厅拿本书

**Python 生成的 XML**：
```xml
<Sequence>
  <MoveTo target_place="客厅"/>
  <PickUp object_name="书"/>
</Sequence>
```

**C++ 执行输出**：
```
[检测到新任务！]
[动作] 🤖 正在前往: 客厅
[动作] 🦾 正在抓取: 书 [成功] ✓
>>> 任务完成，继续等待...
```

### 示例 2：容错任务
**用户指令**：去厨房拿水杯

**Python 生成的 XML**（带 Fallback）：
```xml
<Fallback>
  <Sequence>
    <MoveTo target_place="厨房"/>
    <PickUp object_name="水杯"/>
  </Sequence>
  <VoiceAlert message="⚠️ 水杯无法抓取，请稍后再试"/>
</Fallback>
```

**C++ 执行输出**：
```
[检测到新任务！]
[动作] 🤖 正在前往: 厨房
[动作] 🦾 尝试抓取: 水杯 [失败] ❌
[语音播报] 📢 : ⚠️ 水杯无法抓取，请稍后再试
>>> 任务完成，继续等待...
```

---

## 测试方法

### 1. 测试 Python 生成器
```bash
cd /Users/jzxzhou/code/Robot_Project
.venv/bin/python brain/brain_node.py
```

### 2. 运行演示脚本
```bash
bash demo.sh
```

### 3. 测试 C++ 执行（手动容错树）

准备一个包含 Fallback 的 JSON：
```bash
cat > task_bridge.json << 'EOF'
{
  "tree_xml": "<root BTCPP_format=\"4\"><BehaviorTree ID=\"MainTree\"><Fallback><Sequence><MoveTo target_place=\"厨房\"/><PickUp object_name=\"水杯\"/></Sequence><VoiceAlert message=\"⚠️ 水杯无法抓取，请稍后再试\" /></Fallback></BehaviorTree></root>"
}
EOF
```

启动 C++ 控制器：
```bash
./cerebellum/build/robot_brain
```

### 4. 完整集成测试

**终端 1：启动 C++ 控制器**
```bash
cd /Users/jzxzhou/code/Robot_Project
./cerebellum/build/robot_brain
```

**终端 2：发送 Python 指令**
```bash
cd /Users/jzxzhou/code/Robot_Project
.venv/bin/python brain/brain_node.py
```

**预期行为**：C++ 会检测到 task_bridge.json，加载其中的 XML，并动态执行。

---

## 可用节点参考

### 控制节点

| 节点 | 用途 | 子节点 | 执行规则 |
|------|------|--------|--------|
| `<Sequence>` | 顺序控制 | 多个 | 依次执行，有失败则整体失败 |
| `<Fallback>` | 容错控制 | 多个 | 依次尝试，有成功则整体成功 |

### 动作节点

| 节点 | 参数 | 功能 | 返回值 |
|------|------|------|--------|
| `<MoveTo>` | `target_place` | 移动到指定地点 | SUCCESS |
| `<PickUp>` | `object_name` | 抓取物体（"水杯"返回 FAILURE） | SUCCESS / FAILURE |
| `<VoiceAlert>` | `message` | 播报语音提示 | SUCCESS |

---

## 扩展建议

### 1. 添加更多容错策略
- 重试节点：失败 N 次后放弃
- 条件检查：执行前检查前置条件

### 2. 增加新的动作节点
```cpp
class OpenDoor : public SyncActionNode { /* ... */ };
class SwitchLight : public SyncActionNode { /* ... */ };
```

### 3. 实现状态反馈
- C++ 将执行状态写回 JSON
- Python 读取并展示在前端

### 4. WebSocket 实时推送
- 替代 JSON 文件轮询
- 实时化显示行为树执行过程

---

## 常见问题

**Q1: 为什么要用 Fallback？**  
A: 某些操作本身可能失败（如抓取易碎品），使用 Fallback 可以设计备选方案，提高任务成功率。

**Q2: 如果 LLM 生成的 XML 格式错误怎么办？**  
A: C++ 的 try-catch 会捕获异常，打印错误信息，继续等待下一个任务。

**Q3: 如何测试新的节点？**  
A: 先在 C++ 中注册新节点，然后在 XML 中使用它，运行程序观察输出。

**Q4: Sequence 和 Fallback 可以嵌套吗？**  
A: 可以！BehaviorTree.CPP 支持任意深度的嵌套。

---

## 总结

✅ **动态 XML 生成**：LLM 直接生成 BehaviorTree.CPP 兼容的 XML  
✅ **容错机制**：Fallback 支持失败恢复和备选方案  
✅ **解耦设计**：Python 生成树，C++ 执行树，通过 JSON 通信  
✅ **可扩展性**：轻松添加新节点、新控制逻辑  

这为未来的复杂任务编排、实时动态规划提供了基础架构！🚀
