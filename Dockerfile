# 使用 Python 3.10 作为基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 将 client_child.py 复制到容器的工作目录
COPY client_child.py /app/
COPY config.ini /app/
COPY gmgn.py /app/
COPY portfolivalueCalculator.py /app/

# 安装任何所需的依赖包
# 如果有 requirements.txt 文件，可以将其复制并安装依赖
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 创建一个 logs 目录，用于挂载外部日志文件
RUN mkdir /app/logs

# 默认命令执行 client_child.py 脚本
CMD ["python", "client_child.py"]