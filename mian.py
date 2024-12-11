###1号脚本 从WS获取数据，十分钟检查一次币种市值大于1W小于10W的踢出监听范围，在此范围内的压入2号服务器redis
import asyncio
import websockets
import json
import logging
import requests  # 用于发送 Telegram API 请求
import os
from logging.handlers import TimedRotatingFileHandler
from portfolivalueCalculator import PortfolioValueCalculator
from datetime import datetime, timedelta
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
TELEGRAM_BOT_TOKEN = '7914406898:AAHP3LuMY2R647rK3gI0qsiJp0Fw8J-aW_E'  # 线上 Telegram 机器人的 API Token
#TELEGRAM_BOT_TOKEN = '7601466837:AAHd9g8QJik3kLtjyRDq-OuYD9CcCWKAJR4'  # 测试 Telegram 机器人的 API Token

TELEGRAM_CHAT_ID = '@laojingyu'  # 线上 Telegram 用户或群组 ID
#TELEGRAM_CHAT_ID = '@solanapostalert'  # 测试 Telegram 用户或群组 ID
HELIUS_API_KEY = 'c3b599f9-2a66-494c-87da-1ac92d734bd8'#HELIUS API KEY#
# Redis 配置
REDIS_HOST = "43.153.140.171"
REDIS_PORT = 6379
REDIS_PWD = "xiaosan@2020"
REDIS_DB = 0
# 订阅过期时间设置为10分钟
SUBSCRIPTION_EXPIRY = 10 * 60
# 筛选地址活跃度为10分钟活跃
TOKEN_EXPIRY = 10 * 60
# API token 用于身份验证
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3MzMyMDIyODIyOTUsImVtYWlsIjoiY3Jhenl0aWFubEBnbWFpbC5jb20iLCJhY3Rpb24iOiJ0b2tlbi1hcGkiLCJhcGlWZXJzaW9uIjoidjIiLCJpYXQiOjE3MzMyMDIyODJ9.Vy8DY8UP6Z3i2iP8YwvLq3ohNT7CoPH4gcXx_7GY8fE"
WS_URL = "wss://pumpportal.fun/api/data"  # WebSocket 地址


ADDRESS_EXPIRY = "expiry:"#redis存放已经请求过的 地址
ADDRESS_SUCCESS = "success:"#存放播报的
REDIS_EXPIRATION_TIME = 3 * 24 * 60 * 60 #redis 缓存请求过的地址，三天之内不在请求 
# 请求头
headers = {
    "token": TOKEN
}

# 日志文件夹和文件名
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_filename = os.path.join(LOG_DIR, "client.log")

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
subscriptions = {}# 存储mint_address和时间戳
ws = None# WebSocket 连接





async def cleanup_subscriptions():
    while True:
        current_time = time.time()
        expired_addresses = []
        
        # 遍历所有订阅，检查是否超过了过期时间
        for mint_address, item in subscriptions.items():
            if current_time - item['create_time'] > SUBSCRIPTION_EXPIRY:
                expired_addresses.append(mint_address)

        # 移除过期的订阅
        for mint_address in expired_addresses:
            #将活跃度在设定值范围内的 请求查看市值
            if current_time - subscriptions[mint_address]["last_trade_time"] < TOKEN_EXPIRY:
                logging.info(f'代币 {mint_address} 已经过了设定的 {SUBSCRIPTION_EXPIRY}s 订阅存活时间 但是依然在代币设定的活跃度  {TOKEN_EXPIRY}s 范围内')
                executor.submit(check_tokens_to_redis, mint_address)
            del subscriptions[mint_address]
            logging.info(f"订阅 {mint_address} 已过期，已取消订阅。")
               
        # 取消订阅
        if subscriptions and ws:
            payload = {
                "method": "unsubscribeTokenTrade",
                "keys": expired_addresses  
            }
            await ws.send(json.dumps(payload))
        
        logging.error(f"----目前进程播报----")
        logging.error(f"----创建监听队列{message_queue_1.qsize()} 条----")
        logging.error(f"----数据处理队列{message_queue_2.qsize()} 条----")
        logging.error(f"----进程播报结束----")
        logging.info(f"目前订阅数量 {len(subscriptions)}")
        logging.info(f"本次取消数量 {len(expired_addresses)}")
        await asyncio.sleep(60)  # 每60秒检查一次

# 异步函数：处理 WebSocket
async def websocket_handler():
    global ws
    try:
        async with websockets.connect(WS_URL) as ws_instance:
            ws = ws_instance  # 这里将 WebSocket 连接存储到全局变量 ws
            # 连接成功后，发送订阅消息一次
            payload = {
                "method": "subscribeNewToken",
            }
            await ws.send(json.dumps(payload))
            logging.info("订阅请求已发送")

            # 持续接收消息并放入队列
            while True:
                data = await ws.recv()  # 等待并接收新的消息
                try:
                    message = json.loads(data)
                    # 根据消息类型选择将消息放入哪个队列
                    if "txType" in message and message['txType'] == 'create':
                        await message_queue_1.put(data)  # 识别订单创建
                    elif "txType" in message and message["txType"] == "buy":
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

