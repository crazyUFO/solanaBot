# 使用官方 Python 3.10.6 镜像作为基础镜像
FROM python:3.10.6-slim

# 设置工作目录为 /app
WORKDIR /app

# 复制当前目录的所有文件到容器的 /app 目录中
COPY . /app

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt

# 启动应用
CMD ["python", "bot.py"]
