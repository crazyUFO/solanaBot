import asyncio
import websockets
import json
import logging
import requests  # 用于发送 Telegram API 请求
import os
import math
from portfolivalueCalculatorJUP import PortfolioValueCalculatorJUP
from datetime import datetime, timedelta,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
import redis
import time
import configparser
from cloudbypass import Proxy
from gmgn import gmgn
from serverFun import ServerFun
from tg_htmls import tg_message_html_1,tg_message_html_3, tg_message_html_4, tg_message_html_5
from utils import flatten_dict,check_historical_frequency,check_historical_frequency2,is_chinese

from zoneinfo import ZoneInfo
from logging.handlers import TimedRotatingFileHandler
import copy
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
TELEGRAM_BOT_TOKEN_ZHUANZHANG = config.get('TELEGRAM', 'TELEGRAM_BOT_TOKEN_ZHUANZHANG')  # Telegram 机器人的 API Token   老钱包转账
TELEGRAM_CHAT_ID_ZHUANZHANG = config.get('TELEGRAM', 'TELEGRAM_CHAT_ID_ZHUANZHANG')  # 你的 Telegram 用户或群组 ID 老钱包转账
REDIS_HOST = config.get('REDIS', 'REDIS_HOST') #本地
REDIS_PORT =  config.getint('REDIS', 'REDIS_PORT')
REDIS_PWD = config.get('REDIS', 'REDIS_PWD')
REDIS_DB = config.getint('REDIS', 'REDIS_DB')
WS_URL = config.get('General', 'WS_URL') # WebSocket 地址
# 日志文件夹和文件名
LOG_DIR = config.get('LOG', 'DIR')
LOG_NAME = config.get('LOG', 'NAME')
MINT_SUCCESS = "mint_success:"#redis存放已经发送到交易的盘
ADDRESS_SUCCESS = "success:"#存放播报过的 success:mint地址/type类型 1 2 3 4
ADDRESS_EXPIRY = "expiry:" #今日交易超限制，新账号，这种的就直接锁住
# 创建线程池执行器
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

#redis 缓存查询的 代币 dev数据 去重数据 市值数据
MINT_SUBSCRBED = "mint_subscrbed:"#redis存放已经订阅过的地址 //去重
TXHASH_SUBSCRBED = "txhash_subscrbed:"#redis 按订单去重 原子锁
MINT_DEV_DATA = "mint_dev_data:"#缓存10秒之内的dev数据不在请求
ADDRESS_HOLDINGS_DATA = "address_holdings_data:"#用户单币盈利缓存1天
ADDRESS_HOLDINGS_ALERT_DATA = "address_holdings_alert_data:"#用户最近活跃 ##分析感叹号数量
ADDRESS_TOKENS_DATA = "address_tokens_data:" #用户tokens sol 余额 缓存1小时
MINT_POOL_DATA = "mint_pool_data:"#代币流动性缓存10秒
WALLET_INFOS = "wallet_infos:"#钱包详情的缓存
#2025.1.2日更新增加新播报需求
MINT_15DAYS_ADDRESS = "mint_15days_address:"
MINT_ZHUANZHANG_ADDRESS = "mint_zhuanzhang_address:"
#2025.1.27日更新跨度扫描 的全局订单
MINT_ODDERS = "mint_odders"
SYMBOL_UNIQUE = "symbol_unique:" #重复名字的去重
#2025.1.16更新 缓存所有发送到后台里的 代币 需要更新最高市值用到
MINT_NEED_UPDATE_MAKET_CAP = "mint_need_update_maket_cap:"
MINT_NEED_UPDATE_MAKET_CAP_LOCKED = "mint_need_update_maket_cap_locked"#因为多台服务器的原因，每次只有一台服务器进入更新
mint_15days_address = {}
exchange_wallets = [] #拉黑的交易所地址，从服务器获取
user_wallets = []#拉黑的钱包地址
#1.21号更新，客户端公平消费机制
CLIENT_MQ_LIST = "client_mq_list" #客户端队列
CLIENT_ID = config.get('REDIS', 'REDIS_LIST_CLIENT_ID') #客户端id
TXHASH_MQ_LIST = "txhash_mq_list" #去重过后的ws拿到的订单数据
CLIENT = "client:" #客户端相关的，包括计数，各个客户端的最后消费时间，客户端队列，消费订单队列
# 初始化日志目录
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_filename = os.path.join(LOG_DIR, LOG_NAME)

# 创建一个定时滚动日志处理器
handler = TimedRotatingFileHandler(
    log_filename,  # 日志文件的路径
    when="midnight",  # 每天午夜生成新日志
    interval=1,  # 每天滚动一次
    backupCount=2,  # 保留最近的3天日志（包括今天的）
    encoding="utf-8"  # 设置日志文件编码为UTF-8
)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 配置根日志
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        handler,  # 使用定时滚动日志处理器
        logging.StreamHandler()  # 控制台输出日志
    ]
)

# 获取日志记录器
logger = logging.getLogger()
logger.info("日志已启动")

# 初始化 Redis 连接
logger.info("初始化 Redis 连接池")
redis_pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT,password=REDIS_PWD, db=REDIS_DB,decode_responses=True, max_connections=MAX_WORKERS)

# 初始化 WebSocket 和代理
ws = None
ws_initialized_event = asyncio.Event()
subscribed_new_mq_list = asyncio.Queue()
market_cap_sol_height_update_mq_list = asyncio.Queue()

proxy = Proxy("81689111-dat:toeargna")
proxy_expired = {"create_time": time.time(), "proxy": str(proxy.copy().set_expire(60 * 10))}

# 初始化全局变量用于订阅和价格管理
subscriptions = {}
sol_price = {"create_time": None, "price": 0}

