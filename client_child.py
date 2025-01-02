import asyncio
import redis.client
import websockets
import json
import logging
import requests  # 用于发送 Telegram API 请求
import os
import math
from portfolivalueCalculatorJUP import PortfolioValueCalculatorJUP
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import redis
import time
import configparser
from cloudbypass import Proxy
from gmgn import gmgn
from tg_htmls import tg_message_html_1,tg_message_html_3, tg_message_html_4
# 创建配置解析器对象
config = configparser.ConfigParser()
# 读取INI文件时指定编码
with open('config.ini', 'r', encoding='utf-8') as f:
    config.read_file(f)
# 读取指定的参数
DOMAIN = config.get('SERVER', 'DOMAIN') #服务器域
SERVER_ID = config.get('SERVER', 'SERVER_ID') #本脚本ID
MAX_WORKERS = config.getint('General', 'MAX_WORKERS') #最大线程数
TELEGRAM_BOT_TOKEN = config.get('TELEGRAM', 'TELEGRAM_BOT_TOKEN')  # Telegram 机器人的 API Token 老鲸鱼
TELEGRAM_CHAT_ID = config.get('TELEGRAM', 'TELEGRAM_CHAT_ID')  # 你的 Telegram 用户或群组 ID  老鲸鱼
TELEGRAM_BOT_TOKEN_BAOJI = config.get('TELEGRAM', 'TELEGRAM_BOT_TOKEN_BAOJI')  # Telegram 机器人的 API Token   暴击的
TELEGRAM_CHAT_ID_BAOJI = config.get('TELEGRAM', 'TELEGRAM_CHAT_ID_BAOJI')  # 你的 Telegram 用户或群组 ID 暴击的
TELEGRAM_BOT_TOKEN_15DAYS = config.get('TELEGRAM', 'TELEGRAM_BOT_TOKEN_15DAYS')  # Telegram 机器人的 API Token   15day老钱包
TELEGRAM_CHAT_ID_15DAYS = config.get('TELEGRAM', 'TELEGRAM_CHAT_ID_15DAYS')  # 你的 Telegram 用户或群组 ID 15day老钱包
REDIS_HOST = config.get('REDIS', 'REDIS_HOST') #本地
REDIS_PORT =  config.getint('REDIS', 'REDIS_PORT')
REDIS_PWD = config.get('REDIS', 'REDIS_PWD')
REDIS_DB = config.getint('REDIS', 'REDIS_DB')
REDIS_LIST = config.get('REDIS', 'REDIS_LIST')
WS_URL = config.get('General', 'WS_URL') # WebSocket 地址
# 日志文件夹和文件名
LOG_DIR = config.get('LOG', 'DIR')
LOG_NAME = config.get('LOG', 'NAME')
MINT_SUCCESS = "mint_success:"#redis存放已经播报过的盘 //1小时释放
ADDRESS_SUCCESS = "success:"#存放播报的 老鲸鱼
ADDRESS_SUCCESS_BAOJI = "success_baoji:"#存放播报的 暴击
ADDRESS_EXPIRY = "expiry:" #今日交易超限制，新账号，这种的就直接锁住
# 创建线程池执行器
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

#redis 缓存查询的 代币 dev数据 去重数据 市值数据 
MINT_SUBSCRBED = "mint_subscrbed:"#redis存放已经订阅过的地址 //去重
TXHASH_SUBSCRBED = "txhash_subscrbed:"#redis 按订单去重 原子锁
MINT_DEV_DATA = "mint_dev_data:"#缓存10秒之内的dev数据不在请求
ADDRESS_HOLDINGS_DATA = "address_holdings_data:"#用户单币盈利缓存1天
ADDRESS_TOKENS_DATA = "address_tokens_data:" #用户tokens sol 余额 缓存1小时
#2025.1.2日更新增加新播报需求
MINT_15DAYS_ADDRESS = "mint_15days_address:"
mint_15days_address = {}
# 初始化日志
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_filename = os.path.join(LOG_DIR, LOG_NAME)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()
logger.info("日志已启动")

