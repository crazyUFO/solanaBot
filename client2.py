####2号脚本采用redis链接方法，从redis中遍历数据取出进行订阅操作
import asyncio
import websockets
import json
import aiohttp
import logging
import requests  # 用于发送 Telegram API 请求
import os
from logging.handlers import TimedRotatingFileHandler
from portfolivalueCalculator import PortfolioValueCalculator
from datetime import datetime, timedelta
import concurrent.futures
import redis
# 创建线程池执行器
executor = concurrent.futures.ThreadPoolExecutor(max_workers=15)
# 常量定义
SINGLE_SOL = 0.5  # 单次买入阈值
DAY_NUM = 2  # 间隔天数
BLANCE = 100  # 账户余额阈值
TOKEN_BALANCE = 10000 #单位是美刀
MIN_TOKEN_CAP = 10000 #市值最小 单位是美刀
MAX_TOKEN_CAP = 100000 #市值最大 单位是美刀
TELEGRAM_BOT_TOKEN = '7914406898:AAHP3LuMY2R647rK3gI0qsiJp0Fw8J-aW_E'  # Telegram 机器人的 API Token
TELEGRAM_CHAT_ID = '@laojingyu'  # 你的 Telegram 用户或群组 ID
HELIUS_API_KEY = 'c3b599f9-2a66-494c-87da-1ac92d734bd8'#HELIUS API KEY
# Redis 配置
REDIS_HOST = "43.153.140.171"
REDIS_PORT = 6379
REDIS_PWD = "xiaosan@2020"
REDIS_DB = 0
# API token 用于身份验证
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3MzMyMDAyNzMxNzUsImVtYWlsIjoibGlhbmdiYTc4ODhAZ21haWwuY29tIiwiYWN0aW9uIjoidG9rZW4tYXBpIiwiYXBpVmVyc2lvbiI6InYyIiwiaWF0IjoxNzMzMjAwMjczfQ.ll8qNb_Z8v4JxdFvMKGWKDHoM7mh2hB33u7noiukOfA"
WS_URL = "wss://pumpportal.fun/api/data"  # WebSocket 地址

# 请求头
headers = {
    "token": TOKEN
}

# 日志文件夹和文件名
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_filename = os.path.join(LOG_DIR, "client2.log")

# 创建一个TimedRotatingFileHandler，日志每12小时轮换一次，保留最近7天的日志
handler = TimedRotatingFileHandler(
    log_filename,
    when="h",  # 按小时轮换
    interval=4,  # 每12小时轮换一次
    backupCount=3,  # 保留最近14个轮换的日志文件（即7天的日志）
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
message_queue_1 = asyncio.Queue()  # 处理 WS队列监听
message_queue_2 = asyncio.Queue()  # 处理 分发线程任务
subscriptions = []# 存储未打满10W也不低于1W美金的token
ws = None# WebSocket 连接


async def cleanup_subscriptions():
    while True:      
        logging.error(f"----目前进程播报----")
        logging.error(f"----创建监听队列{message_queue_1.qsize()} 条----")
        logging.error(f"----数据处理队列{message_queue_2.qsize()} 条----")
        logging.error(f"----进程播报结束----")
        logging.info(f"目前订阅数量 {len(subscriptions)}")
        executor.map(check_tokens_to_redis, subscriptions)
        await asyncio.sleep(3600)  # 每过1小时检查一次

# 异步函数：处理 WebSocket
async def websocket_handler():
    global ws
    try:
        async with websockets.connect(WS_URL) as ws_instance:
            ws = ws_instance  # 这里将 WebSocket 连接存储到全局变量 ws
            # 持续接收消息并放入队列
            while True:
                data = await ws.recv()  # 等待并接收新的消息
                try:
                    message = json.loads(data)
                    if "txType" in message and message["txType"] == "buy":
                        await message_queue_2.put(data)  # 买入单推送
                    else:
                        # logging.warning(f"无法识别的消息类型: {data}")
                        pass
                
                except json.JSONDecodeError:
                        logging.error(f"消息解析失败: {data}")

    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"WebSocket 连接意外关闭: {e}. 正在重连...")
        await asyncio.sleep(5)  # 等待 5 秒后重新连接
    except Exception as e:
        logging.error(f"发生了意外错误: {e}. 正在重连...")
        await asyncio.sleep(5)  # 等待 5 秒后重新连接