# 初始化 gmgn API
gmgn_api = gmgn()
# 初始化 服务器API
server_fun_api = ServerFun(domain = DOMAIN)
# 全局请求头（初始为空）
headers = {}
async def redis_get_settings():
    """监听 Redis 频道 `settings`，并处理接收到的消息"""
    try:
        pubsub = redis_client().pubsub()
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
    global headers
    global SOLSCAN_TOKEN, HELIUS_API_KEY, PURCHASE_AMOUNT, DAY_INTERVAL,REDIS_EX_TIME,MIN_PURCHASE_AMOUNT,WIN_RATE
    global MIN_MARKET_CAP, MAX_MARKET_CAP, DEV_TEAM_SOL_WITH_SUB, DEV_TEAM_SOL_WITHOUT_SUB
    global BLACKLIST_RATIO, PROFIT_7D, WIN_RATE_7D, BUY_FREQUENCY
    global REMOVE_DUPLICATES_BY_NAME, REMOVE_CHINESE_BY_NAME, SUBSCRIPTION_CYCLE
    global TRANSACTION_ADDRESS_GROUP, SPREAD_DETECTION_SETTINGS_ENABLED
    global SPREAD_DETECTION_SETTINGS_SPREAD, SPREAD_DETECTION_SETTINGS_ALLOWED_OCCURRENCES
    global SPREAD_DETECTION_SETTINGS_MAX_COUNT, TYPE1_SETTINGS_TRANSACTION_ENABLED
    global TYPE1_SETTINGS_PURCHASE_AMOUNT, TYPE1_SETTINGS_DAY_INTERVAL, TYPE1_SETTINGS_MARKET_CAP_LIMIT
    global TYPE1_SETTINGS_SOL_LIMIT, TYPE1_SETTINGS_TOKEN_BALANCE, TYPE2_SETTINGS_TRANSACTION_ENABLED
    global TYPE2_SETTINGS_PURCHASE_AMOUNT, TYPE2_SETTINGS_DAY_INTERVAL, TYPE2_SETTINGS_MARKET_CAP_LIMIT
    global TYPE2_SETTINGS_PROFIT_PER_TOKEN, TYPE2_SETTINGS_PROFIT_RATE_PER_TOKEN, TYPE3_SETTINGS_TRANSACTION_ENABLED
    global TYPE3_SETTINGS_DAY_INTERVAL, TYPE4_SETTINGS_TRANSACTION_ENABLED, TYPE4_SETTINGS_DAY_INTERVAL
    global TYPE4_SETTINGS_PARENT_WALLET_TRANSFER_SOL, TYPE4_SETTINGS_TOKEN_QUANTITY, TYPE4_SETTINGS_TOKEN_BALANCE
    global SPREAD_DETECTION_SETTINGS_AMOUNT_RANGE_MIN, SPREAD_DETECTION_SETTINGS_AMOUNT_RANGE_MAX
    global TYPE3_SETTINGS_PURCHASE_AMOUNT, TYPE4_SETTINGS_PURCHASE_AMOUNT, ALLOWED_TRAN_TYPES,TYPE4_SETTINGS_PARENT_WALLET_TRANSACTION_RANGE
    global SPREAD_DETECTION_SETTINGS_ENABLED_TWO,SPREAD_DETECTION_SETTINGS_SPREAD_TWO,SPREAD_DETECTION_SETTINGS_AMOUNT_RANGE_TWO,SPREAD_DETECTION_SETTINGS_MAX_COUNT_TWO
    #全局设置
    REDIS_EX_TIME = None #从服务器拿到四个类型的周期数据，取最短的那个作为时间周期
    MIN_PURCHASE_AMOUNT = None #从服务器拿到四个类型的单笔购买数据，取最少得那个
    SOLSCAN_TOKEN = None #solscan token
    HELIUS_API_KEY = None # helius api token
    PURCHASE_AMOUNT = None # 单笔购买
    DAY_INTERVAL = None # 间隔时间
    MIN_MARKET_CAP = None #最小市值
    MAX_MARKET_CAP = None #最大市值
    DEV_TEAM_SOL_WITH_SUB = None # dev有小号 sol
    DEV_TEAM_SOL_WITHOUT_SUB = None #dev没小号sol
    BLACKLIST_RATIO = None #黑盘比例
    PROFIT_7D = None #七天盈利额度
    WIN_RATE = None#总胜率
    WIN_RATE_7D = None #七天盈利率
    BUY_FREQUENCY = None #七天购买频率
    REMOVE_DUPLICATES_BY_NAME = None # 移除同名
    REMOVE_CHINESE_BY_NAME = None #移除中文名
    SUBSCRIPTION_CYCLE = None # 订阅周期
    TRANSACTION_ADDRESS_GROUP = None #交易地址组
    ALLOWED_TRAN_TYPES = None # 允许交易的类型
    SPREAD_DETECTION_SETTINGS_ENABLED = None # 跨度开关
    SPREAD_DETECTION_SETTINGS_SPREAD = None # 跨度
    SPREAD_DETECTION_SETTINGS_ALLOWED_OCCURRENCES = None #允许出现的次数
    SPREAD_DETECTION_SETTINGS_AMOUNT_RANGE_MIN = None # 金额范围最小
    SPREAD_DETECTION_SETTINGS_AMOUNT_RANGE_MAX = None #金额范围最大
    SPREAD_DETECTION_SETTINGS_MAX_COUNT = None # 允许出现的次数计次
    #跨度检测二挡
    SPREAD_DETECTION_SETTINGS_ENABLED_TWO = None
    SPREAD_DETECTION_SETTINGS_SPREAD_TWO = None
    SPREAD_DETECTION_SETTINGS_AMOUNT_RANGE_TWO = None
    SPREAD_DETECTION_SETTINGS_MAX_COUNT_TWO = None
    #类型一设置
    TYPE1_SETTINGS_TRANSACTION_ENABLED = None #交易开关
    TYPE1_SETTINGS_PURCHASE_AMOUNT = None#单独设置购买金额
    TYPE1_SETTINGS_DAY_INTERVAL = None # 单独设置间隔时间
    TYPE1_SETTINGS_MARKET_CAP_LIMIT = None #最小市值
    TYPE1_SETTINGS_SOL_LIMIT = None # sol的余额
    TYPE1_SETTINGS_TOKEN_BALANCE = None # tokens 余额
    #类型二设置
    TYPE2_SETTINGS_TRANSACTION_ENABLED = None #交易开关
    TYPE2_SETTINGS_PURCHASE_AMOUNT = None #单独设置购买
    TYPE2_SETTINGS_DAY_INTERVAL = None #单独设置间隔时间
    TYPE2_SETTINGS_MARKET_CAP_LIMIT = None #最小市值
    TYPE2_SETTINGS_PROFIT_PER_TOKEN = None #单币盈利
    TYPE2_SETTINGS_PROFIT_RATE_PER_TOKEN = None #单币盈利率
    #类型三设置
    TYPE3_SETTINGS_TRANSACTION_ENABLED = None #交易开关
    TYPE3_SETTINGS_PURCHASE_AMOUNT = None #单独设置购买金额
    TYPE3_SETTINGS_DAY_INTERVAL = None #单独设置间隔时间
    #类型四设置
    TYPE4_SETTINGS_TRANSACTION_ENABLED = None #交易开关
    TYPE4_SETTINGS_PURCHASE_AMOUNT = None #单独设置交易金额
    TYPE4_SETTINGS_DAY_INTERVAL = None #单独设置间隔时间
    TYPE4_SETTINGS_PARENT_WALLET_TRANSACTION_RANGE = None #交易记录查询范围
    TYPE4_SETTINGS_PARENT_WALLET_TRANSFER_SOL = None # 父钱包转账sol
    TYPE4_SETTINGS_TOKEN_QUANTITY = None #账户代币数
    TYPE4_SETTINGS_TOKEN_BALANCE = None #代币余额

    
    response = server_fun_api.getConfigById(server_id=server_id)
    if response.status_code == 200:
        data = response.json()['data']
        config = json.loads(data.get('settings'))
        allowed_tran_types = []
        #提取交易类型
        if config.get("spread_detection_settings_enabled"):
            # 获取 amount_range 并解析 min 和 max
            amount_range = config.get("spread_detection_settings_amount_range")
            min_val, max_val = map(float, amount_range.split('-'))
            config['spread_detection_settings_amount_range_min'] = min_val
            config['spread_detection_settings_amount_range_max'] = max_val
        #允许交易的 和 没有单独设置单笔购买和时间跨度的
        for i in range(1, 5):
            if not config.get(f"type{i}_settings_purchase_amount"):
                config[f"type{i}_settings_purchase_amount"] = config["purchase_amount"]
            if config.get(f"type{i}_settings_transaction_enabled"):
                allowed_tran_types.append(i)
        config['allowed_tran_types'] = allowed_tran_types
        url = config.get('transaction_address_group')
        config['transaction_address_group'] = url.replace(" ", "").split("\n") if url else []
        #订阅周期秒化
        config['subscription_cycle'] = config['subscription_cycle'] * 60
        #设定单子的最少时间过期
        config['redis_ex_time'] = min(config['type1_settings_day_interval'],config['type2_settings_day_interval'],config['type3_settings_day_interval'],config['type4_settings_day_interval'])
        #设置单子的最小排除单笔购买
        config['min_purchase_amount'] = min(config['type1_settings_purchase_amount'],config['type2_settings_purchase_amount'],config['type3_settings_purchase_amount'],config['type4_settings_purchase_amount'])
        config = flatten_dict(config)
        #把confg中的所有key初始化到全局变量
        globals().update(config)
        headers = {
            "token":SOLSCAN_TOKEN
        }
    else:
        logging.error(f"获取配置失败: {response.text}")
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
    r = redis_client()
    while True:
        await ws_initialized_event.wait()
        current_time = time.time()
        expired_addresses = []
        
        if current_time - proxy_expired.get("create_time") >= 60*9:
            logging.info(f"更换代理")
            proxy_expired['create_time'] = current_time
            proxy_expired['proxy'] = str(proxy.copy().set_expire(60 * 10))

        # if not sol_price.get("create_time") or current_time - sol_price.get("create_time") >= 60*5:
        sol_price['create_time'] = current_time
        sol_price['price'] = await get_sol_for_usdt()
        logging.info(f"更新SOL的价格 {sol_price['price']} usd")
        #获取拉黑的地址
        fetch_black_wallets()
        # 遍历所有订阅，最后一次交易时间超时 12.31日更新 并且要低于市值设定最小值或者高于市值设定最大值
        for mint_address, data in subscriptions.items():            
            market_cap_usdt = data['market_cap_sol'] * sol_price['price']
            if current_time - data['last_trade_time'] >= SUBSCRIPTION_CYCLE and (market_cap_usdt < MIN_MARKET_CAP or market_cap_usdt >= MAX_MARKET_CAP):
                logging.info(f"代币 {mint_address} 市值 {market_cap_usdt} 并已经超过超时阈值 {SUBSCRIPTION_CYCLE / 60} 分钟")
                expired_addresses.append(mint_address)
        # 移除过期的订阅
        for mint_address in expired_addresses:
            try:
                del subscriptions[mint_address]
            except Exception as e:
                logging.error(f"在移除 mint_address 报错:{e}")
            #redis里刷新最高市值的也移除一下
            r.delete(f"{MINT_NEED_UPDATE_MAKET_CAP}{mint_address}")
                   
        if ws:
        #将订阅的数组分片，以免数据过大 WS会断开
            chunks = [expired_addresses[i:i + 20] for i in range(0, len(expired_addresses), 20)]
            for chunk in chunks:
                # 
                payload = {
                    "method": "unsubscribeTokenTrade",
                    "keys": chunk  
                }
                await ws.send(json.dumps(payload))
                await asyncio.sleep(5)
        logging.error(f"----目前 {CLIENT_ID} 进程播报----")
        logging.error(f"----创建监听队列 {subscribed_new_mq_list.qsize()} 条----")
        logging.error(f"----数据处理队列 {market_cap_sol_height_update_mq_list.qsize()} 条----")
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
                r = redis_client()
                # 持续接收消息并处理
                while True:
                    data = await ws.recv()  # 等待并接收新的消息
                    try:
                        message = json.loads(data)
                        if "txType" in message:
                            txType = message["txType"]
                            mint = message['mint']
                            # 获取当前时间并转换为 ISO 8601 国内格式
                            message['create_time_utc'] = get_utc_now()
                            # 当前时间的时间戳格式
                            message['create_time_stamp'] = int(time.time() * 1000) #毫秒级
                            #计算代币美元单价
                            message['sol_price_usd'] = sol_price['price']                           
                            if txType == 'create':
                                await subscribed_new_mq_list.put(message)  # 识别订单创建
                            elif txType == "buy" and "solAmount" in message:
                                #1.24日更新，把每个mint下面的订单都记录，以便推单统计
                                set_odder_to_redis(mint,message)
                                #加入最后活跃时间
                                if mint in subscriptions:
                                    subscriptions[mint].update({
                                        "last_trade_time": time.time(),
                                        "market_cap_sol": message['marketCapSol'],
                                    })
                                    #刷新最高市值
                                    if message['marketCapSol'] > subscriptions[mint]["market_cap_sol_height"]:
                                        subscriptions[mint].update({
                                            "market_cap_sol_height":message['marketCapSol'],
                                            "market_cap_sol_height_need_update":True #需要进行更新了
                                        })
                                        #存过后台的，直接刷新市值
                                        r.set(f"{MINT_NEED_UPDATE_MAKET_CAP}{mint}",json.dumps(subscriptions[mint]),xx=True,ex=7200)
                                #扫描符合要求的订单
                                if message['solAmount'] >= MIN_PURCHASE_AMOUNT:
                                    lock_acquired = r.set(f"{TXHASH_SUBSCRBED}{message['signature']}","原子锁1秒", nx=True, ex=1)  # 锁5秒自动过期
                                    if lock_acquired:
                                        #因为是全局的，以防脚本之间订阅不相同，找不到mint
                                        message["subscriptions"] = subscriptions[mint]
                                        r.rpush(f"{CLIENT}{TXHASH_MQ_LIST}", json.dumps(message))
                            elif txType == "sell":
                                #加入最后活跃时间
                                if mint in subscriptions:
                                    subscriptions[mint].update({
                                        "last_trade_time": time.time(),
                                        "market_cap_sol": message['marketCapSol'],
                                    })
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
# 订阅新代币队列
async def subscribed_new_mq():
        while True:
            # 从队列中获取消息并处理
            data= await subscribed_new_mq_list.get()
            try:
                if "mint" not in data:
                    logging.error(f"{data} 不存在的订阅代币")
                    continue

                mint = data["mint"]
                
                # 如果该 mint_address 不在订阅列表中，进行订阅
                if mint not in subscriptions:
                    subscriptions[mint] = {
                        "mint":mint,
                        "last_trade_time":time.time(),
                        "market_cap_sol":data['marketCapSol'],
                        "market_cap_sol_height":data['marketCapSol'],#最高市值初始化
                        "symbol":data['symbol'],
                        "create_time_utc":data['create_time_utc'],
                        "market_cap_sol_height_need_update":False, #更新最高市值的flag True 就是需要更新到后端
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
                logging.error(f"订阅新代币列队出错: {e}")
async def fair_consumption():
    await ws_initialized_event.wait()

    r = redis_client()
    logging.info(f"启动客户端队列,客户端 id {CLIENT_ID}")
    # 使用 Redis 自增计数器来确保客户端ID的唯一排序分数
    rank_score = r.incr(f"{CLIENT}client_counter")
    r.zadd(f"{CLIENT}{CLIENT_MQ_LIST}", {CLIENT_ID: rank_score})

    task_count = 0  # 记录客户端处理的任务数
    update_threshold = 1  # 每处理1个任务更新一次分数
    last_task_time = time.time()  # 记录上次处理任务的时间
    max_wait_time = 5  # 设置最大等待时间（秒）
    time_out_count = 0#超时的次数
    while True:
        rank = r.zrank(f"{CLIENT}{CLIENT_MQ_LIST}", CLIENT_ID)
        if rank is not None and rank == 0:  # 排名最前面，开始消费
            logging.info(f"开始消费..")
            while True:
                product_data = r.lpop(f"{CLIENT}{TXHASH_MQ_LIST}")
                if product_data:
                    message = json.loads(product_data)
                    logging.info(f"用户 {message['traderPublicKey']} {message['signature']}  交易金额:{message['solAmount']}")
                    executor.submit(transactions_message_no_list,message)
                    task_count += 1  # 增加任务计数
                    
                    # 每处理一定数量的任务后更新分数
                    if task_count >= update_threshold:
                        rank_score = r.incr(f"{CLIENT}client_counter")
                        r.zadd(f"{CLIENT}{CLIENT_MQ_LIST}", {CLIENT_ID: rank_score})
                        task_count = 0  # 重置任务计数
                        logging.info(f"更新分数，客户端 {CLIENT_ID} 排名重新计算")

                    last_task_time = time.time()  # 更新任务处理时间
                    # 更新客户端的最后分数更新时间
                    r.hset(f"{CLIENT}{CLIENT_ID}_last_update_time", "time", time.time())
                    break
                else:
                    # 如果客户端卡住了超过最大等待时间，则更新其分数并跳出
                    if time.time() - last_task_time >= max_wait_time:
                        logging.warning(f"客户端 {CLIENT_ID} 已等待超过 {max_wait_time} 秒，强制更新分数并返回队列")
                        rank_score = r.incr(f"{CLIENT}client_counter")  # 强制更新分数
                        r.zadd(f"{CLIENT}{CLIENT_MQ_LIST}", {CLIENT_ID: rank_score})
                        # 更新客户端的最后分数更新时间
                        r.hset(f"{CLIENT}{CLIENT_ID}_last_update_time", "time", time.time())
                        last_task_time = time.time()  # 重置任务时间
                        break
                    await asyncio.sleep(0.01)

        else:
            await asyncio.sleep(0.01)
#心跳检查 客户端队列，是否有掉线的客户端
async def check_inactive_clients():
    r = redis_client()
    # 设定过期时间
    SCORE_UPDATE_THRESHOLD = 60
    while True:
        logging.info("检查客户端队列中超过 60 秒未更新分数的客户端...")
        current_time = time.time()

        # 获取客户端队列中的所有客户端
        clients = r.zrange(f"{CLIENT}{CLIENT_MQ_LIST}", 0, -1)
        for client_id in clients:
            # 获取客户端的分数
            rank_score = r.zscore(f"{CLIENT}{CLIENT_MQ_LIST}", client_id)
            if rank_score:
                # 获取客户端最后更新时间
                last_update_time = r.hget(f"{CLIENT}{client_id}_last_update_time", "time")
                if last_update_time:
                    last_update_time = float(last_update_time)
                    if current_time - last_update_time >= SCORE_UPDATE_THRESHOLD:
                        logging.warning(f"客户端 {client_id} 已超过 {SCORE_UPDATE_THRESHOLD} 秒未更新分数，移除该客户端")
                        r.zrem(f"{CLIENT}{CLIENT_MQ_LIST}", client_id)  # 移除客户端
                        r.hdel(f"{CLIENT}{client_id}_last_update_time", "time")  # 清除客户端的最后更新时间

        # 每隔 1 秒检查一次
        await asyncio.sleep(1)
#最高市值更新列队
async def market_cap_sol_height_update():
    while True:
        logging.info(f"开始最高市值更新")
        #更新最高市值到后台
        await update_maket_cap_height_value()
        logging.info(f"最高市值更新结束")
        await asyncio.sleep(300)  # 每过5分钟检查一次

#订单不走列队
def transactions_message_no_list(item):
    '''
        先排除redis中存在的
        为三种播报拿到交易记录，拿到交易记录之后，再线程分发到三种播报
    '''
    check = redis_client().exists(f"{ADDRESS_EXPIRY}{item['traderPublicKey']}")
    print(SPREAD_DETECTION_SETTINGS_ENABLED,SPREAD_DETECTION_SETTINGS_ENABLED_TWO)
    if not check:
        redis_client().set(f"{ADDRESS_EXPIRY}{item['traderPublicKey']}","周期排除",nx=True,ex=int(REDIS_EX_TIME * 86400)) #买入直接排除 进行节流
        #推单检测
        mint_odders = None
        if SPREAD_DETECTION_SETTINGS_ENABLED:
            mint_odders = json.loads(redis_client().hget(MINT_ODDERS,item['mint']))
            if not check_historical_frequency2(item['mint'],item['signature'],SPREAD_DETECTION_SETTINGS_SPREAD,1,2,mint_odders,logging):
                return
        if SPREAD_DETECTION_SETTINGS_ENABLED_TWO:
            mint_odders = json.loads(redis_client().hget(MINT_ODDERS, item['mint'])) if not mint_odders else mint_odders
            if not check_historical_frequency2(item['mint'],item['signature'],SPREAD_DETECTION_SETTINGS_SPREAD_TWO,SPREAD_DETECTION_SETTINGS_AMOUNT_RANGE_TWO,SPREAD_DETECTION_SETTINGS_MAX_COUNT_TWO,mint_odders,logging):
                return


        now = datetime.now() #当前时间
        start_time = int((now - timedelta(days=365)).timestamp())#获取近365天的20条记录
        transactions_data =  fetch_user_transactions(start_time,now.timestamp(),item)#获取近365天内的20条交易记录
        if not transactions_data:
            logging.error(f"用户 {item['traderPublicKey']} 没有交易记录")
            return 
        #多线程调用GMGN
        future_dev = executor.submit(fetch_mint_dev,item)
        future_alert = executor.submit(fetch_user_wallet_holdings_show_alert,item)
        future_wallet_info = executor.submit(fetch_wallet_info,item)
        # 等待任务完成
        dev_data = future_dev.result()
        alert_data = future_alert.result()
        #检查dev数据
        if dev_data:##符合条件就是 诈骗盘 条件：老鲸鱼是dev团队中人 dev和dev小号
            return
        #检查感叹号数据
        if alert_data and alert_data > BLACKLIST_RATIO:
            return
        #检查钱包数据
        if future_wallet_info:
            return
        #4种type都需要用到的数据
        item['alert_data'] = alert_data
        item['symbol'] = item['subscriptions']['symbol']
        item['market_cap'] = item['marketCapSol'] * sol_price['price'] #市值
        item['isSentToExchange'] = 0 #是否已经发送到交易端
        item['mint_create_time_utc'] = item['subscriptions']['create_time_utc'] #代币创建时间

        if item['solAmount'] >= TYPE1_SETTINGS_PURCHASE_AMOUNT or item['solAmount'] >= TYPE2_SETTINGS_PURCHASE_AMOUNT:#类型1 2
            data =  analyze_transaction_records(transactions_data,item,3)
            if not data:
                return 
            if data['time_diff'] >= DAY_INTERVAL:#类型1类型2满足3天以上的
                executor.submit(type1, item,f"老鲸鱼CA:{item['symbol']}")  #老鲸鱼
                executor.submit(type2, item,f"暴击CA:{item['symbol']}")  #老鲸鱼暴击
            else:
                if data['time_diff'] >=TYPE1_SETTINGS_DAY_INTERVAL and data['count'] == 0:
                    executor.submit(type1, item,f"老鲸鱼CA:{item['symbol']}")  #老鲸鱼
                if data['time_diff'] >=TYPE2_SETTINGS_DAY_INTERVAL and data['count'] == 0:
                    executor.submit(type2, item,f"暴击CA:{item['symbol']}")  #老鲸鱼
        if item['solAmount'] >= TYPE3_SETTINGS_PURCHASE_AMOUNT:
            executor.submit(type3, item,transactions_data)
        if item['solAmount'] >= TYPE4_SETTINGS_PURCHASE_AMOUNT:
            executor.submit(type4, item,transactions_data)
    else:
        logging.info(f"用户 {item['traderPublicKey']} 已被redis排除")
#新版更新老鲸鱼转账钱包
def type4(item,transactions_data):
    '''
    老鲸鱼转账钱包 
    内容 抓内盘买单（买单钱包必须是操作不频繁24小时内没操作过 买卖的再去抓上级） 
    钱包上级转账是鲸鱼钱包 至少持有两个代币 持有代币余额大于5w刀以上

    符合条件播报钱包和上级钱包 和ca  一级钱包购买大于0.3
    '''
    now = datetime.now() #当前时间
    block_time = datetime.fromtimestamp(transactions_data[0]['block_time'])
    time_diff = (now - block_time).total_seconds()
    if time_diff < TYPE4_SETTINGS_DAY_INTERVAL * 86400: 
        return
    start_time = int((now - timedelta(days=TYPE4_SETTINGS_PARENT_WALLET_TRANSACTION_RANGE)).timestamp())#获取近72小时内的转账记录
    transfer_data = fetch_user_transfer(start_time,now.timestamp(),item['traderPublicKey'])
    father_address = None
    for value in transfer_data:
        sol_amount = value['amount']/(10**value['token_decimals'])
        if sol_amount >= TYPE4_SETTINGS_PARENT_WALLET_TRANSFER_SOL and value['from_address'] not in exchange_wallets:#2个以上转账 并且不是交易所地址
            father_address = value['from_address']
            break
    if not father_address:
        return
    logging.info(f"用户 {item['traderPublicKey']} 的上级转账老钱包为 {father_address}")
    data = fetch_user_tokens(father_address)
    tokens = data.get('tokens')
    total_balance = data.get('total_balance')
    sol = data.get('sol')
    logging.info(f"老钱包 {father_address} 的数值 tokens 数量 {len(tokens)} sol {sol} total_balance {total_balance}")
    if len(tokens)>=TYPE4_SETTINGS_TOKEN_QUANTITY and total_balance >=TYPE4_SETTINGS_TOKEN_BALANCE:

        #检测 并发送到交易端
        if send_to_trader(item=item,type=4):
            item['isSentToExchange'] = 1 #是否已经发送到交易端

        #计数播报次数
        # 使用 Redis 的 incr 命令增加计数
        key = f"{MINT_ZHUANZHANG_ADDRESS}{item['mint']}:trade_count"
        redis_client().incr(key)
        trade_count = int(redis_client().get(key))

        item['total_balance'] = total_balance
        item['sol'] = sol
        item['traderPublicKeyParent'] = father_address
        item['title'] = f"第{trade_count}通知转账CA:{item['symbol']}"
        send_telegram_notification(tg_message_html_5(item),[TELEGRAM_BOT_TOKEN_ZHUANZHANG,TELEGRAM_CHAT_ID_ZHUANZHANG],f"用户 {item['traderPublicKey']} 转账老钱包",item)

        #保存播报记录
        item['type'] = 4
        save_transaction(item)
#老鲸鱼15天钱包
def type3(item, transactions_data):
    '''
        2025.1.2 日增加新播报需求，老钱包买单 内盘出现两个个15天以上没操作过买币卖币行为的钱包 播报出来播报符合条件的俩个钱包地址 加上ca后续有符合钱包持续播报 单笔0.3以上
    '''
    now = datetime.now()  # 当前时间
    block_time = datetime.fromtimestamp(transactions_data[0]['block_time'])
    time_diff = (now - block_time).days
    
    if time_diff < TYPE3_SETTINGS_DAY_INTERVAL:
        return

    logging.info(f"代币 {item['mint']} 发现了{TYPE3_SETTINGS_DAY_INTERVAL}天钱包 {item['traderPublicKey']}")
    mint = item['mint']
    
    # 使用 Redis 记录每个 mint 地址符合条件的钱包地址
    redis_key = f"{MINT_15DAYS_ADDRESS}{mint}"
    
    # 从 Redis 获取当前符合条件的钱包地址列表
    mint_15days_address = redis_client().get(redis_key)
    if mint_15days_address:
        mint_15days_address = json.loads(mint_15days_address)
    else:
        mint_15days_address = []
    
    # 将当前的钱包地址加入到符合条件的钱包地址列表中
    mint_15days_address.append(item['traderPublicKey'])
    
    # 将更新后的列表存储回 Redis
    redis_client().set(redis_key, json.dumps(mint_15days_address), ex=86400)

    # 使用 Redis 计数器记录符合条件的钱包数量
    counter_key = f"{redis_key}:count"  # 计数器键名
    redis_client().incr(counter_key)  # 增加计数器值
    
    # 获取当前符合条件的钱包地址数量
    wallet_count = int(redis_client().get(counter_key))  # 获取当前符合条件的钱包数量

    if wallet_count >= 2:

        #检测 并发送到交易端
        if send_to_trader(item=item, type=3):  # 通知交易端
            item['isSentToExchange'] = 1  # 是否已经发送到交易端
        
        item['traderPublicKeyOld'] = mint_15days_address[wallet_count - 2]
        item['title'] = f"第{wallet_count - 1}通知CA:{item['symbol']}"
        send_telegram_notification(tg_message_html_4(item), [TELEGRAM_BOT_TOKEN_15DAYS, TELEGRAM_CHAT_ID_15DAYS], f"代币 {mint} 15天钱包",item)

        #保存播报记录
        item['type'] = 3
        save_transaction(item)
# 老鲸鱼钱包
def type1(item,title):
    try:
        #市值检测
        if item['market_cap'] < TYPE1_SETTINGS_MARKET_CAP_LIMIT:#老鲸鱼暴击的条件 小于设定的市值时 
            logging.error(f"代币 {item['mint']} 的市值 {item['market_cap']} 设定 {TYPE1_SETTINGS_MARKET_CAP_LIMIT} 不满足")
            return
        # tokens 余额检测
        data = fetch_user_tokens(item['traderPublicKey'])
        total_balance = data.get('total_balance')
        sol = data.get('sol')
        logging.info(f"用户 {item['traderPublicKey']} tokens:{total_balance} sol:{sol}")
        if total_balance < TYPE1_SETTINGS_TOKEN_BALANCE:
            return
        
        #检测 并发送到交易端
        if send_to_trader(item=item,type=1):
            item['isSentToExchange'] = 1 #是否已经发送到交易端
        
        #检测重复并播报到TG群
        if save_success_to_redis(mint=item['mint'],type=1,address=item['traderPublicKey']):            
            item['title'] = title
            item['sol'] = sol
            item['total_balance'] = total_balance
            send_telegram_notification(tg_message_html_1(item),[TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID],f"用户 {item['traderPublicKey']} {title}",item)

        #保存播报记录
        item['type'] = 1 
        save_transaction(item)
    except Exception as e:
            logging.error(f"获取 {item['traderPublicKey']} 的余额出错 {e}")
# 老金鱼暴击
def type2(item,title):
    logging.info(f"用户 {item['traderPublicKey']} 请求老鲸鱼暴击 {item['mint']}")
    try:
        #市值检测
        if item['market_cap'] < TYPE2_SETTINGS_MARKET_CAP_LIMIT:#老鲸鱼暴击的条件 小于设定的市值时 
            logging.error(f"代币 {item['mint']} 的市值 {item['marketCapSol']} 设定 {TYPE2_SETTINGS_MARKET_CAP_LIMIT} 不满足")
            return
        # 单币盈利检测 大于设定值 ，并且盈利率要大于300%
        data = fetch_user_wallet_holdings(item['traderPublicKey'])
        if not data:
            logging.info(f"用户 {item['traderPublicKey']} 代币盈亏数据是空")
            return
        hold_data = data
        if float(hold_data['realized_profit']) < TYPE2_SETTINGS_PROFIT_PER_TOKEN or float(hold_data['realized_pnl']) < TYPE2_SETTINGS_PROFIT_RATE_PER_TOKEN:
            logging.info(f"用户{item['traderPublicKey']} 单笔最大盈利(已结算) {hold_data['realized_profit']} usdt 小于设定值 {TYPE2_SETTINGS_PROFIT_PER_TOKEN} 盈利率为{(float(hold_data['realized_pnl']) * 100):.2f}")
            return
        #检测 并发送到交易端
        if send_to_trader(item=item,type=2):
            item['isSentToExchange'] = 1 #是否已经发送到交易端
        #检测重复并播报到TG群
        if save_success_to_redis(mint=item['mint'],type=2,address=item['traderPublicKey']):
            hold_data["traderPublicKey"] = item['traderPublicKey']
            hold_data["title"] = title
            hold_data['mint'] = item['mint']
            hold_data['solAmount'] = item['solAmount']
            hold_data['signature'] = item['signature']
            hold_data['market_cap'] = item['market_cap']#市值
            hold_data['alert_data'] = item['alert_data']#黑盘占比
            send_telegram_notification(tg_message_html_3(hold_data),[TELEGRAM_BOT_TOKEN_BAOJI,TELEGRAM_CHAT_ID_BAOJI],f"用户 {item['traderPublicKey']} {title}",item)
             
        #保存播报记录
        item['type'] = 2 
        save_transaction(item)
    except Exception as e:
        logging.error("捕捉到的异常:", e)      
# 查看用户一段时间的交易记录
def fetch_user_transactions(start_time,end_time,item):
    url = f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={item['traderPublicKey']}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&block_time[]={start_time}&block_time[]={end_time}&page=1&page_size=10&sort_by=block_time&sort_order=desc"
    response= requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        return response_data.get('data', [])
    return []
# 发送 Telegram 消息
def send_telegram_notification(message,bot,tag,item):
    #开始播报记录时间
    item['sentToBroadcastAt'] = get_utc_now()
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
def fetch_wallet_info(item):
    address = item['traderPublicKey']
    data = redis_client().get(f"{WALLET_INFOS}{address}")
    if data:
        logging.info(f"用户 {address} 取出钱包详情缓存")
        data =  json.loads(data)
    else:
        proxies = {
            "https":proxy_expired.get("proxy")
        }
        res = gmgn_api.getWalletInfo(walletAddress=address,period="7d",proxies=proxies)
        if res.status_code == 200:
            data = res.json().get('data', {})
            if data:
                logging.info(f"用户 {address} 钱包详情已缓存")
                redis_client().set(f"{WALLET_INFOS}{address}",json.dumps(data),ex=86400)
            else:
                logging.error(f"用户 {address} 钱包详情为空不能缓存")
                return True
        else:
            logging.error(f"用户 {address} 获取钱包详情 {res.text}")
            return True
    #判断总胜率
    winrate = data.get('winrate',0)
    realized_profit_7d = data.get('realized_profit_7d',0)
    pnl_7d = data.get('pnl_7d',0)
    buy_7d = data.get('buy_7d',0)
    if  WIN_RATE and winrate is not None  and winrate >= WIN_RATE:
        logging.info(f"用户 {address} 7天内结算盈利额度 {data['realized_profit_7d']}")
        return False
    if PROFIT_7D and realized_profit_7d is not None and  realized_profit_7d  >= PROFIT_7D:
        logging.info(f"用户 {address} 7天内结算盈利额度 {data['realized_profit_7d']}")
        return False
    if WIN_RATE_7D and pnl_7d is not None and  pnl_7d >= WIN_RATE_7D:
        logging.info(f"用户 {address} 7天内盈利率 {data['buy_7d']}")
        return False
    if BUY_FREQUENCY and buy_7d is not None and  buy_7d < BUY_FREQUENCY:
        logging.info(f"用户 {address} 7天内购买 {data['buy_7d']}")
        return False
    logging.info(f"用户 {address} 钱包符合要求")
    return False
#请求用户的代币盈亏情况 之请求一条，按降序排列，这一条就是金额最大的
def fetch_user_wallet_holdings(address):
    data = redis_client().get(f"{ADDRESS_HOLDINGS_DATA}{address}")

    if data:
        logging.info(f"用户 {address} 取出代币盈利缓存")
        return json.loads(data)
    else:
        proxies = {
            "https":proxy_expired.get("proxy")
        }
        res = gmgn_api.getWalletHoldings(walletAddress=address,params="limit=1&orderby=realized_profit&direction=desc&showsmall=true&sellout=true&tx30d=true",proxies=proxies)
        if res.status_code == 200:
            data = res.json().get('data', {})
            # 默认 `holdings` 字段为空列表，避免字段不存在的情况
            holdings = data.get('holdings', [])
            holdings_data = {}
             # 如果 `holdings` 存在且非空，取第一个元素
            if holdings:
                holdings_data = holdings[0]
                logging.info(f"用户 {address} 代币盈利已缓存")
                redis_client().set(f"{ADDRESS_HOLDINGS_DATA}{address}",json.dumps(holdings_data),ex=int(86400 * REDIS_EX_TIME))
            else:
                 logging.info(f"用户 {address} 没有有效的代币盈利数据，不进行缓存")
            return holdings_data
        else:
            logging.error(f"用户 {address} 获取代币盈亏失败 {res.text}")
    return {}
#请求代币token的dev情况
def fetch_mint_dev(item):
    mint = item['mint']
    traderPublicKey = item['traderPublicKey']
    res = redis_client().get(f"{MINT_DEV_DATA}{mint}")
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
            redis_client().set(f"{MINT_DEV_DATA}{mint}",json.dumps(data),ex=10)
        else:
            logging.error(f"代币 {mint} 获取dev情况失败 {res.text}")
            return True
    #检查是否是创建者
    for value in data:
        if "creator" in value['maker_token_tags'] and value['maker'] == traderPublicKey:
            logging.error(f"用户 {traderPublicKey} 是代币 {mint} 的创建者")
            return True
        
    #检查dev团队是否跑路，跑路直接放行通过
    unrealized_profits = sum(record["unrealized_profit"] for record in data)
    if data and round(unrealized_profits, 5) <=0:
        logging.info(f"代币 {mint} dev已清仓")
        return False
    
    #检查dev团队持仓 
    sols = sum(record["quote_amount"] for record in data)
    if len(data) > 1:#有小号
        if sols>=DEV_TEAM_SOL_WITH_SUB:
            logging.error(f"代币 {mint} dev团队存在小号 持仓 {sols} sol超过 {DEV_TEAM_SOL_WITH_SUB}")
            return True
    else:#没小号
        if sols>=DEV_TEAM_SOL_WITHOUT_SUB:
            logging.error(f"代币 {mint} dev团队不存在小号 持仓 {sols} sol超过 {DEV_TEAM_SOL_WITHOUT_SUB}")
            return True
    logging.info(f"代币 {mint} dev检测合格")
    return False
#请求用户的token和sol总和
def fetch_user_tokens(address):
    data = redis_client().get(f"{ADDRESS_TOKENS_DATA}{address}")
    if data and "total_balance" in data:
        logging.info(f"用户 {address} 取出tokens sol 缓存")
        return json.loads(data)
    portfolio_calculator = PortfolioValueCalculatorJUP(
        balances_api_key=HELIUS_API_KEY,
        account_address=address
    )
    data = {"total_balance":portfolio_calculator.calculate_total_value(),"sol":portfolio_calculator.get_sol(),"tokens":portfolio_calculator.get_tokens()}
    logging.info(f"用户 {address} tokens sol 已缓存")
    redis_client().set(f"{ADDRESS_TOKENS_DATA}{address}",json.dumps(data),ex=3600)
    return data
#单独的sol取出接口
def fetch_user_account_sol(address):
    data = redis_client().get(f"{ADDRESS_TOKENS_DATA}{address}")
    if data and "sol" in json.loads(data):
        logging.info(f"用户 {address} sol 缓存")
        return json.loads(data)  
    response = requests.get(f"https://pro-api.solscan.io/v2.0/account/detail?address={address}", headers=headers)
    if response.status_code == 200:
        response_data =  response.json().get('data')
        data = {"sol":response_data.get('lamports') / 10**9}
        redis_client().set(f"{ADDRESS_TOKENS_DATA}{address}",json.dumps(data),ex=3600)
        logging.info(f"用户 {address}  sol 余额已缓存")
        return data
    logging.info(f"用户 {address}  solana 余额接口调用失败了")
    return {"sol":0}
#检测并发送到交易端
def send_to_trader(item,type):
    mint = item['mint']
    traderPublicKey = item['traderPublicKey']
    symbol = item['symbol']
    if type not in ALLOWED_TRAN_TYPES:
        #失败原因放进去
        item['failureReason'] = f"交易类型不允许"

        logging.error(f"代币 {mint} 用户 {traderPublicKey} 交易类型 {type} 不允许")
        return False
    if traderPublicKey in user_wallets:
        #失败原因放进去
        item['failureReason'] = f"已被拉黑阻止交易"

        logging.error(f"用户 {traderPublicKey} 已被拉黑阻止交易 交易类型 {type}")
        return False
    if not TRANSACTION_ADDRESS_GROUP:
        #失败原因放进去
        item['failureReason'] = f"回调地址没有填写"

        logging.error(f"回调地址没有填写")
        return False
    #把重复名称的去掉
    if REMOVE_DUPLICATES_BY_NAME:
        if not symbol_unique(symbol,mint):
            item['failureReason'] = f"symbol {symbol} 同名重复"
            logging.error(f"symbol {symbol} 同名重复")
            return False
    
    #把中文的去掉
    if REMOVE_CHINESE_BY_NAME:
        if is_chinese(symbol):
            item['failureReason'] = f"symbol {symbol} 是中文"
            logging.error(f"symbol {symbol} 是中文,交易端排除")
            return False
    
    #看看redis是否已经发送到交易端了
    status = redis_client().set(f"{MINT_SUCCESS}{mint}", symbol, nx=True, ex=int(86400 * REDIS_EX_TIME))
    if not status:
        #失败原因放进去
        item['failureReason'] = f"已经发送过交易端了"

        logging.error(f"代币 {mint} 已经发送过交易端了")
        return False
    #开始发送到交易所记录时间
    item['sentToExchangeAt'] = get_utc_now()
    #开始通知交易端 多线程等待返回
    futures = [executor.submit(call_trade, mint,url,type) for url in TRANSACTION_ADDRESS_GROUP]
    # 等待并获取所有结果
    msg = ""
    flag = False
    for future in as_completed(futures):
        result = future.result()  # 获取任务的结果
        if result['success']:
            flag = True
        msg += result['msg']
            

    item['failureReason'] = msg

    if not flag:#所有地址都调用失败，删除redis记录
        logging.info(f"代币 {mint} 调用所有地址调用都失败 删掉redis记录")
        redis_client().delete(f"{MINT_SUCCESS}{mint}")
        redis_client().delete(f"{SYMBOL_UNIQUE}{mint}")
    return flag
def call_trade(mint, call_back_url, type):
    try:
        # 设置请求参数
        params = {
            'ca': mint,
            'type_id': type
        }
        # 设置 headers，确保发送的内容类型为 JSON
        headers = {'Content-Type': 'application/json'}       
        # 发送 POST 请求
        response = requests.post(call_back_url, json=params, headers=headers)
        
        # 检查返回的状态码
        if response.status_code == 200:
            logging.info(f"代币 {mint} 发送到交易端地址 {call_back_url} 代号 {type}")
            return {"success": True, "msg": f"交易端地址 {call_back_url} 成功"}
        else:
            logging.error(f"代币 {mint} 调用交易端地址 {call_back_url} 失败 代号 {type} statusCode:{response.status_code}")
            return {"success": False, "msg": f"调用交易端地址 {call_back_url} 失败 statusCode: {response.status_code}"}    
    except Exception as e:
        logging.error(f"代币 {mint} 调用交易端地址 {call_back_url} 失败: {str(e)}")
        return {"success": False, "msg": f"调用交易端地址 {call_back_url} 失败: {str(e)}"}
#获取代币流动性
def fetch_token_pool(mint):
    data = redis_client().get(f"{MINT_POOL_DATA}{mint}")
    if data:
        logging.info(f"代币 {mint} 取出代币流动性缓存")
        return json.loads(data)
    else:
        proxies = {
            "https":proxy_expired.get("proxy")
        }
        res = gmgn_api.getTokenPoolInfo(token=mint,proxies=proxies)
        if res.status_code == 200:
            data = res.json()['data']
            logging.info(f"代币 {mint} 代币流动性已缓存")
            redis_client().set(f"{MINT_POOL_DATA}{mint}",json.dumps(data),ex=10)
            return data
        else:
            logging.error(f"代币 {mint} 获取代币流动性失败 {res.text}")
    return {}
#请求用户的代币列表并对感叹号的数量进行计数
def fetch_user_wallet_holdings_show_alert(item):
    address = item['traderPublicKey']
    mint = item['mint']
    data = redis_client().get(f"{ADDRESS_HOLDINGS_ALERT_DATA}{address}")
    if data:
        logging.info(f"用户 {address} 取出用户最近活跃 {data} 警告数据百分比")
        return float(data)
    else:
        proxies = {
            "https":proxy_expired.get("proxy")
        }
        res = gmgn_api.getWalletHoldings(walletAddress=address,params="limit=50&orderby=last_active_timestamp&direction=desc&showsmall=true&sellout=true&tx30d=true",proxies=proxies)
        if res.status_code == 200:
            data = res.json()['data']
            holdings = data.get('holdings')
            holdings_data = []
            for value in holdings:#去除当前这一笔买入
                if value['token']['address'] != mint:
                    holdings_data.append(value)

            # 统计 is_show_alert 为 True 的数量
            is_show_alert_true_count = sum(1 for item in holdings_data if item.get("token", {}).get("is_show_alert"))
            total_count = len(holdings_data) 
            # 检查是否为空列表，避免除以零
            if total_count <= 0:
                proportion = None  # 如果没有数据，比例设为 0
            else:
                proportion = is_show_alert_true_count / total_count
            if proportion:
                logging.info(f"用户 {address} 用户最近活跃 警告数据百分比 {proportion} 已缓存")
                redis_client().set(f"{ADDRESS_HOLDINGS_ALERT_DATA}{address}",proportion,ex=int(86400 * REDIS_EX_TIME))
                if proportion > BLACKLIST_RATIO:
                    logging.error(f"用户 {address} 感叹号数据 {proportion} 大于{BLACKLIST_RATIO}")
                    return None
                else:
                    logging.info(f"用户 {address} 感叹号数据 {proportion} 合格")
                    return proportion
            else:
                logging.error(f"用户 {address} 用户最近活跃 警告数据百分比 是空 不能缓存")                
            return None
        else:
            logging.error(f"用户 {address} 获取用户最近活跃失败 {res.text}")
    return None
#请求用户转账记录
def fetch_user_transfer(start_time,end_time,address):
    url = f"https://pro-api.solscan.io/v2.0/account/transfer?address={address}&token=So11111111111111111111111111111111111111111&block_time[]={start_time}&block_time[]={end_time}&exclude_amount_zero=true&flow=in&page=1&page_size=10&sort_by=block_time&sort_order=desc"   
    response= requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        return response_data.get('data', [])
    return []
#保存每种类型通知过的避免同一种类型同一个mint重复播报
def save_success_to_redis(mint,type,address):
    if address in user_wallets:
        logging.error(f"用户 {address} 已被拉黑阻止播报 播报类型 {type}")
        return False
    #存放播报过的 success:mint地址/type类型 1 2 3 4
    status = redis_client().set(f"{ADDRESS_SUCCESS}{mint}/{type}",address,nx=True)
    if status:
        return True
    else:
        logging.info(f"代币 {mint} 类型{type} 阻止重复播报")
        return False
#获得拉黑的地址
def fetch_black_wallets():
    logging.info("获取拉黑的地址...")
    response = server_fun_api.getBlackWallets()
    if response.status_code == 200:
        data = response.json()['data']
        # 使用列表推导式分别获取交易所钱包和用户钱包
        global exchange_wallets, user_wallets
        exchange_wallets = [entry["walletAddress"] for entry in data if entry["type"] == 1]
        user_wallets = [entry["walletAddress"] for entry in data if entry["type"] == 2]
#计算当前的utc国内时间
def get_utc_now():
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).isoformat()
#获取一个空闲的redis客户端
def redis_client():
    return redis.Redis(connection_pool=redis_pool)
