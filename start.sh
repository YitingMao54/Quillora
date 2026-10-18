#!/bin/bash
# 华为PC营销软文智能体 - 一键启动
cd "$(dirname "$0")"
echo "正在启动 华为PC营销软文智能体 ..."
echo "启动后浏览器访问: http://localhost:8501"
echo "（按 Ctrl+C 可停止服务）"
./venv/bin/streamlit run app.py --server.headless true --server.port 8501