# 监听并处理队列数据
async def listen_to_redis():
    logging.info("开始监听 Redis 队列...")
    while True:
        try:
            # 从 Redis 队列中获取数据
            message = redis_client.lpop("tokens")
            if message:
                # 收到服务端的redis消息更新
                logging.info(f"收到队列消息: {message}")
                data = json.loads(message)
                token = data.get('address');             
                if token not in subscriptions:
                    subscriptions.append(token)
                    logging.info(f"订阅新地址 {token} 已记录。")
                payload = {
                    "method": "subscribeTokenTrade",
                    "keys": [token]  # array of token CAs to watch
                }
                await ws.send(json.dumps(payload))
            else:
                # 如果队列为空，等待一会儿再检查
                await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"监听 Redis 队列时出错: {e}")

#异步函数：从队列中获取交易者数据并处理
async def transactions_message():
    async with aiohttp.ClientSession() as session:  # 创建一个会话，用于所有请求
        while True:
            # 从队列中获取消息并处理
            data = await message_queue_2.get()
            try:
                big_data = json.loads(data)

                if "traderPublicKey" not in big_data:
                    continue
                        
                logging.info(f"处理交易: {big_data['signature']} 开始请求详情")
                # 将任务提交给线程池进行处理
                executor.submit(start, session, big_data)
                #await start(session, big_data)  
                
            except Exception as e:
                logging.error(f"处理消息时出错2: {e}")

