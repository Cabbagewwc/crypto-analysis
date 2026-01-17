# ===================================
# 加密货币智能分析系统 - Docker 镜像
# ===================================
# 支持两种模式：
# 1. HuggingFace Spaces (Web UI) - 设置 HF_SPACE=1
# 2. 命令行/定时任务 - 默认模式

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY *.py ./
COPY data_provider/ ./data_provider/

# 创建数据目录
RUN mkdir -p /app/data /app/logs /app/reports

# 设置环境变量默认值
ENV PYTHONUNBUFFERED=1
ENV LOG_DIR=/app/logs
ENV DATABASE_PATH=/app/data/crypto_analysis.db
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# 暴露端口（Web UI 模式）
EXPOSE 7860

# 健康检查
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# 启动脚本 - 根据 HF_SPACE 环境变量决定启动模式
# HuggingFace Spaces 会自动设置此变量
CMD ["sh", "-c", "if [ \"$HF_SPACE\" = '1' ] || [ -n \"$SPACE_ID\" ]; then python app.py; else python main.py --schedule; fi"]