#更新最高市值
async def update_maket_cap_height_value():
    cursor = 0
    keys = []
    r = redis_client()
    # 使用 SCAN 命令遍历所有匹配的键
    while True:
        cursor, result =r.scan(cursor=cursor, match=f"{MINT_NEED_UPDATE_MAKET_CAP}*")
        keys.extend(result)
        if cursor == 0:
            break
        # 如果没有匹配到任何键，提前退出
    if not keys:
        logging.info("更新最高市值没有找到符合条件的键.")
        return
    # 获取这些键的值
    values = r.mget(keys)
    for value in values:
        if value is None:
            logging.info(f"最高市值取到的value是NONE")
            continue
        data = json.loads(value)
        mint = data.get('mint','')
        if not data['market_cap_sol_height_need_update'] or not mint:
            logging.info(f"代币 {mint} 不需要更新最高市值")
            continue
        maket_data = fetch_maket_data(mint=mint)
        if not maket_data:
            continue
        try:
            params = {
                "ca":mint,
                "tokenMarketValueHeight":maket_data['high'],
                "timeToHighMarketValue":maket_data['time_diff']
            }
            response = server_fun_api.updateMaketValueHeightByCa(params)
            response.raise_for_status()
            logging.info(f"代币 {mint} 更新最高市值 => {maket_data['high']}")
            data['market_cap_sol_height_need_update'] = False
            r.set(f"{MINT_NEED_UPDATE_MAKET_CAP}{mint}",json.dumps(data),xx=True,ex=7200)
        except requests.exceptions.RequestException as e:
            # 捕获所有请求相关的异常，包括状态码非200
            logging.error(f"更新最高市值接口报错 请求出错: {e}")
            continue
        await asyncio.sleep(2)
