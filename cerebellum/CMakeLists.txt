cmake_minimum_required(VERSION 3.16)
project(HumanoidRobot)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# 寻找 BehaviorTree.CPP 库
find_package(behaviortree_cpp REQUIRED)
find_package(nlohmann_json REQUIRED)

# 当前项目仅使用 ws://，关闭 TLS 相关依赖（OpenSSL / MbedTLS）。
set(USE_TLS OFF CACHE BOOL "Disable TLS for ixwebsocket" FORCE)
set(USE_MBED_TLS OFF CACHE BOOL "Disable mbedTLS for ixwebsocket" FORCE)
set(USE_ZLIB OFF CACHE BOOL "Disable zlib for ixwebsocket" FORCE)

# 引入 ixwebsocket（C++ WebSocket 客户端）
FetchContent_Declare(
	ixwebsocket
	GIT_REPOSITORY https://github.com/machinezone/IXWebSocket.git
	GIT_TAG v11.4.5
)
FetchContent_MakeAvailable(ixwebsocket)

add_executable(robot_brain main.cpp)

# 链接库和头文件
target_link_libraries(robot_brain
	PRIVATE
		BT::behaviortree_cpp
		nlohmann_json::nlohmann_json
)

if(TARGET ixwebsocket::ixwebsocket)
	target_link_libraries(robot_brain PRIVATE ixwebsocket::ixwebsocket)
elseif(TARGET ixwebsocket)
	target_link_libraries(robot_brain PRIVATE ixwebsocket)
else()
	message(FATAL_ERROR "ixwebsocket target not found. Check FetchContent output.")
endif()