####2号脚本采用redis链接方法，从redis中遍历数据取出进行订阅操作
import asyncio
import redis.client
import websockets
import json
import logging
import requests  # 用于发送 Telegram API 请求
import os
from logging.handlers import TimedRotatingFileHandler
from portfolivalueCalculator import PortfolioValueCalculator
from datetime import datetime, date
import concurrent.futures
import redis
import time
# 创建线程池执行器
executor = concurrent.futures.ThreadPoolExecutor(max_workers=15)
# 常量定义
SINGLE_SOL = 0.5  # 单次买入阈值
DAY_NUM = 3  # 间隔天数
BLANCE = 100  # 账户余额阈值
TOKEN_BALANCE = 10000 #单位是美刀
MIN_TOKEN_CAP = 10000 #市值最小 单位是美刀
MAX_TOKEN_CAP = 100000 #市值最大 单位是美刀
TELEGRAM_BOT_TOKEN = '7914406898:AAHP3LuMY2R647rK3gI0qsiJp0Fw8J-aW_E'  # Telegram 机器人的 API Token
TELEGRAM_CHAT_ID = '@laojingyu'  # 你的 Telegram 用户或群组 ID
HELIUS_API_KEY = 'c3b599f9-2a66-494c-87da-1ac92d734bd8'#HELIUS API KEY
# Redis 配置
#REDIS_HOST = "43.153.140.171" #远程
REDIS_HOST = "127.0.0.1" #本地
REDIS_PORT = 6379
REDIS_PWD = "xiaosan@2020"
REDIS_DB = 0
# API token 用于身份验证
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3MzMyMDAyNzMxNzUsImVtYWlsIjoibGlhbmdiYTc4ODhAZ21haWwuY29tIiwiYWN0aW9uIjoidG9rZW4tYXBpIiwiYXBpVmVyc2lvbiI6InYyIiwiaWF0IjoxNzMzMjAwMjczfQ.ll8qNb_Z8v4JxdFvMKGWKDHoM7mh2hB33u7noiukOfA"
WS_URL = "wss://pumpportal.fun/api/data"  # WebSocket 地址


TOKEN_EXPIRY = 10 * 60 # 筛选地址活跃度为10分钟活跃
ADDRESS_EXPIRY = "expiry:"#redis存放已经请求过的 地址
ADDRESS_SUCCESS = "success:"#存放播报的
TOKEN_IN_SCOPE = "token:" #保存范围内以上的币种
REDIS_EXPIRATION_TIME = 3 * 24 * 60 * 60 #redis 缓存请求过的地址，三天之内不在请求 

TOKENS_PATH = "tokens.txt"

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
subscriptions = {}# 存储未打满10W也不低于1W美金的token
ws = None# WebSocket 连接
# 事件标记，表示 WebSocket 已连接
ws_initialized_event = asyncio.Event()

async def cleanup_subscriptions():
    while True:
        await ws_initialized_event.wait()
        current_time = time.time()
        expired_addresses = []
        # 遍历所有订阅，最后一次交易时间超时
        for mint_address, last_trade_time in subscriptions.items():
            if current_time - last_trade_time >= TOKEN_EXPIRY:
                expired_addresses.append(mint_address)
        
        # 移除过期的订阅
        for mint_address in expired_addresses:
            redis_client.delete(redis_client.delete(f"{TOKEN_IN_SCOPE}{mint_address}"))
            del subscriptions[mint_address]
            logging.info(f"订阅 {mint_address} 活跃度低下 已取消订阅")
        
        # #将剩下的这些，再看看市值有没有超过设定值，超过也一起删了
        # for token,last_trade_time in subscriptions.items():
        #     executor.submit(check_tokens_to_redis, token)
        #取消订阅
        if ws:
        #将订阅的数组分片，以免数据过大 WS会断开
            chunks = [expired_addresses[i:i + 30] for i in range(0, len(expired_addresses), 30)]
            for chunk in chunks:
                # 
                payload = {
                    "method": "unsubscribeTokenTrade",
                    "keys": chunk  
                }
                await ws.send(json.dumps(payload))
                await asyncio.sleep(2)
        logging.error(f"----目前进程播报----")
        logging.error(f"----创建监听队列{message_queue_1.qsize()} 条----")
        logging.error(f"----数据处理队列{message_queue_2.qsize()} 条----")
        logging.error(f"----进程播报结束----")
        logging.info(f"目前订阅数量 {len(subscriptions)}")
        logging.info(f"本次取消数量 {len(expired_addresses)}")
        await asyncio.sleep(60)  # 每过1小时检查一次

