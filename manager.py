import asyncio
import websockets
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
import concurrent.futures
import redis
import time
import configparser
from itertools import cycle
# 创建配置解析器对象
config = configparser.ConfigParser()
# 读取INI文件时指定编码
with open('config.ini', 'r', encoding='utf-8') as f:
    config.read_file(f)
# 读取指定的参数
MAX_WORKERS = config.getint('General', 'MAX_WORKERS') #最大线程数
SINGLE_SOL = config.getfloat('General', 'SINGLE_SOL')  # 单次买入阈值
DAY_NUM = config.getint('General', 'DAY_NUM') # 间隔天数
BLANCE = config.getint('General', 'BLANCE')  # 账户余额阈值
TOKEN_BALANCE = config.getint('General', 'TOKEN_BALANCE') #单位是美刀
MIN_TOKEN_CAP = config.getint('General', 'MIN_TOKEN_CAP') #市值最小 单位是美刀
MAX_TOKEN_CAP = config.getint('General', 'MAX_TOKEN_CAP') #市值最大 单位是美刀
TELEGRAM_BOT_TOKEN = config.get('TELEGRAM', 'TELEGRAM_BOT_TOKEN')  # Telegram 机器人的 API Token
TELEGRAM_CHAT_ID = config.get('TELEGRAM', 'TELEGRAM_CHAT_ID')  # 你的 Telegram 用户或群组 ID
HELIUS_API_KEY = config.get('General', 'HELIUS_API_KEY')#HELIUS API KEY
REDIS_HOST = config.get('REDIS', 'REDIS_HOST') #本地
REDIS_PORT =  config.getint('REDIS', 'REDIS_PORT')
REDIS_PWD = config.get('REDIS', 'REDIS_PWD')
REDIS_DB = config.getint('REDIS', 'REDIS_DB')
REDIS_LIST = config.get('REDIS', 'REDIS_LIST')
TOKEN = config.get('General', 'SOLSCAN_TOKEN')
WS_URL = config.get('General', 'WS_URL') # WebSocket 地址
TOKEN_EXPIRY = 30 * config.getint('General', 'TOKEN_EXPIRY') # 筛选地址活跃度为10分钟活跃
# 日志文件夹和文件名
LOG_DIR = config.get('LOG', 'DIR')
LOG_NAME = config.get('LOG', 'NAME')
ADDRESS_EXPIRY = "expiry:"#redis存放已经请求过的 地址
ADDRESS_SUCCESS = "success:"#存放播报的
TOKEN_IN_SCOPE = "token:" #保存范围内以上的币种
REDIS_EXPIRATION_TIME = 3 * 24 * 60 * 60 #redis 缓存请求过的地址，三天之内不在请求 
# 创建线程池执行器
executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
# 常量定义

# 日志文件夹和文件名
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_filename = os.path.join(LOG_DIR,LOG_NAME)

# 创建一个TimedRotatingFileHandler，日志每12小时轮换一次，保留最近7天的日志
handler = TimedRotatingFileHandler(
    log_filename,
    when="h",  # 按小时轮换
    interval=12,  # 每12小时轮换一次
    backupCount=6,  # 保留最近14个轮换的日志文件（即7天的日志）
    encoding="utf-8"  # 指定文件编码为 utf-8，解决中文乱码问题
)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler, logging.StreamHandler()]  # 同时输出到文件和控制台
)

logging.info("日志轮换配置完成")

# 初始化 Redis
redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PWD,
    decode_responses=True
)

ws = None  # WebSocket 连接

# 定义队列名称
queues = [f"tokens_{i}" for i in range(1, 11)]  # 10个队列: tokens_1, tokens_2, ..., tokens_10

# 循环队列生成器（确保按顺序分配数据到队列）
queue_cycle = cycle(queues)

# 初始化所有队列的计数器
def reset_counters():
    """将所有队列的推送和处理计数器初始化为0"""
    for queue_name in queues:
        # 重置推送计数器
        redis_client.set(f"{queue_name}_count", 0)
        # 重置收到计数器
        redis_client.set(f"{queue_name}_processed_count", 0)
        # 重置播报计数器
        redis_client.set(f"{queue_name}_success_count", 0)
        logging.info(f"已将队列 {queue_name} 的计数器重置为 0")
# 先重置计数器
reset_counters()

async def cleanup_subscriptions():
    """清理过期的订阅或处理其他清理操作"""
    while True:
        for list_name in queues:            
            logging.info(f"队列 {list_name} 推送 {redis_client.get(f"{list_name}_count")} 条")
            logging.info(f"队列 {list_name} 收到 {redis_client.get(f"{list_name}_processed_count")} 条")
            logging.info(f"队列 {list_name} 播报 {redis_client.get(f"{list_name}_success_count")} 条")
        await asyncio.sleep(60)  # 每60秒检查一次

async def websocket_handler():
    """处理 WebSocket 连接与数据"""
    global ws
    while True:
        try:
            logging.info("正在尝试建立 WebSocket 连接...")
            async with websockets.connect(WS_URL) as ws_instance:
                ws = ws_instance  # 存储 WebSocket 连接实例
                logging.info("WebSocket 连接已建立！")
                # 订阅请求
                payload = {
                    "method": "subscribeNewToken",
                }
                await ws.send(json.dumps(payload))
                logging.info("订阅请求已发送")

                while True:
                    data = await ws.recv()  # 等待并接收新的消息
                    try:
                        message = json.loads(data)
                        if not "txType" in message:
                            logging.info(f"ws 推送的消息有错误 没有txType")
                        if "txType" in message and message['txType'] == 'create':
                            # 获取下一个队列名
                            queue_name = next(queue_cycle)
                            redis_client.rpush(queue_name, json.dumps(data))  # 推送到对应的 Redis 队列
                            logging.info(f"新建盘数据已推送至 {queue_name}")
                            # 更新计数器
                            redis_client.incr(f"{queue_name}_count")
                    except json.JSONDecodeError:
                        logging.error(f"消息解析失败: {data}")
                    except Exception as e:
                        logging.error(f"接收消息时发生错误: {e}")

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            logging.error(f"WebSocket 连接失败: {e}. 正在重连...")
            await asyncio.sleep(5)  # 等待 5 秒后重新连接

        except Exception as e:
            logging.error(f"发生了意外错误: {e}. 正在重连...")
            await asyncio.sleep(5)  # 等待 5 秒后重新连接

# 主程序
async def main():
    """启动 WebSocket 和清理任务"""
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())

    # 等待任务完成
    await asyncio.gather(ws_task, cleanup_task)

# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
