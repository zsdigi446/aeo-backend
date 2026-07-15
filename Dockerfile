# AEO Analyzer 后端 - Railway 部署用
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# Railway 注入 PORT 环境变量，uvicorn 监听该端口
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
