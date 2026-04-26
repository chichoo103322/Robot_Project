#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <ixwebsocket/IXNetSystem.h>
#include <ixwebsocket/IXWebSocket.h>
#include <nlohmann/json.hpp>

#include <chrono>
#include <cctype>
#include <filesystem>
#include <functional>
#include <fstream>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using namespace BT;
using json = nlohmann::json;
namespace fs = std::filesystem;

namespace {

std::string toLowerCopy(std::string value)
{
    for (char& c : value)
    {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return value;
}

std::vector<std::string> splitCsvLine(const std::string& line)
{
    std::vector<std::string> fields;
    std::string field;
    std::istringstream stream(line);
    while (std::getline(stream, field, ','))
    {
        fields.push_back(field);
    }
    return fields;
}

class VisionDetectNode : public SyncActionNode
{
public:
    VisionDetectNode(const std::string& name, const NodeConfig& config)
      : SyncActionNode(name, config)
    {
    }

    static PortsList providedPorts()
    {
        return {
            InputPort<std::string>("target_object"),
            OutputPort<std::string>("target_coordinates")
        };
    }

    NodeStatus tick() override
    {
        const std::string targetObject = getInput<std::string>("target_object").value_or("");
        if (targetObject.empty())
        {
            std::cerr << "[VisionDetect] target_object 为空" << std::endl;
            return NodeStatus::FAILURE;
        }

        fs::path latestFile;
        fs::file_time_type latestTime;
        bool foundFile = false;

        for (const auto& entry : fs::directory_iterator(fs::current_path()))
        {
            if (!entry.is_regular_file())
            {
                continue;
            }

            const std::string filename = entry.path().filename().string();
            const bool nameMatch =
                filename.rfind("object_coordinates_", 0) == 0 && entry.path().extension() == ".csv";
            if (!nameMatch)
            {
                continue;
            }

            const auto writeTime = entry.last_write_time();
            if (!foundFile || writeTime > latestTime)
            {
                latestFile = entry.path();
                latestTime = writeTime;
                foundFile = true;
            }
        }

        if (!foundFile)
        {
            std::cerr << "[VisionDetect] 未找到 object_coordinates_*.csv 文件" << std::endl;
            return NodeStatus::FAILURE;
        }

        std::ifstream file(latestFile);
        if (!file.is_open())
        {
            std::cerr << "[VisionDetect] 无法打开文件: " << latestFile.string() << std::endl;
            return NodeStatus::FAILURE;
        }

        std::string header;
        if (!std::getline(file, header))
        {
            std::cerr << "[VisionDetect] CSV 文件为空: " << latestFile.string() << std::endl;
            return NodeStatus::FAILURE;
        }

        const auto headerFields = splitCsvLine(header);
        int classIdx = -1;
        int xIdx = -1;
        int yIdx = -1;
        int zIdx = -1;

        for (size_t i = 0; i < headerFields.size(); ++i)
        {
            const std::string key = toLowerCopy(headerFields[i]);
            if (key == "class") classIdx = static_cast<int>(i);
            if (key == "x(m)") xIdx = static_cast<int>(i);
            if (key == "y(m)") yIdx = static_cast<int>(i);
            if (key == "z(m)") zIdx = static_cast<int>(i);
        }

        if (classIdx < 0 || xIdx < 0 || yIdx < 0 || zIdx < 0)
        {
            std::cerr << "[VisionDetect] CSV 表头缺少 Class/X(m)/Y(m)/Z(m): "
                      << latestFile.string() << std::endl;
            return NodeStatus::FAILURE;
        }

        std::vector<std::string> lines;
        std::string line;
        while (std::getline(file, line))
        {
            if (!line.empty())
            {
                lines.push_back(line);
            }
        }

        if (lines.empty())
        {
            std::cerr << "[VisionDetect] CSV 数据区为空: " << latestFile.string() << std::endl;
            return NodeStatus::FAILURE;
        }

        const std::string targetLower = toLowerCopy(targetObject);
        const size_t recentCount = std::min<size_t>(10, lines.size());

        for (size_t i = 0; i < recentCount; ++i)
        {
            const std::string& candidate = lines[lines.size() - 1 - i];
            const auto fields = splitCsvLine(candidate);
            const size_t needed = static_cast<size_t>(std::max({classIdx, xIdx, yIdx, zIdx})) + 1;
            if (fields.size() < needed)
            {
                continue;
            }

            if (toLowerCopy(fields[classIdx]) != targetLower)
            {
                continue;
            }

            const std::string coordinates = fields[xIdx] + "," + fields[yIdx] + "," + fields[zIdx];
            setOutput("target_coordinates", coordinates);
            std::cout << "[VisionDetect] 识别成功 target=" << targetObject
                      << " coordinates=" << coordinates << std::endl;
            return NodeStatus::SUCCESS;
        }

        std::cerr << "[VisionDetect] 最新数据中未找到目标: " << targetObject
                  << " file=" << latestFile.string() << std::endl;
        return NodeStatus::FAILURE;
    }
};

std::string escapeXml(const std::string& value)
{
    std::string out;
    out.reserve(value.size());
    for (char c : value)
    {
        switch (c)
        {
            case '&': out += "&amp;"; break;
            case '<': out += "&lt;"; break;
            case '>': out += "&gt;"; break;
            case '\"': out += "&quot;"; break;
            case '\'': out += "&apos;"; break;
            default: out += c; break;
        }
    }
    return out;
}

class RobotActionNode : public SyncActionNode
{
public:
    using Reporter = std::function<void(int, int, const std::string&, const std::string&, const std::string&)>;

    RobotActionNode(const std::string& name, const NodeConfig& config)
      : SyncActionNode(name, config)
    {
    }

    static PortsList providedPorts()
    {
        return {
            InputPort<std::string>("device"),
            InputPort<std::string>("action"),
            InputPort<std::string>("target"),
            InputPort<int>("step_id"),
            InputPort<int>("db_task_id")
        };
    }

    static void setReporter(Reporter reporter)
    {
        reporter_ = std::move(reporter);
    }

    NodeStatus tick() override
    {
        const std::string device = getInput<std::string>("device").value_or("未知设备");
        const std::string action = getInput<std::string>("action").value_or("未知动作");
        const std::string target = getInput<std::string>("target").value_or("未知目标");
        const int stepId = getInput<int>("step_id").value_or(-1);
        const int dbTaskId = getInput<int>("db_task_id").value_or(-1);

        std::cout << "[执行] task=" << dbTaskId << " step=" << stepId
                  << " device=" << device << " action=" << action
                  << " target=" << target << std::endl;

        if (reporter_)
        {
            reporter_(dbTaskId, stepId, device, "RUNNING", action);
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(200));

        if (reporter_)
        {
            reporter_(dbTaskId, stepId, device, "SUCCESS", action + " completed");
        }

        return NodeStatus::SUCCESS;
    }

private:
    static Reporter reporter_;
};

RobotActionNode::Reporter RobotActionNode::reporter_ = nullptr;

std::string buildTreeXml(const json& taskJson, int dbTaskId)
{
    if (!taskJson.contains("task_list") || !taskJson["task_list"].is_array())
    {
        throw std::runtime_error("task_json 缺少 task_list 数组");
    }

    std::ostringstream xml;
    xml << "<root BTCPP_format=\"4\"><BehaviorTree ID=\"MainTree\"><Sequence name=\"RootSequence\">";

    for (const auto& task : taskJson["task_list"])
    {
        const int stepId = task.value("id", -1);
        const std::string device = escapeXml(task.value("device", "未知设备"));
        const std::string action = escapeXml(task.value("action", "未知动作"));
        const std::string target = escapeXml(task.value("target", ""));
        const std::string failHandler = task.value("fail_handler", "");
        const bool shouldRetry = failHandler.find("重试") != std::string::npos;
        const bool isVisionStep = task.value("device", "") == "视觉";

        std::ostringstream taskNode;
        if (isVisionStep)
        {
            taskNode << "<VisionDetect target_object=\"" << target << "\""
                     << " target_coordinates=\"{target_coordinates}\"/>";
        }
        else
        {
            taskNode << "<RobotAction device=\"" << device << "\""
                     << " action=\"" << action << "\""
                     << " target=\"" << target << "\""
                     << " step_id=\"" << stepId << "\""
                     << " db_task_id=\"" << dbTaskId << "\"/>";
        }

        if (shouldRetry)
        {
            xml << "<RetryUntilSuccessful num_attempts=\"3\">"
                << taskNode.str()
                << "</RetryUntilSuccessful>";
        }
        else
        {
            xml << taskNode.str();
        }
    }

    xml << "</Sequence></BehaviorTree></root>";
    return xml.str();
}

void executeTaskJson(BehaviorTreeFactory& factory, const json& dispatchMsg, ix::WebSocket& ws)
{
    const int dbTaskId = dispatchMsg.value("task_id", -1);
    if (!dispatchMsg.contains("task_json") || !dispatchMsg["task_json"].is_object())
    {
        throw std::runtime_error("task_dispatch 缺少 task_json 对象");
    }

    const json taskJson = dispatchMsg["task_json"];
    const std::string xmlText = buildTreeXml(taskJson, dbTaskId);

    std::cout << "[调度] 收到任务 task_id=" << dbTaskId << "，开始执行" << std::endl;
    auto tree = factory.createTreeFromText(xmlText);
    tree.tickWhileRunning();

    json taskDone = {
        {"task_id", dbTaskId},
        {"status", "SUCCESS"},
        {"step_id", -1},
        {"detail", "all steps completed"}
    };
    ws.send(taskDone.dump());
    std::cout << "[调度] 任务完成 task_id=" << dbTaskId << std::endl;
}

}  // namespace

int main()
{
    ix::initNetSystem();

    BehaviorTreeFactory factory;
    factory.registerNodeType<RobotActionNode>("RobotAction");
    factory.registerNodeType<VisionDetectNode>("VisionDetect");

    ix::WebSocket ws;
    ws.setUrl("ws://127.0.0.1:8000/ws/robot");

    std::mutex executeMutex;

    RobotActionNode::setReporter([&ws](int dbTaskId, int stepId, const std::string& device,
                                       const std::string& status, const std::string& detail) {
        if (dbTaskId < 0)
        {
            return;
        }
        json payload = {
            {"task_id", dbTaskId},
            {"step_id", stepId},
            {"device", device},
            {"status", status},
            {"detail", detail}
        };
        ws.send(payload.dump());
    });

    ws.setOnMessageCallback([&](const ix::WebSocketMessagePtr& msg) {
        if (msg->type == ix::WebSocketMessageType::Open)
        {
            std::cout << ">>> 已连接后端 WebSocket: ws://127.0.0.1:8000/ws/robot" << std::endl;
            return;
        }

        if (msg->type == ix::WebSocketMessageType::Close)
        {
            std::cout << "[连接关闭] code=" << msg->closeInfo.code
                      << " reason=" << msg->closeInfo.reason << std::endl;
            return;
        }

        if (msg->type == ix::WebSocketMessageType::Error)
        {
            std::cerr << "[连接错误] " << msg->errorInfo.reason << std::endl;
            return;
        }

        if (msg->type != ix::WebSocketMessageType::Message)
        {
            return;
        }

        try
        {
            const json incoming = json::parse(msg->str);
            const std::string type = incoming.value("type", "");

            if (type != "task_dispatch")
            {
                return;
            }

            std::lock_guard<std::mutex> lock(executeMutex);
            executeTaskJson(factory, incoming, ws);
        }
        catch (const std::exception& e)
        {
            std::cerr << "[任务处理失败] " << e.what() << std::endl;
        }
    });

    ws.start();

    std::cout << ">>> 小脑端已启动，等待后端任务下发... (Ctrl+C 退出)" << std::endl;
    while (true)
    {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    ws.stop();
    ix::uninitNetSystem();
    return 0;
}