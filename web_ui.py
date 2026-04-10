import streamlit as st
import json
import os
from brain.brain_node import nlp_processor

# 设置页面配置
st.set_page_config(
    page_title="🤖 机器人控制中心",
    page_icon="🤖",
    layout="centered"
)

# 页面标题和简介
st.title("🤖 机器人控制中心")
st.markdown("""
欢迎使用机器人控制界面！在这里，您可以使用自然语言指令控制机器人。

**使用说明：**
- 在下方输入框中输入自然语言指令
- 点击"执行任务"按钮
- 系统将解析指令并下发给机器人控制器
""")

# 默认输入文本
default_text = "去厨房帮我拿个杯子"

# 文本输入框
user_input = st.text_input(
    "请输入自然语言指令：",
    value=default_text,
    placeholder="例如：去客厅帮我拿遥控器"
)

# 执行任务按钮
if st.button("执行任务", type="primary"):
    if user_input.strip() == "":
        st.error("请输入有效的指令！")
    else:
        # 显示加载动画
        with st.spinner("大脑正在解析指令..."):
            try:
                # 调用 NLP 处理器
                result = nlp_processor(user_input)
                
                # 展示解析结果
                st.subheader("📋 解析结果")
                st.json(result)
                
                # 写入 task_bridge.json
                project_root = os.path.dirname(os.path.abspath(__file__))
                bridge_path = os.path.join(project_root, "task_bridge.json")
                with open(bridge_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                # 成功提示
                st.success("✅ 任务已成功下发给 C++ 控制器！")
                st.info(f"指令已保存到：{bridge_path}")
                
            except Exception as e:
                st.error(f"❌ 处理失败：{str(e)}")

# 底部信息
st.markdown("---")
st.markdown("*基于大模型和行为树的智能机器人控制系统*")