#include <iostream>
#include <fstream>
#include <string>
#include <chrono>
#include <thread>
#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <nlohmann/json.hpp> // 需要用到这个 JSON 库

using namespace BT;
using json = nlohmann::json;

// 之前的 MoveTo 和 PickUp 类保持不变...
class MoveTo : public SyncActionNode {
public:
    MoveTo(const std::string& name, const NodeConfig& config) : SyncActionNode(name, config) {}
    static PortsList providedPorts() { return { InputPort<std::string>("target_place") }; }
    NodeStatus tick() override {
        auto msg = getInput<std::string>("target_place");
        std::cout << "[动作] 🤖 正在前往: " << msg.value() << std::endl;
        return NodeStatus::SUCCESS;
    }
};

class PickUp : public SyncActionNode {
public:
    PickUp(const std::string& name, const NodeConfig& config) : SyncActionNode(name, config) {}
    static PortsList providedPorts() { return { InputPort<std::string>("object_name") }; }
    NodeStatus tick() override {
        auto msg = getInput<std::string>("object_name");
        std::cout << "[动作] 🦾 正在抓取: " << msg.value() << std::endl;
        return NodeStatus::SUCCESS;
    }
};

int main() {
    BehaviorTreeFactory factory;
    factory.registerNodeType<MoveTo>("MoveTo");
    factory.registerNodeType<PickUp>("PickUp");

    const std::string xml_text = R"(
    <root BTCPP_format="4">
        <BehaviorTree ID="MainTree">
            <Sequence>
                <MoveTo target_place="{location}" />
                <PickUp object_name="{item}" />
            </Sequence>
        </BehaviorTree>
    </root>
    )";

    std::cout << ">>> 机器人控制器已启动，等待指令... (按 Ctrl+C 退出)" << std::endl;

    while (true) {
        // 1. 检查是否存在中转文件
        std::ifstream f("task_bridge.json");
        if (f.good()) {
            try {
                json data = json::parse(f);
                f.close(); // 必须先关闭文件才能删除
                
                std::cout << "\n[检测到新任务！]" << std::endl;
                
                // 2. 创建树并注入黑板数据
                auto tree = factory.createTreeFromText(xml_text);
                tree.rootBlackboard()->set("location", data["location"].get<std::string>());
                tree.rootBlackboard()->set("item", data["item"].get<std::string>());

                // 3. 执行任务
                tree.tickWhileRunning();
                
                // 4. 执行完后删除文件，防止重复执行
                std::remove("task_bridge.json");
                std::cout << ">>> 任务完成，继续等待..." << std::endl;

            } catch (json::parse_error& e) {
                // 如果文件还没写完就被读取，可能会报错，跳过这次循环即可
            }
        }
        
        // 每 500 毫秒检查一次，节省 CPU
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
    return 0;
}