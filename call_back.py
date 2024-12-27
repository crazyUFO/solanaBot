import os
import logging
from flask import Flask, jsonify, request
import subprocess
from waitress import serve

# 创建 Flask 应用实例
app = Flask(__name__)

# 配置日志记录
log_folder = 'logs'
if not os.path.exists(log_folder):
    os.makedirs(log_folder)

# 配置日志输出格式和日志文件
log_filename = os.path.join(log_folder, 'app.log')

logging.basicConfig(
    level=logging.INFO,  # 设置日志级别
    format='%(asctime)s - %(levelname)s - %(message)s',  # 设置日志格式
    handlers=[
        logging.FileHandler(log_filename),  # 日志文件
        logging.StreamHandler()  # 控制台输出
    ]
)

# 获取 Logger 实例
logger = logging.getLogger()

# 预定义的 API 密钥（可以通过环境变量或配置文件管理）
API_SECRET_KEY = 'xiaosan@2020'  

@app.route('/')
def home():
    logger.info("Server is running")  # 记录 INFO 级别日志
    return "Server is running"

@app.route('/restart', methods=['POST'])
def restart():
    # 从请求头中获取 API 密钥
    api_key = request.headers.get('X-API-Key')  # 你可以选择其他头部字段名
    
    # 验证 API 密钥
    if api_key != API_SECRET_KEY:
        logger.warning(f"Unauthorized access attempt. Invalid API Key: {api_key}")
        return jsonify({
            "status": "error",
            "message": "Invalid API Key"
        }), 403  # HTTP 403 Forbidden 错误表示访问被拒绝

    # 密钥验证通过，执行重启脚本
    logger.info("API Key validated successfully. Restarting shell script...")
    try:
        # 调用 shell 脚本
        result = subprocess.run(["./restart.sh"], capture_output=True, text=True, check=True)
        
        # 记录脚本输出到日志
        logger.info(f"Shell script output: {result.stdout}")
        
        # 返回 shell 脚本的输出
        return jsonify({
            "status": "success",
            "message": "脚本重启成功",
            "output": result.stdout
        })
    except subprocess.CalledProcessError as e:
        # 记录错误信息到日志
        logger.error(f"Error occurred: {e.stderr}")
        
        # 如果出现错误，返回错误信息
        return jsonify({
            "status": "error",
            "message": "脚本重启失败",
            "error_output": e.stderr
        }), 500  # HTTP 500 错误码表示服务器内部错误
@app.route('/stop', methods=['POST'])
def stop():
    # 从请求头中获取 API 密钥
    api_key = request.headers.get('X-API-Key')  # 你可以选择其他头部字段名
    
    # 验证 API 密钥
    if api_key != API_SECRET_KEY:
        logger.warning(f"Unauthorized access attempt. Invalid API Key: {api_key}")
        return jsonify({
            "status": "error",
            "message": "Invalid API Key"
        }), 403  # HTTP 403 Forbidden 错误表示访问被拒绝

    # 密钥验证通过，执行重启脚本
    logger.info("API Key validated successfully. Restarting shell script...")
    try:
        # 调用 shell 脚本
        result = subprocess.run(["./stop.sh"], capture_output=True, text=True, check=True)
        
        # 记录脚本输出到日志
        logger.info(f"Shell script output: {result.stdout}")
        
        # 返回 shell 脚本的输出
        return jsonify({
            "status": "success",
            "message": "脚本重启成功",
            "output": result.stdout
        })
    except subprocess.CalledProcessError as e:
        # 记录错误信息到日志
        logger.error(f"Error occurred: {e.stderr}")
        
        # 如果出现错误，返回错误信息
        return jsonify({
            "status": "error",
            "message": "脚本重启失败",
            "error_output": e.stderr
        }), 500  # HTTP 500 错误码表示服务器内部错误


if __name__ == '__main__':
    logger.info("Starting the Flask application...")
    serve(app, host='0.0.0.0', port=5000)