async def websocket_handler():
    global ws
    while True:
        try:
            logging.info("正在尝试建立 WebSocket 连接...")
            async with websockets.connect(WS_URL) as ws_instance:
                ws = ws_instance  # 存储 WebSocket 连接实例
                logging.info("WebSocket 连接已建立！")
                ws_initialized_event.set()  # 标记 WebSocket 连接已完成

                # 持续接收消息并处理
                while True:
                    data = await ws.recv()  # 等待并接收新的消息
                    try:
                        message = json.loads(data)
                        if "txType" in message and message["txType"] == "buy":
                            await message_queue_2.put(data)  # 将买入单推送到队列
                        else:
                            pass  # 处理其他消息类型（可根据需要添加）

                    except json.JSONDecodeError:
                        logging.error(f"消息解析失败: {data}")

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            logging.error(f"WebSocket 连接失败: {e}. 正在重连...")
            await asyncio.sleep(5)  # 等待 5 秒后重新连接

        except Exception as e:
            logging.error(f"发生了意外错误: {e}. 正在重连...")
            await asyncio.sleep(5)  # 等待 5 秒后重新连接

# 监听并处理队列数据
async def listen_to_redis():
    logging.info("开始监听 Redis 队列...")
    while True:
        await ws_initialized_event.wait()
        try:
            if ws is not None:
                # 从 Redis 队列中获取数据
                message = redis_client.lpop("tokens")
                if message:
                    # 收到服务端的redis消息更新
                    data = json.loads(message)
                    token = data.get('address');             
                    if token not in subscriptions:
                        subscriptions[token] = time.time()
                        # 存入redis
                        #redis_client.set(f"{TOKEN_IN_SCOPE}{token}",json.dumps(data))
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
#脚本启动加载redis中
async def load_redis_data():
    logging.info("载入redis已经记录的数据")
    # SCAN 命令获取匹配的键
    cursor = 0
    while True:
        await ws_initialized_event.wait()#等待链接
        cursor, keys = redis_client.scan(cursor, match=TOKEN_IN_SCOPE+"*")
        tokens = []
        if len(keys)>0:
            for token in keys:
                str = token.replace("token:","")
                subscriptions[str] = time.time()
                logging.info(f"订阅新地址 {str} 已记录。")
                tokens.append(str)
            payload = {
                "method": "subscribeTokenTrade",
                "keys": tokens  # array of token CAs to watch
            }
            await ws.send(json.dumps(payload))
            logging.info(f"从redis中拉扫描到未订阅数据,现在订阅 {tokens}")
            tokens=[]
        if cursor == 0:
            break  # 游标为0表示扫描结束


#异步函数：从队列中获取交易者数据并处理
async def transactions_message():
    while True:
        # 从队列中获取消息并处理
        data = await message_queue_2.get()
        try:
            big_data = json.loads(data)
            #加入最后活跃时间
            if big_data['mint'] in subscriptions:
                subscriptions[big_data['mint']] = time.time()
                logging.info(f"代币 {big_data['mint']} 最后一次购买时间刷新 {subscriptions[big_data['mint']]}")
            # 检查键是否存在
            # if redis_client.exists(f"{ADDRESS_EXPIRY}{big_data['traderPublicKey']}") == 0:   #没有缓存就发出请求流程
            #     redis_client.set(f"{ADDRESS_EXPIRY}{big_data['traderPublicKey']}",big_data['traderPublicKey'],REDIS_EXPIRATION_TIME) #缓存已经请求过的地址
            #await start(session, big_data)  
            executor.submit(start, big_data)
        except Exception as e:
            logging.error(f"处理消息时出错2: {e}")