# 初始化 Redis 连接
logger.info("初始化 Redis")
redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PWD,
    db=REDIS_DB,
    decode_responses=True
)

# 初始化 WebSocket 和代理
ws = None
ws_initialized_event = asyncio.Event()
message_queue_1 = asyncio.Queue()
message_queue_2 = asyncio.Queue()

proxy = Proxy("81689111-dat:toeargna")
proxy_expired = {"create_time": time.time(), "proxy": str(proxy.copy().set_expire(60 * 10))}

# 初始化全局变量用于订阅和价格管理
subscriptions = {}
sol_price = {"create_time": None, "price": 0}

# 初始化 gmgn API
gmgn_api = gmgn()

# 全局请求头（初始为空）
headers = {}
async def redis_get_settings():
    """监听 Redis 频道 `settings`，并处理接收到的消息"""
    try:
        pubsub = redis_client.pubsub()
        pubsub.subscribe('settings')
        pubsub.ignore_subscribe_messages = True
        logging.info('redis_task 启动，监听 settings 频道')

        while True:
            try:
                # 获取消息
                message = await asyncio.to_thread(pubsub.get_message, timeout=1)
                if message and message['type'] == 'message':
                    logging.info(f"接收到服务器推送的配置: {message['data']}")
                    data = json.loads(message['data'])
                    await fetch_config(server_id=data['id'])
            except Exception as e:
                logging.error(f"处理 Redis 消息时出错: {e}")
            await asyncio.sleep(0.1 if message else 1)

    except Exception as e:
        logging.critical(f"Redis 监听任务异常退出: {e}")
    finally:
        # 关闭资源
        if 'pubsub' in locals():
            pubsub.close()
# 获取远程配置函数
async def fetch_config(server_id = SERVER_ID):
    try:
        response = requests.get(f"{DOMAIN}/api/nodes/{server_id}")
        response.raise_for_status()  # 如果请求失败，则抛出异常
        data = response.json()['data']
        config = json.loads(data.get('settings'))
        global SOLSCAN_TOKEN,HELIUS_API_KEY,SINGLE_SOL,DAY_NUM,BLANCE,TOKEN_BALANCE,MIN_TOKEN_CAP,MAX_TOKEN_CAP,TOTAL_PROFIT,TOKEN_EXPIRY,CALL_BACK_URL,MIN_DAY_NUM
        TOKEN_EXPIRY = config.get("TOKEN_EXPIRY") * 60
        SINGLE_SOL = config.get("SINGLE_SOL")
        MIN_TOKEN_CAP = config.get("MIN_TOKEN_CAP")
        MAX_TOKEN_CAP = config.get("MAX_TOKEN_CAP")
        TOTAL_PROFIT = config.get("TOTAL_PROFIT")
        TOKEN_BALANCE = config.get("TOKEN_BALANCE")
        HELIUS_API_KEY = config.get("HELIUS_API_KEY")
        SOLSCAN_TOKEN = config.get("SOLSCAN_TOKEN")
        DAY_NUM = config.get("DAY_NUM")
        MIN_DAY_NUM = 0.625 # 虽小满足播报的单位，同时也是redis缓存释放的时间
        BLANCE = config.get("BLANCE")
        CALL_BACK_URL = config.get("CALL_BACK_URL")
        logging.info("配置加载成功")
        # 配置加载完成后创建请求头
        global headers
        headers = {
            "token": SOLSCAN_TOKEN
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"获取配置失败: {e}")
        # 可以设置默认配置或者退出程序
        exit(1)
async def get_sol_for_usdt():
    proxies = {
        "https":proxy_expired.get("proxy")
    }
    res = gmgn_api.get_gas_price_sol(proxies=proxies)
    if res.status_code == 200:
        data = res.json()['data']
        return  data.get('native_token_usd_price')
    return 0

