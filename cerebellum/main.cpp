#include <iostream>
#include <fstream>
#include <string>
#include <chrono>
#include <thread>
#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp>

using namespace BT;
using json = nlohmann::json;

// ========== 动作节点定义 ==========

// MoveTo: 移动到指定地点
class MoveTo : public SyncActionNode {
public:
    MoveTo(const std::string& name, const NodeConfig& config) : SyncActionNode(name, config) {}
    
    static PortsList providedPorts() {
        return { InputPort<std::string>("target_place") };
    }
    
    NodeStatus tick() override {
        auto msg = getInput<std::string>("target_place");
        std::cout << "[动作] 🤖 正在前往: " << msg.value() << std::endl;
        return NodeStatus::SUCCESS;
    }
};

// PickUp: 抓取物体
class PickUp : public SyncActionNode {
public:
    PickUp(const std::string& name, const NodeConfig& config) : SyncActionNode(name, config) {}
    
    static PortsList providedPorts() {
        return { InputPort<std::string>("object_name") };
    }
    
    NodeStatus tick() override {
        auto msg = getInput<std::string>("object_name");
        std::cout << "[动作] 🦾 正在抓取: " << msg.value() << std::endl;
        return NodeStatus::SUCCESS;
    }
};

// VoiceAlert: 新增的语音播报节点
class VoiceAlert : public SyncActionNode {
public:
    VoiceAlert(const std::string& name, const NodeConfig& config) : SyncActionNode(name, config) {}
    
    static PortsList providedPorts() {
        return { InputPort<std::string>("message") };
    }
    
    NodeStatus tick() override {
        auto msg = getInput<std::string>("message");
        std::cout << "[语音播报] 📢 : " << msg.value() << std::endl;
        return NodeStatus::SUCCESS;
    }
};

int main() {
    BehaviorTreeFactory factory;
    
    // 注册所有节点
    factory.registerNodeType<MoveTo>("MoveTo");
    factory.registerNodeType<PickUp>("PickUp");
    factory.registerNodeType<VoiceAlert>("VoiceAlert");

    std::cout << ">>> 机器人控制器已启动，等待指令... (按 Ctrl+C 退出)" << std::endl;

    while (true) {
        // 1. 检查是否存在中转文件
        std::ifstream f("task_bridge.json");
        if (f.good()) {
            try {
                json data = json::parse(f);
                f.close(); // 必须先关闭文件才能删除
                
                std::cout << "\n[检测到新任务！]" << std::endl;
                
                // 2. 从 JSON 中提取动态 XML
                std::string xml_text = data["tree_xml"].get<std::string>();
                
                // 3. 使用工厂动态创建行为树
                auto tree = factory.createTreeFromText(xml_text);
                
                // 4. 执行任务
                tree.tickWhileRunning();
                
                // 5. 执行完后删除文件，防止重复执行
                std::remove("task_bridge.json");
                std::cout << ">>> 任务完成，继续等待..." << std::endl;

            } catch (json::parse_error& e) {
                // 如果文件还没写完或 JSON 格式错误，跳过这次循环
                std::cerr << "[错误] JSON 解析失败: " << e.what() << std::endl;
            } catch (std::exception& e) {
                // 行为树创建或执行失败
                std::cerr << "[错误] 行为树执行失败: " << e.what() << std::endl;
            }
        }
        
        // 每 500 毫秒检查一次，节省 CPU
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
    return 0;
}