def start(item):
    response=requests.get(f"https://pro-api.solscan.io/v2.0/transaction/actions?tx={item['signature']}",headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        # 检查数据是否符合条件
        sol_bal_change = response_data.get('data',{}).get('activities',[])
        active_data = {}
        if len(sol_bal_change) == 0:#看看能不能每个活动都查到
            logging.error(f"{item['traderPublicKey']} 查询 {item['signature']} 失败")
        for value in sol_bal_change:
                if(value['name'] == "PumpFunSwap" and value['program_id'] == '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'):
                    active_data  = value.get('data',{})
                    break
        item["amount"] = active_data.get("amount_1",0)/ (10 ** 9)
        logging.info(f"用户 {item['traderPublicKey']} {item['signature']}  交易金额:{item['amount']}")
        if item["amount"] >= SINGLE_SOL:#条件一大于预设值
                check_user_transactions(item)
    else:
        logging.error(f"请求交易数据数据失败: {response.status_code} - { response.text()}")

# 异步请求用户交易记录和余额
def check_user_transactions(item):
    today = time.time()##获取今天0点的时间往前查，也就说今天的交易不算在内的最后一次买入是什么时候
    url = f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={item['traderPublicKey']}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&block_time[]=0&block_time[]={(today-86400)}&page=1&page_size=20&sort_by=block_time&sort_order=desc" 
    response= requests.get(url,headers=headers) 
    if response.status_code == 200:
        response_data =  response.json()
        data = response_data.get('data', [])
        block_time = None
        if len(data) > 0:
            for value in data:
                routers = value.get("routers",{})
                if routers:
                    routers["token1"] == "So11111111111111111111111111111111111111111"#证明是买入
                    block_time = value['block_time']
                
        if block_time:# 查找今天除外的买入记录，第一条查看他的区块链时间并且大于设定值
            day_diff = (time.time() - block_time) / 86400
            logging.info(f"两笔交易的时间差 {day_diff} 天")
            if  day_diff >= DAY_NUM:
                logging.info(f"{item['traderPublicKey']} 在过去 {day_diff} 天内没有代币交易，突然进行了交易。")        
                # 检查用户账户余额
                check_user_balance(item)
            else:
                logging.info((f"两笔交易的时间差 {day_diff} 天"))
        else:
            logging.error(f"{item['traderPublicKey']} {item['signature']} 获取历史区块链时间失败 参数时间戳 {today} 之前并无交易数据 新钱包 ")
    else:
        logging.error(f"请求用户交易记录失败: {response.status_code} - { response.text()}")


# 异步请求用户的账户余额
def check_user_balance(item):
    try:
        logging.info(f"请求用户余额: {item['traderPublicKey']}")
        portfolio_calculator = PortfolioValueCalculator(
            balances_api_key=HELIUS_API_KEY,
            account_address=item['traderPublicKey']
        )
        total_balance = portfolio_calculator.calculate_total_value()
        sol = portfolio_calculator.get_sol()
        logging.info(f"用户余额--{item['traderPublicKey']}--tokens:{total_balance} sol:{sol}")
        #if total_balance >= TOKEN_BALANCE or sol >= BLANCE:
        if total_balance >= TOKEN_BALANCE:
                    message = f'''
<b>🐋🐋🐋🐋鲸鱼钱包🐋🐋🐋🐋</b>

token:\n<code>{item["mint"]}</code>

购买的老钱包:\n<code>{item['traderPublicKey']}</code>

购买金额:<b>{(item['amount']):.4f} SOL</b>
钱包余额:<b>{sol} SOL</b>
钱包代币余额总计:<b> {total_balance} USDT</b>
链上查看钱包: <a href="https://solscan.io/account/{item['traderPublicKey']}"><b>SOLSCAN</b></a> <a href="https://gmgn.ai/sol/address/{item['traderPublicKey']}"><b>GMGN</b></a>
token详情:<a href="https://solscan.io/account/{item['traderPublicKey']}#defiactivities"><b>详情</b></a>

📈查看K线: <a href="https://pump.fun/coin/{item["mint"]}"><b>PUMP</b></a> <a href="https://gmgn.ai/sol/token/{item["mint"]}"><b>GMGN</b></a>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
                        '''
                    send_telegram_notification(message)
                    #保存通知过的
                    redis_client.set(f"{ADDRESS_SUCCESS}{item['traderPublicKey']}",json.dumps(item))
    except Exception as e:
            logging.error(f"获取{item['traderPublicKey']}的余额出错{e}")


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
            logging.error(f"通知发送失败: {response.json()}")
    except Exception as e:
        logging.error(f"发送通知时出错: {e}")

#请求代币元信息

def check_tokens_to_redis(token):
    url = f"https://pro-api.solscan.io/v2.0/token/meta?address={token}"
    response = requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data = response.json()
        data = response_data.get('data',{})
        market_cap = data.get('market_cap',0) or 0
        logging.info(f"token {token} market_cap {market_cap}")
        try:
            if market_cap > MAX_TOKEN_CAP:# 再范围之外移除监听
                if token in subscriptions:
                    del subscriptions[token]
                #从redis中移除范围以外的
                redis_client.delete(f"{TOKEN_IN_SCOPE}{token}")
                logging.info(f"token {token} market_cap {market_cap:.4f} 超出范围 正在移除监听")
                # 取消订阅
                if subscriptions and ws:
                    payload = {
                        "method": "unsubscribeTokenTrade",
                        "keys": [token]  
                    }
                    ws.send(json.dumps(payload))
        except Exception as e:
            logging.error(f"移除监听出错了: {token}  {e}")

    else:
        logging.error(f"{token}获取元信息失败 : {response.status_code}")


# 主程序
async def main():
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动处理队列的任务
    redis_task = asyncio.create_task(listen_to_redis())

    # 启动载入redis数据任务
    #redis_data_load = asyncio.create_task(load_redis_data())

    # 启动交易监听队列任务
    transactions_task= asyncio.create_task(transactions_message())

    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())


    # 等待任务完成
    await asyncio.gather(ws_task,redis_task,transactions_task,cleanup_task)


# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