async def cleanup_subscriptions():
    while True:
        await ws_initialized_event.wait()
        current_time = time.time()
        expired_addresses = []
        
        if current_time - proxy_expired.get("create_time") >= 60*9:
            logging.info(f"更换代理")
            proxy_expired['create_time'] = current_time
            proxy_expired['proxy'] = str(proxy.copy().set_expire(60 * 10))

        if not sol_price.get("create_time") or current_time - sol_price.get("create_time") >= 60*5:
            logging.info(f"更新SOL的价格")
            sol_price['create_time'] = current_time
            sol_price['price'] = await get_sol_for_usdt()


        # 遍历所有订阅，最后一次交易时间超时 12.31日更新 并且要低于市值设定最小值或者高于市值设定最大值
        for mint_address, data in subscriptions.items():
            market_cap_usdt = data['market_cap_sol'] * sol_price['price']
            if current_time - data['last_trade_time'] >= TOKEN_EXPIRY and (market_cap_usdt < MIN_TOKEN_CAP or market_cap_usdt >= MAX_TOKEN_CAP):
                logging.info(f"代币 {mint_address} 市值 {market_cap_usdt} 并已经超过超时阈值 {TOKEN_EXPIRY} 分钟")
                expired_addresses.append(mint_address)
        
        # 移除过期的订阅
        for mint_address in expired_addresses:
            del subscriptions[mint_address]
        
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
        logging.error(f"----创建监听队列 {message_queue_1.qsize()} 条----")
        logging.error(f"----数据处理队列 {message_queue_2.qsize()} 条----")
        logging.error(f"----数据线程占用 {len(executor._threads)} 条----")
        logging.error(f"----目前代币数量 {len(subscriptions)} 枚----")
        logging.error(f"----本次取消数量 {len(expired_addresses)} 枚----")
        logging.error(f"----当前使用代理 {proxy_expired['proxy']} ----")
        logging.error(f"----当前SOL/美刀 {sol_price['price']} ----")
        logging.error(f"----进程播报结束")
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
                payload = {
                    "method": "subscribeNewToken",
                }
                await ws.send(json.dumps(payload))
                logging.info("订阅请求已发送")
                # 持续接收消息并处理
                while True:
                    data = await ws.recv()  # 等待并接收新的消息
                    try:
                        message = json.loads(data)
                        if "txType" in message:
                            txType = message["txType"]
                            mint = message['mint']
                            if txType == 'create':
                                # 写入redis加原子锁
                                # 尝试获取锁（NX确保只有一个线程能设置）
                                # lock_acquired = redis_client.set(f"{MINT_SUBSCRBED}{mint}", REDIS_LIST, nx=True, ex=2)  # 锁5秒自动过期
                                # if lock_acquired:
                                await message_queue_1.put(message)  # 识别订单创建
                            elif txType == "buy":
                                try:
                                    amount = message['solAmount']
                                except KeyError:
                                    logging.error(f"下标solAmount {message}")
                                    amount = 0
                                #加入最后活跃时间
                                if mint in subscriptions:
                                    subscriptions[mint] = {
                                        "last_trade_time":time.time(),
                                        "market_cap_sol":message['marketCapSol']
                                    }
                                #扫描符合要求的订单
                                if amount >= 0.3: ##2025.1.2 日增加新播报需求，老钱包买单 内盘出现两个个15天以上没操作过买币卖币行为的钱包 播报出来播报符合条件的俩个钱包地址 加上ca后续有符合钱包持续播报 单笔0.3以上
                                    lock_acquired = redis_client.set(f"{TXHASH_SUBSCRBED}{message['signature']}","原子锁5秒", nx=True, ex=5)  # 锁5秒自动过期
                                    if lock_acquired:
                                        message['amount'] = amount
                                        logging.error(f"用户 {message['traderPublicKey']} {message['signature']}  交易金额:{amount}")
                                        transactions_message_no_list(message)
                                    #await message_queue_2.put(message)  # 买入单推送
                                # else:
                                #     logging.info(f"用户 {message['traderPublicKey']} {message['signature']}  交易金额:{amount} 不满足")
                            elif txType == "sell":
                                #加入最后活跃时间
                                if mint in subscriptions:
                                    subscriptions[mint] = {
                                        "last_trade_time":time.time(),
                                        "market_cap_sol":message['marketCapSol']
                                    }
                        else:
                            logging.info(f"其他数据 {message}")  
                    except json.JSONDecodeError:
                        logging.error(f"消息解析失败: {data}")

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            logging.error(f"WebSocket 连接失败: {e}. 正在重连...")
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
                if "mint" not in data:
                    logging.error(f"{data} 不存在的订阅代币")
                    continue

                mint = data["mint"]
                
                # 如果该 mint_address 不在订阅列表中，进行订阅
                if mint not in subscriptions:
                    subscriptions[mint] = {
                        "last_trade_time":time.time(),
                        "market_cap_sol":data['marketCapSol']
                    }
                    logging.info(f"订阅新代币 {mint} 已记录")                    
                    payload = {
                        "method": "subscribeTokenTrade",
                        "keys": [mint]  # array of token CAs to watch
                    }
                    await ws.send(json.dumps(payload))
                else:
                    logging.info(f"代币 {mint} 重复订阅")                
            except Exception as e:
                logging.error(f"处理消息时出错1: {e}")