#请求保存播报记录到数据库中
def save_transaction(item):
    server_fun_api.saveTransaction(item)
    redis_client().set(f"{MINT_NEED_UPDATE_MAKET_CAP}{item['mint']}",json.dumps(item['subscriptions']),ex=7200)
#请求市场数据
def fetch_maket_data(mint):
    proxies = {
        "https":proxy_expired.get("proxy")
    }
    now = datetime.now() #当前时间
    start_time = now - timedelta(days=1)#前一天时间
    res = gmgn_api.getKline(token=mint,type="mcapkline",params=f"resolution=1s&from={int(start_time.timestamp())}&to={int(now.timestamp())}",proxies=proxies)
    if res.status_code == 200:
        data = res.json()['data']
        if data:
            # 筛选出high最大值的数据
            max_high_data = max(data, key=lambda x: x["high"])
            # 获取第一个元素的时间
            first_time = int(data[0]["time"])
            # 获取最大值对应的时间
            max_time = int(max_high_data["time"])
            # 计算时间差
            time_diff = max_time - first_time
            logging.info(f"代币 {mint} 最高市值 {max_high_data['high']} 时间差 {int(time_diff /1000)} 秒")
        return {"high":max_high_data['high'],"time_diff":int(time_diff /1000)}
    else:
        logging.error(f"代币 {mint} 获取市场数据失败 {res.text}")
        return {}
