cmake_minimum_required(VERSION 3.10)
project(HumanoidRobot)

set(CMAKE_CXX_STANDARD 17)

# 寻找 BehaviorTree.CPP 库
find_package(behaviortree_cpp REQUIRED)

add_executable(robot_brain main.cpp)

# 链接库和头文件
target_link_libraries(robot_brain BT::behaviortree_cpp)