#订单不走列队
def transactions_message_no_list(data):
    check = redis_client.exists(f"{ADDRESS_EXPIRY}{data['traderPublicKey']}")
    if not check: #排除了那些频繁交易的 减少API输出
        if data['amount'] >= SINGLE_SOL:
            executor.submit(check_user_transactions, data)
        executor.submit(check_account_tran, data)
    else:
        logging.info(f"用户 {data['traderPublicKey']} 已被redis排除 {MIN_DAY_NUM} 天")

#异步函数：从队列中获取交易者数据并处理
# async def transactions_message():
#     while True:
#         # 从队列中获取消息并处理
#         data = await message_queue_2.get()
#         try:
#             check = redis_client.exists(f"{ADDRESS_EXPIRY}{data['traderPublicKey']}")
#             if not check: #排除了那些频繁交易的 减少API输出
#                 executor.submit(check_user_transactions, data)
#             else:
#                 logging.info(f"用户 {data['traderPublicKey']} 已被redis排除24小时")
#         except Exception as e:
#             logging.error(f"处理消息时出错2: {e}")

# def start(item):
#     response=requests.get(f"https://pro-api.solscan.io/v2.0/transaction/actions?tx={item['signature']}",headers=headers)
#     if response.status_code == 200:
#         response_data =  response.json()
#         # 检查数据是否符合条件
#         sol_bal_change = response_data.get('data',{}).get('activities',[])
#         active_data = {}
#         if len(sol_bal_change) == 0:#看看能不能每个活动都查到
#             logging.error(f"{item['traderPublicKey']} 查询 {item['signature']} 失败")
#         for value in sol_bal_change:
#                 if(value['name'] == "PumpFunSwap" and value['program_id'] == '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'):
#                     active_data  = value.get('data',{})
#                     break
#         item["amount"] = active_data.get("amount_1",0)/ (10 ** 9)
#         real_account =  active_data.get("account","")
#         if item['traderPublicKey'] !=real_account and real_account:
#             logging.error(f"pump 推送的用户为 {item['traderPublicKey']} tx查询的实际用户为 {real_account}")
#             item['traderPublicKey'] = real_account
#         logging.info(f"用户 {item['traderPublicKey']} {item['signature']}  交易金额:{item['amount']}")
#         if item["amount"] >= SINGLE_SOL:#条件一大于预设值
#                 check_user_transactions(item)
#     else:
#         logging.error(f"请求交易数据数据失败: {response.status_code} - { response.text()}")