def start(session, item):
    logging.info(f"请求交易数据: {item['signature']}")#交易的tx_hash
    response=requests.get(f"https://pro-api.solscan.io/v2.0/transaction/actions?tx={item['signature']}",headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        # 检查数据是否符合条件
        sol_bal_change = response_data.get('data',{}).get('activities',[])
        logging.info(f"获取TX行为数据成功: {len(sol_bal_change)} 条")
        active_data = {}
        for value in sol_bal_change:
                if(value['name'] == "PumpFunSwap" and value['program_id'] == '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'):
                    active_data  = value.get('data',{})
                    break;
        item["amount"] = active_data.get("amount_1",0)/ (10 ** 9)
        logging.error(f'交易金额-----:{item["amount"]}')
        if item["amount"] >= SINGLE_SOL:#条件一大于预设值
                check_user_transactions(session,item)
    else:
        logging.error(f"请求交易数据数据失败: {response.status_code} - { response.text()}")

# 异步请求用户交易记录和余额
def check_user_transactions(session, item):
    logging.info(f"请求用户交易记录: {item['traderPublicKey']}")
    response= requests.get(f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={item['traderPublicKey']}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&page=1&page_size=40&sort_by=block_time&sort_order=desc",headers=headers) 
    if response.status_code == 200:
        response_data =  response.json()
        #logging.info(f"获取用户交易记录成功: {response_data}")
        logging.info(f"获取用户交易记录成功 {len(response_data)} 条")
        if response_data.get('success') and len(response_data.get('data', [])) >= 2:
            arr = response_data['data']
            time1 = arr[0]
            time2 = arr[1]
            # 遍历数据
            for i in range(len(arr)):
                if arr[i]['trans_id'] == item['signature']:  # 对比
                    logging.info(f"从用户活动第 {i} 条中找到了 {item['signature']} hash签名")
                    # 取出当前数据和下一条数据
                    time1 = arr[i]
                    time2 = arr[i + 1] if i + 1 < len(arr) else None  # 防止越界
                    break  # 结束循环
            time_diff = (time1['block_time'] - time2['block_time']) / 86400  # 将区块时间转换为天数
            if time_diff >= DAY_NUM:
                logging.info(f"---------检测到用户交易数据----------------")
                logging.info(f"{item['traderPublicKey']} 在过去 {time_diff:.4f} 天内没有代币交易，突然进行了交易。")
                logging.info("---------检测结束---------------")
                
                # 检查用户账户余额
                check_user_balance(session, item)

    else:
        logging.error(f"请求用户交易记录失败: {response.status_code} - { response.text()}")

# 异步请求用户的账户余额
def check_user_balance(session, item):
    logging.info(f"请求用户余额: {item['traderPublicKey']}")
    portfolio_calculator = PortfolioValueCalculator(
    balances_api_key=HELIUS_API_KEY,
    account_address=item['traderPublicKey']
    )
    logging.info(f"用户余额--{item['traderPublicKey']}--tokens:{total_balance} sol:{sol}")
    try:
        total_balance = portfolio_calculator.calculate_total_value()
        sol = portfolio_calculator.get_sol()
        if total_balance >= TOKEN_BALANCE or sol >= BLANCE:
                    message = f'''
<b>🐋🐋🐋🐋鲸鱼钱包🐋🐋🐋🐋</b>

token:\n<code>{item["mint"]}</code>

购买的老钱包:\n<code>{item['traderPublicKey']}</code>

购买金额:<b>{(item['amount']):.4f} SOL<b/>
钱包余额:<b>{sol} SOL<b/>
钱包代币余额总计:<b> {total_balance} USDT<b/>
链上查看钱包: <a href="https://solscan.io/account/{item['traderPublicKey']}"><b>SOLSCAN</b></a> <a href="https://gmgn.ai/sol/address/{item['traderPublicKey']}"><b>GMGN</b></a>
token详情:<a href="https://solscan.io/account/{item['traderPublicKey']}#defiactivities"><b>详情</b></a>

📈查看K线: <a href="https://pump.fun/coin/{item["mint"]}"><b>PUMP</b></a> <a href="https://gmgn.ai/sol/token/{item["mint"]}"><b>GMGN</b></a>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
                        '''
                    send_telegram_notification(message)
    except Exception as e:
            logging.error(f"获取tokens的余额出错{e}")
        


# 发送 Telegram 消息
def send_telegram_notification(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"  # 设置为 HTML 格式
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            logging.info("通知发送成功！")
        else:
            logging.error(f"通知发送失败: {response.status_code}")
    except Exception as e:
        logging.error(f"发送通知时出错: {e}")

#请求代币元信息

def check_tokens_to_redis(token):
    url = f"https://pro-api.solscan.io/v2.0/token/meta?address={token}"
    response = requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data = response.json()
        data = response_data.get('data',{})
        market_cap = data.get('market_cap',0)
        logging.info(f"正在检查token市值 {token}")
        if market_cap < MIN_TOKEN_CAP or market_cap > MAX_TOKEN_CAP:# 再范围之外移除监听
            del subscriptions[token]
            logging.info(f"{token} 市值为 {market_cap:.4f} 超出范围 正在移除监听")
            # 取消订阅
            if subscriptions and ws:
                payload = {
                    "method": "unsubscribeTokenTrade",
                    "keys": [token]  
                }
                ws.send(json.dumps(payload))

    else:
        logging.error(f"{token}获取元信息失败 : {response.status_code}")


# 主程序
async def main():
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动处理队列的任务
    redis_task = asyncio.create_task(listen_to_redis())

    # 启动交易监听队列任务
    transactions_task= asyncio.create_task(transactions_message())

    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())

    # 等待任务完成
    await asyncio.gather(ws_task, redis_task,transactions_task,cleanup_task)
    # await asyncio.gather(redis_task)


# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())