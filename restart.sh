#!/bin/bash

# 获取当前脚本所在目录
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# 指定虚拟环境路径
VENV_DIR="$SCRIPT_DIR/.venv"

# 指定要运行的 Python 脚本路径
PYTHON_SCRIPT="$SCRIPT_DIR/main.py"

# 检查虚拟环境是否存在
if [ ! -d "$VENV_DIR" ]; then
    echo "虚拟环境未找到！请确保虚拟环境位于: $VENV_DIR"
    exit 1
fi

# 检查脚本是否已在运行
RUNNING_PID=$(ps -ef | grep "[p]ython $PYTHON_SCRIPT" | awk '{print $2}')

if [ -n "$RUNNING_PID" ]; then
    echo "脚本已经在运行，进程 PID: $RUNNING_PID"
    exit 0
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 运行 Python 脚本（在后台）
nohup python "$PYTHON_SCRIPT" > "$SCRIPT_DIR/output.log" 2>&1 &

# 获取后台进程的 PID
PID=$!

# 打印后台进程信息
echo "脚本已启动，进程 PID: $PID"
echo "日志文件: $SCRIPT_DIR/output.log"

# 退出虚拟环境
deactivate