#新版更新老钱包买单查看用户历史的买入记录
def check_account_tran(item):
    '''
        #2025.1.2 日增加新播报需求，老钱包买单 内盘出现两个个15天以上没操作过买币卖币行为的钱包 播报出来播报符合条件的俩个钱包地址 加上ca后续有符合钱包持续播报 单笔0.3以上
    '''
    now = datetime.now() #当前时间
    start_time = int((now - timedelta(days=365)).timestamp())#获取近365天的20条记录
    transactions_data =  fetch_user_transactions(start_time,now.timestamp(),item)#获取近365天内的20条交易记录

    if len(transactions_data)==0:
        logging.info(f"用户 {item['traderPublicKey']} 没有交易 疑似是新账号（15天钱包的方法）")
        return
    block_time = datetime.fromtimestamp(transactions_data[0]['block_time'])
    time_diff = (now - block_time).days
    if time_diff >=15:
        logging.info(f"代币 {item['mint']} 发现了15天钱包 {item['traderPublicKey']}")
        mint = item['mint']
        mint_15days_address.setdefault(mint,[]).append(item['traderPublicKey'])
        redis_client.set(f"{MINT_15DAYS_ADDRESS}{item['mint']}",json.dumps(mint_15days_address[mint]),ex=86400)
        item['market_cap'] = item['marketCapSol'] * sol_price['price'] #市值
        length = len(mint_15days_address[mint])
        item['traderPublicKeyOld'] = mint_15days_address[mint][length-2]
        item['title'] = "15天钱包"
        send_telegram_notification(tg_message_html_4(item),[TELEGRAM_BOT_TOKEN_15DAYS,TELEGRAM_CHAT_ID_15DAYS],f"代币 {mint} 15天钱包")

    