#储存所有订单到redis
def set_odder_to_redis(mint,data):
    r = redis_client()
    # 深拷贝 message
    order = copy.deepcopy(data)
    # 获取 mint 的订单列表，或初始化为空列表
    current_orders = json.loads(r.hget(MINT_ODDERS, mint) or "[]")
    # 添加新订单
    current_orders.append(order)
    # 存储更新后的订单列表
    r.hset(MINT_ODDERS, mint, json.dumps(current_orders))

#type1和type2 的分析交易记录
def analyze_transaction_records(transactions_data,item,count):
    now = datetime.now() #当前时间
    today = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())#今天的0点
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
    if sum > count:#前面只能出现4条买入，加上自己就是第五条
        logging.info(f"用户 {item['traderPublicKey']} 今日交易买入量已超{count}条")
        return None
    if not last_time:
        #redis 记录新用户
        logging.info(f"用户 {item['traderPublicKey']} 没有今日之外的交易数据")
        return None
    time_diff = (first_time - last_time) / 86400
    logging.info(f"用户 {item['traderPublicKey']} 今日买入 {sum}笔 今日第一笔和之前最后一笔交易时间差为 {time_diff} 天")
    return {"time_diff":time_diff,"count":sum}

#暂时的对于symbol进行去重处理
def symbol_unique(symbol,mint):
    r = redis_client()
    return r.set(f"{SYMBOL_UNIQUE}{symbol}", mint,nx=True, ex=86400)
# 主程序
async def main():
    # 启动 WebSocket 连接处理
    redis_task = asyncio.create_task(redis_get_settings())
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动处理新代币订阅
    subscribed_new_task = asyncio.create_task(subscribed_new_mq())

    # 启动处理最高市值更新
    market_cap_sol_height_task = asyncio.create_task(market_cap_sol_height_update())

    #启动公平消费任务
    fair_consumption_task = asyncio.create_task(fair_consumption())
    #心跳检查客户端队列
    check_inactive_clients_task = asyncio.create_task(check_inactive_clients())
    # 启动交易监听队列任务
    # transactions_task= asyncio.create_task(transactions_message())

    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())

    # 读取配置
    await fetch_config()
    # 等待任务完成
    await asyncio.gather(subscribed_new_task,ws_task,fair_consumption_task,check_inactive_clients_task,market_cap_sol_height_task,cleanup_task,redis_task)
    
# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