# 异步函数：从队列中获取消息并处理
async def process_message():
        while True:
            # 从队列中获取消息并处理
            data= await message_queue_1.get()
            try:
                big_data = json.loads(data)
                if "mint" not in big_data:
                    continue

                mint_address = big_data["mint"]
                
                # Subscribing to trades on tokens
            # 如果该 mint_address 不在订阅列表中，进行订阅，并记录时间戳 生成最后交易时间字段
                if mint_address not in subscriptions:
                    subscriptions[mint_address] = {
                        "create_time":time.time(),#给个创建时间
                        "last_trade_time":time.time() # 记录下这个币种最后一次用户买入的时间
                    }
                    logging.info(f"订阅 {mint_address} 时间戳已记录")
                    
                payload = {
                    "method": "subscribeTokenTrade",
                    "keys": [mint_address]  # array of token CAs to watch
                }
                await ws.send(json.dumps(payload))
                

            except Exception as e:
                logging.error(f"处理消息时出错1: {e}")

#异步函数：从队列中获取交易者数据并处理
async def transactions_message():
    while True:
        # 从队列中获取消息并处理
        data = await message_queue_2.get()
        try:
            big_data = json.loads(data)
            #加入最后活跃时间
            if big_data['mint'] in subscriptions:
                subscriptions[big_data['mint']]['last_trade_time'] = time.time()
                # logging.info(f"代币 {big_data['mint']} 最后一次购买时间刷新 {subscriptions[big_data['mint']]['last_trade_time']}")
            # 检查键是否存在
            # if redis_client.exists(f"{ADDRESS_EXPIRY}{big_data['traderPublicKey']}") == 0:   #没有缓存就发出请求流程
            #     redis_client.set(f"{ADDRESS_EXPIRY}{big_data['traderPublicKey']}",big_data['traderPublicKey'],REDIS_EXPIRATION_TIME) #缓存已经请求过的地址
            # 将任务提交给线程池进行处理
            executor.submit(start, big_data)
            #await start(session, big_data)  
            
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
        #pump推送的购买地址 可能和 实际查出的购买地址不一样
        real_account =  active_data.get("account","")
        if item['traderPublicKey'] !=real_account and real_account:
            logging.error(f"pump 推送的用户为 {item['traderPublicKey']} hash查询的实际用户为 {real_account}")
            item['traderPublicKey'] = real_account
        logging.info(f"用户 {item['traderPublicKey']} {item['signature']}  交易金额:{item['amount']}")
        if item["amount"] >= SINGLE_SOL:#条件一大于预设值
                check_user_transactions(item)
    else:
        logging.error(f"请求交易数据数据失败: {response.status_code} - { response.text()}")

# 异步请求用户交易记录和余额
def check_user_transactions(item):
    try:
        now = datetime.now() #当前时间
        start_time = int((now - timedelta(days=365)).timestamp())#获取近365天的20条记录
        today = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())#今天的0点
        transactions_data =  fetch_user_transactions(start_time,now.timestamp(),item)#获取近90天内的20条交易记录
        
        if len(transactions_data)==0:
            logging.info(f"用户 {item['traderPublicKey']} 没有交易 疑似是新账号")
            return
        
        sum = 0 #计算今日内的条数
        last_time = None #存放今日之外的最后一笔交易的时间
        first_time = None #存放今日内的第一笔交易的时间
        for value in transactions_data: #有几种情况 1.用户今天只交易了一条没有以往的数据 first_time有值 last_time 是none  sum <= 10 2.用户今日数据超标 first有值 last_time 是none sum > 10 3.今日用户没有交易 但是有以往的数据 first_time 是none last_time 是 有值的 sum是0
            if value['block_time'] - today > 0:#区块链时间减去今天0点的时间大于0 代表今天之内交易的
                sum=sum+1
            else:
                last_time = value['block_time'] # 当区块链时间有一个是今天以外的时间，将这个对象取出并结束循环
                break
        if sum >10:
            logging.info(f"用户 {item['traderPublicKey']} 今日交易量已经超过10条")
            return
        if not last_time:
            logging.info(f"用户 {item['traderPublicKey']} 20条以内没有今日之外的交易数据")
            return
        if not first_time:
            first_time = now.timestamp()
        time_diff = (first_time - last_time) / 86400
        logging.info(f"用户 {item['traderPublicKey']} 今日交易 {sum}笔 今日第一笔和之前最后一笔交易时间差为 {time_diff} 天")
        if time_diff >=DAY_NUM:
            check_user_balance(item)
    except Exception as e:
         print("捕捉到的异常:", e)
         print("当前作用域中的变量:", dir())  # 打印所有变量和模块名



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
    
# 查看用户一段时间的交易记录
def fetch_user_transactions(start_time,end_time,item):
    url = f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={item['traderPublicKey']}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&block_time[]={start_time}&block_time[]={end_time}&page=1&page_size=20&sort_by=block_time&sort_order=desc"
    response= requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        return response_data.get('data', [])
    return []


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
        market_cap = data.get('market_cap',0)
        if market_cap < MAX_TOKEN_CAP:
        # if data.get('address',""):
            redis_client.rpush("tokens", json.dumps(data))
            logging.info(f"{token} 已经压入redis监听池 market_cap: {market_cap:.4f}")
    else:
        logging.error(f"{token}获取元信息失败 : {response.json()}")



# 主程序
async def main():
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动处理队列的任务
    process_task = asyncio.create_task(process_message())

    # 启动交易监听队列任务
    transactions_task= asyncio.create_task(transactions_message())

    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())

    # 等待任务完成
    await asyncio.gather(ws_task, process_task,transactions_task,cleanup_task)

# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