# 异步请求用户交易记录和余额
def check_user_transactions(item):
    '''
        老鲸鱼3种情况：
        1.今日第一笔交易和前一次交易要间隔24小时,中间不能出现任何交易单--1天老鲸鱼
        2.今日第一笔交易和前一次交易要间隔48小时,中间的买入单要在5单一下--2天老鲸鱼
        3.今日第一笔交易和前一次交易要间隔72小时，中间买入单要在5单以下---3天老鲸鱼

        老鲸鱼暴击：
        1.单次买入0.5以上，tokens余额再1W以上，总营收超过1w美金以上
    '''
    try:
        now = datetime.now() #当前时间
        start_time = int((now - timedelta(days=365)).timestamp())#获取近365天的20条记录
        today = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())#今天的0点
        transactions_data =  fetch_user_transactions(start_time,now.timestamp(),item)#获取近365天内的20条交易记录

        if len(transactions_data)==0:
            logging.info(f"用户 {item['traderPublicKey']} 没有交易 疑似是新账号")
            return
        sum = 0 #计算今日内的买入条数
        last_time = None #存放今日之外的最后一笔交易的时间
        first_time = now.timestamp() #这次交易的时间
        for value in transactions_data: #有几种情况 1.用户今天只交易了一条没有以往的数据 first_time有值 last_time 是none  sum <= 10 2.用户今日数据超标 first有值 last_time 是none sum > 10 3.今日用户没有交易 但是有以往的数据 first_time 是none last_time 是 有值的 sum是0
            if value['block_time'] - today > 0:#区块链时间减去今天0点的时间大于0 代表今天之内交易的
                routers = value.get('routers',{})   #token1 的值 1.sol原生代币 2.sol的原始币 3.usdc
                if routers and "token1" in routers and (routers['token1'] =="So11111111111111111111111111111111111111112" or routers['token1'] =="So11111111111111111111111111111111111111111" or routers['token1'] == 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'): #只计算买入 
                    sum=sum+1
            else:
                last_time = value['block_time'] # 当区块链时间有一个是今天以外的时间，将这个对象取出并结束循环
                break
        if sum > 5:#前面只能出现4条买入，加上自己就是第五条
            #redis 记录大于5条的用户
            redis_client.set(f"{ADDRESS_EXPIRY}{item['traderPublicKey']}","当日大于5条交易",nx=True,ex=int(86400 * MIN_DAY_NUM))
            logging.info(f"用户 {item['traderPublicKey']} 今日交易买入量已超5条")
            return
        if not last_time:
            #redis 记录新用户
            redis_client.set(f"{ADDRESS_EXPIRY}{item['traderPublicKey']}","新账号",nx=True,ex=int(86400 * MIN_DAY_NUM))
            logging.info(f"用户 {item['traderPublicKey']} 没有今日之外的交易数据")
            return
        time_diff = (first_time - last_time) / 86400
        logging.info(f"用户 {item['traderPublicKey']} 今日买入 {sum}笔 今日第一笔和之前最后一笔交易时间差为 {time_diff} 天")

        if fetch_mint_dev(item):##符合条件就是 诈骗盘 条件：老鲸鱼是dev团队中人 dev和dev小号，加起来超过10个sol
            return
        #走播报
        logging.info(f"代币 {item['mint']} dev检测合格")
        with ThreadPoolExecutor(max_workers=20) as nested_executor:  
            if time_diff>=DAY_NUM:#两天以上老鲸鱼 老鲸鱼暴击
                nested_executor.submit(check_user_balance, item,f"老鲸鱼")  #老鲸鱼
                nested_executor.submit(check_user_wallet, item,f"老鲸鱼暴击")  #老鲸鱼暴击
            elif time_diff>=MIN_DAY_NUM and  sum == 0:#一天以上老鲸鱼 老鲸鱼暴击 改成了15小时就报               
                nested_executor.submit(check_user_balance, item,f"老鲸鱼")  #老鲸鱼
                nested_executor.submit(check_user_wallet, item,f"老鲸鱼暴击")  #老鲸鱼暴击
    except Exception as e:
         logging.error("用户交易记录的异常:", e)
# 请求用户的账户余额并通知 老鲸鱼播报
def check_user_balance(item,title):
    try:
        data = fetch_user_tokens(item['traderPublicKey'])
        total_balance = data.get('total_balance')
        sol = data.get('sol')
        logging.info(f"用户 {item['traderPublicKey']} tokens:{total_balance} sol:{sol}")
        #if total_balance >= TOKEN_BALANCE or sol >= BLANCE:
        if total_balance >= TOKEN_BALANCE:
            #先通知交易端 #老鲸鱼
            if check_redis_key(item):
                send_to_trader(item['mint'],1)
                item['title'] = title
                item['sol'] = sol
                item['total_balance'] = total_balance
                send_telegram_notification(tg_message_html_1(item),[TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID],f"用户 {item['traderPublicKey']} {title}")
                #保存通知过的
                redis_client.set(f"{ADDRESS_SUCCESS}{item['traderPublicKey']}",json.dumps(item))
            else:
                logging.info(f"代币 {item['mint']} 已经通知过了")
    except Exception as e:
            logging.error(f"获取 {item['traderPublicKey']} 的余额出错 {e}")
# 请求用户的卖出单 老金鱼暴击
def check_user_wallet(item,title):
    logging.info(f"用户 {item['traderPublicKey']} 请求老鲸鱼暴击 {item['mint']}")
    try:
        data = fetch_user_wallet_holdings(item['traderPublicKey'])
        if not data:
            logging.info(f"用户 {item['traderPublicKey']} 代币盈亏data是空")
            return
        holdings = data.get('holdings',[])
        if not holdings:
            logging.info(f"用户 {item['traderPublicKey']} 代币盈亏holdings是空")
            return 
        hold_data = holdings[0]
        if float(hold_data['realized_profit']) < TOTAL_PROFIT:
            logging.info(f"用户{item['traderPublicKey']} 单笔最大盈利(已结算) {hold_data['realized_profit']} usdt 小于设定值 {TOTAL_PROFIT}")
            return
        #获取余额
        if (item['marketCapSol'] * sol_price['price']) < MIN_TOKEN_CAP:#老鲸鱼暴击的条件 小于设定的市值时 
            logging.error(f"代币 {item['mint']} 的市值 {item['marketCapSol']} 设定 {MIN_TOKEN_CAP} 不满足")
            balance_data = fetch_user_account_sol(item['traderPublicKey'])
            sol = balance_data.get('sol')
            if sol < BLANCE:
                logging.error(f"用户 {item['traderPublicKey']} 余额 sol {sol} 设定 {BLANCE} 不满足")
                data = fetch_user_tokens(item['traderPublicKey'])
                total_balance = data.get('total_balance')
                if total_balance < TOKEN_BALANCE:
                    logging.error(f"用户 {item['traderPublicKey']} tokens 余额 {total_balance} 设定 {TOKEN_BALANCE} 不满足")
                    return
        if check_redis_key(item):
            send_to_trader(item['mint'],2)
            hold_data["traderPublicKey"] = item['traderPublicKey']
            hold_data["title"] = title
            hold_data['mint'] = item['mint']
            hold_data['amount'] = item['amount']
            hold_data['signature'] = item['signature']
            hold_data['market_cap'] = item['marketCapSol'] * sol_price['price'] #市值
            send_telegram_notification(tg_message_html_3(hold_data),[TELEGRAM_BOT_TOKEN_BAOJI,TELEGRAM_CHAT_ID_BAOJI],f"用户 {item['traderPublicKey']} {title}")
            # #保存通知过的
            redis_client.set(f"{ADDRESS_SUCCESS_BAOJI}{item['traderPublicKey']}",json.dumps(hold_data))
        else:
            logging.info(f"代币 {item['mint']} 已经通知过了")
    except Exception as e:
        logging.error("捕捉到的异常:", e)      
# 查看用户一段时间的交易记录
def fetch_user_transactions(start_time,end_time,item):
    url = f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={item['traderPublicKey']}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&block_time[]={start_time}&block_time[]={end_time}&page=1&page_size=20&sort_by=block_time&sort_order=desc"
    response= requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        return response_data.get('data', [])
    return []
# 发送 Telegram 消息
def send_telegram_notification(message,bot,tag):
    url = f"https://api.telegram.org/bot{bot[0]}/sendMessage"
    payload = {
        "chat_id": bot[1],
        "text": message,
        "parse_mode": "HTML"  # 设置为 HTML 格式
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            
            logging.info(f"{tag} 通知发送成功！")
        else:
            logging.error(f"{tag} 通知发送失败: {response.json()}")
    except Exception as e:
        logging.error(f"{tag} 发送通知时出错: {e}")
#请求用户的总营收
def fetch_user_total_profit(address):
    proxies = {
        "https":proxy_expired.get("proxy")
    }
    res = gmgn_api.getWalletInfo(walletAddress=address,period="7d",proxies=proxies)
    if res.status_code == 200:
        return res.json()['data']
    logging.error(f"用户 {address} 获取总营收失败 {res.text}")
    return {}
#请求用户的代币盈亏情况 之请求一条，按降序排列，这一条就是金额最大的
def fetch_user_wallet_holdings(address):
    data = redis_client.get(f"{ADDRESS_HOLDINGS_DATA}{address}")

    if data:
        logging.info(f"用户 {address} 取出代币盈利缓存")
        return json.loads(data)
    else:
        proxies = {
            "https":proxy_expired.get("proxy")
        }
        res = gmgn_api.getWalletHoldings(walletAddress=address,params="limit=1&orderby=realized_profit&direction=desc&showsmall=true&sellout=true&tx30d=true",proxies=proxies)
        if res.status_code == 200:
            data = res.json()['data']
            logging.info(f"用户 {address} 代币盈利已缓存")
            redis_client.set(f"{ADDRESS_HOLDINGS_DATA}{address}",json.dumps(data),ex=int(86400 * MIN_DAY_NUM))
            return data
        else:
            logging.error(f"用户 {address} 获取代币盈亏失败 {res.text}")
    return {}
#请求代币token的dev情况
def fetch_mint_dev(item):
    mint = item['mint']
    traderPublicKey = item['traderPublicKey']
    res = redis_client.get(f"{MINT_DEV_DATA}{mint}")
    data=[]
    if res:
        data = json.loads(res)
        logging.info(f"代币 {mint} 取出dev缓存")
    else:
        proxies = {
            "https":proxy_expired.get("proxy")
        }
        res = gmgn_api.getTokenTrades(token=mint,params="limit=20&event=buy&maker=&tag[]=dev_team",proxies=proxies)
        if res.status_code == 200:
            data =  res.json()['data']['history']
            logging.info(f"代币 {mint} dev已缓存")
            redis_client.set(f"{MINT_DEV_DATA}{mint}",json.dumps(data),ex=10)
        else:
            logging.error(f"代币 {mint} 获取dev情况失败 {res.text}")
    for value in data:
        if "creator" in value['maker_token_tags'] and value['maker'] == traderPublicKey:
            logging.error(f"用户 {traderPublicKey} 是代币 {mint} 的创建者")
            return True
    sols = sum(record["quote_amount"] for record in data)
    if sols>=10:
        logging.error(f"代币 {mint} dev团队持仓 {sols} sol超过设置值")
        return True
    return False
#请求用户的token和sol总和
def fetch_user_tokens(address):
    data = redis_client.get(f"{ADDRESS_TOKENS_DATA}{address}")
    if data and "total_balance" in data:
        logging.info(f"用户 {address} 取出tokens sol 缓存")
        return json.loads(data)
    portfolio_calculator = PortfolioValueCalculatorJUP(
        balances_api_key=HELIUS_API_KEY,
        account_address=address
    )
    data = {"total_balance":portfolio_calculator.calculate_total_value(),"sol":portfolio_calculator.get_sol()}
    logging.info(f"用户 {address} tokens sol 已缓存")
    redis_client.set(f"{ADDRESS_TOKENS_DATA}{address}",json.dumps(data),ex=3600)
    return data
#单独的sol取出接口
def fetch_user_account_sol(address):
    data = redis_client.get(f"{ADDRESS_TOKENS_DATA}{address}")
    account_data = json.loads(data)
    if account_data and "sol" in account_data:
        logging.info(f"用户 {address} sol 缓存")
        return account_data  
    response = requests.get(f"https://pro-api.solscan.io/v2.0/account/detail?address={address}", headers=headers)
    if response.status_code == 200:
        response_data =  response.json().get('data')
        data = {"sol":response_data.get('lamports') / 10**9}
        redis_client.set(f"{ADDRESS_TOKENS_DATA}{address}",json.dumps(data),ex=3600)
        logging.info(f"用户 {address}  sol 余额已缓存")
        return data
    logging.info(f"用户 {address}  solana 余额接口调用失败了")
    return {"sol":0}
#通知交易端
def send_to_trader(mint,type):
    if not CALL_BACK_URL:
        logging.info(f"回调地址没有填写")
        return 
    try:
        params = {
            'ca': mint,
            'type_id': type
        }     
        # 设置 headers，确保发送的内容类型为 JSON
        headers = {'Content-Type': 'application/json'}
        # 使用 json= 参数，requests 会自动处理将字典转换为 JSON 格式并设置 Content-Type
        response = requests.post(CALL_BACK_URL, json=params, headers=headers)  # 设置超时为 10 秒
        logging.info(f"代币 {mint} 已经发送到交易端")
        # 如果响应状态码不是 200，会抛出异常
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.info(f"代币 {mint} 发送交易失败")
#查看是mint是否已经播报过了
def check_redis_key(item):
    return redis_client.set(f"{MINT_SUCCESS}{item['mint']}", json.dumps(item), nx=True, ex=int(86400 * MIN_DAY_NUM))
# 主程序
async def main():
    # 启动 WebSocket 连接处理
    redis_task = asyncio.create_task(redis_get_settings())
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动处理队列的任务
    process_task = asyncio.create_task(process_message())
    
    # 启动交易监听队列任务
    # transactions_task= asyncio.create_task(transactions_message())

    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())

    # 读取配置
    await fetch_config()
    # 等待任务完成
    await asyncio.gather(ws_task,process_task,cleanup_task,redis_task)
    
# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
