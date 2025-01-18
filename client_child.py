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
from zoneinfo import ZoneInfo
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
REDIS_LIST = config.get('REDIS', 'REDIS_LIST')
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
#2025.1.2日更新增加新播报需求
MINT_15DAYS_ADDRESS = "mint_15days_address:"
MINT_ZHUANZHANG_ADDRESS = "mint_zhuanzhang_address:"
#2025.1.16更新 缓存所有发送到后台里的 代币 需要更新最高市值用到
MINT_NEED_UPDATE_MAKET_CAP = "mint_need_update_maket_cap:"
MINT_NEED_UPDATE_MAKET_CAP_LOCKED = "mint_need_update_maket_cap_locked"#因为多台服务器的原因，每次只有一台服务器进入更新
mint_15days_address = {}
exchange_wallets = [] #拉黑的交易所地址，从服务器获取
user_wallets = []#拉黑的钱包地址
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
    try:
        response = server_fun_api.getConfigById(server_id=server_id)
        response.raise_for_status()  # 如果请求失败，则抛出异常
        data = response.json()['data']
        config = json.loads(data.get('settings'))
        global SOLSCAN_TOKEN,HELIUS_API_KEY,SINGLE_SOL,DAY_NUM,BLANCE,TOKEN_BALANCE,MIN_TOKEN_CAP,MAX_TOKEN_CAP,TOTAL_PROFIT,TOKEN_EXPIRY,CALL_BACK_URL,MIN_DAY_NUM,LIQUIDITY,ALTER_PROPORTION,ALLOWED_TRAN_TYPES,ALLOWED_DEV_NUM_HAS_CHILD,ALLOWED_DEV_NUM
        TOKEN_EXPIRY = config.get("TOKEN_EXPIRY") * 60
        SINGLE_SOL = config.get("SINGLE_SOL")
        MIN_TOKEN_CAP = config.get("MIN_TOKEN_CAP")
        MAX_TOKEN_CAP = config.get("MAX_TOKEN_CAP")
        TOTAL_PROFIT = config.get("TOTAL_PROFIT")
        TOKEN_BALANCE = config.get("TOKEN_BALANCE")
        HELIUS_API_KEY = config.get("HELIUS_API_KEY")
        SOLSCAN_TOKEN = config.get("SOLSCAN_TOKEN")
        DAY_NUM = config.get("DAY_NUM")
        MIN_DAY_NUM = 0.7 # 虽小满足播报的单位，同时也是redis缓存释放的时间
        LIQUIDITY = 4000 #流动性
        ALTER_PROPORTION = 0.6 #感叹号占比
        ALLOWED_TRAN_TYPES = [1,2,3,4] #允许的交易类型
        ALLOWED_DEV_NUM_HAS_CHILD = 15 #dev数据上限 代表DEV团队整体持有多少 有小号
        ALLOWED_DEV_NUM = 6 #没有小号
        BLANCE = config.get("BLANCE")
        url = config.get("CALL_BACK_URL") ##获取回调地址组
        # 处理空字符串的情况
        CALL_BACK_URL = url.replace(" ", "").split("\n") if url else []
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

        # if not sol_price.get("create_time") or current_time - sol_price.get("create_time") >= 60*5:
        sol_price['create_time'] = current_time
        sol_price['price'] = await get_sol_for_usdt()
        logging.info(f"更新SOL的价格 {sol_price['price']} usd")
        #获取拉黑的地址
        fetch_black_wallets()
        # 遍历所有订阅，最后一次交易时间超时 12.31日更新 并且要低于市值设定最小值或者高于市值设定最大值
        for mint_address, data in subscriptions.items():            
            market_cap_usdt = data['market_cap_sol'] * sol_price['price']
            if current_time - data['last_trade_time'] >= TOKEN_EXPIRY and (market_cap_usdt < MIN_TOKEN_CAP or market_cap_usdt >= MAX_TOKEN_CAP):
                logging.info(f"代币 {mint_address} 市值 {market_cap_usdt} 并已经超过超时阈值 {TOKEN_EXPIRY / 60} 分钟")
                expired_addresses.append(mint_address)
        
        # 移除过期的订阅
        for mint_address in expired_addresses:
            del subscriptions[mint_address]
        
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
        logging.error(f"----目前进程播报----")
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
                            #计算代币美元单价
                            message['sol_price_usd'] = sol_price['price']                           
                            if txType == 'create':
                                await subscribed_new_mq_list.put(message)  # 识别订单创建
                            elif txType == "buy" and "solAmount" in message:
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
                                        redis_client().set(f"{MINT_NEED_UPDATE_MAKET_CAP}{mint}",json.dumps(subscriptions[mint]),xx=True,ex=86400)
                                #扫描符合要求的订单
                                if message['solAmount'] >= 0.3: ##2025.1.2 日增加新播报需求，老钱包买单 内盘出现两个个15天以上没操作过买币卖币行为的钱包 播报出来播报符合条件的俩个钱包地址 加上ca后续有符合钱包持续播报 单笔0.3以上
                                    lock_acquired = redis_client().set(f"{TXHASH_SUBSCRBED}{message['signature']}","原子锁5秒", nx=True, ex=5)  # 锁5秒自动过期
                                    if lock_acquired:
                                        logging.error(f"用户 {message['traderPublicKey']} {message['signature']}  交易金额:{message['solAmount']}")
                                        transactions_message_no_list(message)
                                    #await market_cap_sol_height_update_mq_list.put(message)  # 买入单推送
                                # else:
                                #     logging.info(f"用户 {message['traderPublicKey']} {message['signature']}  交易金额:{amount} 不满足")
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
                        "market_cap_sol_height_need_update":False #更新最高市值的flag True 就是需要更新到后端
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

#最高市值更新列队
async def market_cap_sol_height_update():
    while True:
        logging.info(f"开始最高市值更新")
        #更新最高市值到后台
        update_maket_cap_height_value()
        await asyncio.sleep(300)  # 每过5分钟检查一次

#订单不走列队
def transactions_message_no_list(data):
    check = redis_client().exists(f"{ADDRESS_EXPIRY}{data['traderPublicKey']}")
    if not check: #排除了那些频繁交易的 减少API输出
        executor.submit(check_user_transactions, data)
    else:
        logging.info(f"用户 {data['traderPublicKey']} 已被redis排除 {MIN_DAY_NUM} 天")

def check_user_transactions(item):
    '''
    为三种播报拿到交易记录，拿到交易记录之后，再线程分发到三种播报
    '''
    now = datetime.now() #当前时间
    start_time = int((now - timedelta(days=365)).timestamp())#获取近365天的20条记录
    transactions_data =  fetch_user_transactions(start_time,now.timestamp(),item)#获取近365天内的20条交易记录

    #检查dev数据
    if fetch_mint_dev(item):##符合条件就是 诈骗盘 条件：老鲸鱼是dev团队中人 dev和dev小号
        return
    logging.info(f"代币 {item['mint']} dev检测合格")

    #检查感叹号数据
    alert_data = fetch_user_wallet_holdings_show_alert(item['traderPublicKey'],item['mint'])
    if alert_data is None:
        logging.info(f"用户 {item['traderPublicKey']} 感叹号数据为None")
        return
    if alert_data > ALTER_PROPORTION:
        logging.info(f"用户 {item['traderPublicKey']} 感叹号数据大于50%")
        return
    logging.info(f"用户 {item['traderPublicKey']} 感叹号数据检测合格 {alert_data}")
    
    #4种type都需要用到的数据
    item['alert_data'] = alert_data
    item['symbol'] = subscriptions[item['mint']]['symbol']
    item['market_cap'] = item['marketCapSol'] * sol_price['price'] #市值
    item['isSentToExchange'] = 0 #是否已经发送到交易端
    item['mint_create_time_utc'] = subscriptions[item['mint']]['create_time_utc'] #代币创建时间


    if item['solAmount'] >= SINGLE_SOL:
        #老鲸鱼和老鲸鱼暴击
        executor.submit(ljy_ljy_bj, item,transactions_data)
    #新版15天钱包播报
    executor.submit(ljy_15days, item,transactions_data)
    #新版老钱包转账播报
    executor.submit(ljy_zzqb, item,transactions_data)
#新版更新老鲸鱼转账钱包
def ljy_zzqb(item,transactions_data):
    '''
    老鲸鱼转账钱包 
    内容 抓内盘买单（买单钱包必须是操作不频繁24小时内没操作过 买卖的再去抓上级） 
    钱包上级转账是鲸鱼钱包 至少持有两个代币 持有代币余额大于5w刀以上

    符合条件播报钱包和上级钱包 和ca  一级钱包购买大于0.3
    '''
    if len(transactions_data)==0:
        logging.info(f"用户 {item['traderPublicKey']} 没有交易 疑似是新账号（老钱包转账）")
        return
    now = datetime.now() #当前时间
    block_time = datetime.fromtimestamp(transactions_data[0]['block_time'])
    time_diff = (now - block_time).total_seconds()
    if time_diff < 12 * 3600: #计算小时数
        return
    start_time = int((now - timedelta(days=7)).timestamp())#获取近72小时内的转账记录
    transfer_data = fetch_user_transfer(start_time,now.timestamp(),item['traderPublicKey'])
    father_address = None
    for value in transfer_data:
        sol_amount = value['amount']/(10**value['token_decimals'])
        if sol_amount>=2 and value['from_address'] not in exchange_wallets:#2个以上转账 并且不是交易所地址
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
    if len(tokens)>=2 and total_balance >=20000:

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

def ljy_15days(item, transactions_data):
    '''
        2025.1.2 日增加新播报需求，老钱包买单 内盘出现两个个15天以上没操作过买币卖币行为的钱包 播报出来播报符合条件的俩个钱包地址 加上ca后续有符合钱包持续播报 单笔0.3以上
    '''
    if len(transactions_data) == 0:
        logging.info(f"用户 {item['traderPublicKey']} 没有交易 疑似是新账号（15天钱包的方法）")
        return

    now = datetime.now()  # 当前时间
    block_time = datetime.fromtimestamp(transactions_data[0]['block_time'])
    time_diff = (now - block_time).days
    
    if time_diff < 15:
        return

    logging.info(f"代币 {item['mint']} 发现了15天钱包 {item['traderPublicKey']}")
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
# 异步请求用户交易记录和余额
def ljy_ljy_bj(item,transactions_data):
    '''
        老鲸鱼3种情况：
        1.今日第一笔交易和前一次交易要间隔24小时,中间不能出现任何交易单--1天老鲸鱼
        2.今日第一笔交易和前一次交易要间隔48小时,中间的买入单要在5单一下--2天老鲸鱼
        3.今日第一笔交易和前一次交易要间隔72小时，中间买入单要在5单以下---3天老鲸鱼

        老鲸鱼暴击：
        1.单次买入0.5以上，tokens余额再1W以上，总营收超过1w美金以上
    '''
    try:
        if len(transactions_data)==0:
            logging.info(f"用户 {item['traderPublicKey']} 没有交易 疑似是新账号 (老鲸鱼 老鲸鱼暴击)")
            return
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
        if sum > 3:#前面只能出现4条买入，加上自己就是第五条
            #redis 记录大于5条的用户
            redis_client().set(f"{ADDRESS_EXPIRY}{item['traderPublicKey']}","当日大于5条交易",nx=True,ex=int(86400 * MIN_DAY_NUM))
            logging.info(f"用户 {item['traderPublicKey']} 今日交易买入量已超5条")
            return
        if not last_time:
            #redis 记录新用户
            redis_client().set(f"{ADDRESS_EXPIRY}{item['traderPublicKey']}","新账号",nx=True,ex=int(86400 * MIN_DAY_NUM))
            logging.info(f"用户 {item['traderPublicKey']} 没有今日之外的交易数据")
            return
        time_diff = (first_time - last_time) / 86400
        logging.info(f"用户 {item['traderPublicKey']} 今日买入 {sum}笔 今日第一笔和之前最后一笔交易时间差为 {time_diff} 天")

        with ThreadPoolExecutor(max_workers=20) as nested_executor:  
            if time_diff>=DAY_NUM:#两天以上老鲸鱼 老鲸鱼暴击
                nested_executor.submit(check_user_balance, item,f"老鲸鱼CA:{item['symbol']}")  #老鲸鱼
                nested_executor.submit(check_user_wallet, item,f"暴击CA:{item['symbol']}")  #老鲸鱼暴击
            elif time_diff>=MIN_DAY_NUM and  sum == 0:#一天以上老鲸鱼 老鲸鱼暴击 改成了15小时就报               
                nested_executor.submit(check_user_balance, item,f"老鲸鱼CA:{item['symbol']}")  #老鲸鱼
                nested_executor.submit(check_user_wallet, item,f"暴击CA:{item['symbol']}")  #老鲸鱼暴击
    except Exception as e:
         logging.error("用户交易记录的异常:", e)
# 请求用户的账户余额并通知 老鲸鱼播报
def check_user_balance(item,title):
    try:
        #市值检测
        if item['market_cap'] < MIN_TOKEN_CAP:#老鲸鱼暴击的条件 小于设定的市值时 
            logging.error(f"代币 {item['mint']} 的市值 {item['market_cap']} 设定 {MIN_TOKEN_CAP} 不满足")
            return
        # tokens 余额检测
        data = fetch_user_tokens(item['traderPublicKey'])
        total_balance = data.get('total_balance')
        sol = data.get('sol')
        logging.info(f"用户 {item['traderPublicKey']} tokens:{total_balance} sol:{sol}")
        if total_balance < TOKEN_BALANCE:
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
# 请求用户的卖出单 老金鱼暴击
def check_user_wallet(item,title):
    logging.info(f"用户 {item['traderPublicKey']} 请求老鲸鱼暴击 {item['mint']}")
    try:
        #市值检测
        if item['market_cap'] < MIN_TOKEN_CAP:#老鲸鱼暴击的条件 小于设定的市值时 
            logging.error(f"代币 {item['mint']} 的市值 {item['marketCapSol']} 设定 {MIN_TOKEN_CAP} 不满足")
            return
        # 单币盈利检测 大于设定值 ，并且盈利率要大于300%
        data = fetch_user_wallet_holdings(item['traderPublicKey'])
        if not data:
            logging.info(f"用户 {item['traderPublicKey']} 代币盈亏数据是空")
            return
        hold_data = data
        if float(hold_data['realized_profit']) < TOTAL_PROFIT or float(hold_data['realized_pnl']) < 3:
            logging.info(f"用户{item['traderPublicKey']} 单笔最大盈利(已结算) {hold_data['realized_profit']} usdt 小于设定值 {TOTAL_PROFIT} 盈利率为{(float(hold_data['realized_pnl']) * 100):.2f}")
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
    url = f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={item['traderPublicKey']}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&block_time[]={start_time}&block_time[]={end_time}&page=1&page_size=20&sort_by=block_time&sort_order=desc"
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
                redis_client().set(f"{ADDRESS_HOLDINGS_DATA}{address}",json.dumps(holdings_data),ex=int(86400 * MIN_DAY_NUM))
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
    #检查是否是创建者
    for value in data:
        if "creator" in value['maker_token_tags'] and value['maker'] == traderPublicKey:
            logging.error(f"用户 {traderPublicKey} 是代币 {mint} 的创建者")
            return True
        
    #检查dev团队是否跑路，跑路直接放行通过
    unrealized_profits = sum(record["unrealized_profit"] for record in data)
    if round(unrealized_profits, 5) <=0:
        return False
    
    #检查dev团队持仓 
    sols = sum(record["quote_amount"] for record in data)
    if len(data) > 1:#有小号
        if sols>=ALLOWED_DEV_NUM_HAS_CHILD:
            logging.error(f"代币 {mint} dev团队存在小号 持仓 {sols} sol超过 {ALLOWED_DEV_NUM_HAS_CHILD}")
            return True
    else:#没小号
        if sols>=ALLOWED_DEV_NUM:
            logging.error(f"代币 {mint} dev团队不存在小号 持仓 {sols} sol超过 {ALLOWED_DEV_NUM}")
            return True
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
    if not CALL_BACK_URL:
        #失败原因放进去
        item['failureReason'] = f"回调地址没有填写"

        logging.error(f"回调地址没有填写")
        return False
    #看看redis是否已经发送到交易端了
    status = redis_client().set(f"{MINT_SUCCESS}{mint}", type, nx=True, ex=int(86400 * MIN_DAY_NUM))
    if not status:
        #失败原因放进去
        item['failureReason'] = f"已经发送过交易端了"

        logging.error(f"代币 {mint} 已经发送过交易端了")
        return False
    #开始发送到交易所记录时间
    item['sentToExchangeAt'] = get_utc_now()
    #开始通知交易端 多线程等待返回
    futures = [executor.submit(call_trade, mint,url,type) for url in CALL_BACK_URL]
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
def fetch_user_wallet_holdings_show_alert(address,mint):
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
                redis_client().set(f"{ADDRESS_HOLDINGS_ALERT_DATA}{address}",proportion,ex=int(86400 * MIN_DAY_NUM))
            else:
                logging.info(f"用户 {address} 用户最近活跃 警告数据百分比 是空 不能缓存")
            return proportion
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
def update_maket_cap_height_value():
    cursor = 0
    keys = []
    # 使用 SCAN 命令遍历所有匹配的键
    while True:
        cursor, result =redis_client().scan(cursor=cursor, match=f"{MINT_NEED_UPDATE_MAKET_CAP}*")
        keys.extend(result)
        if cursor == 0:
            break
        # 如果没有匹配到任何键，提前退出
    if not keys:
        logging.info("更新最高市值没有找到符合条件的键.")
        return
    # 获取这些键的值
    values = redis_client().mget(keys)
    for value in values:
        data = json.loads(value)
        if data['market_cap_sol_height_need_update']:
            mint = data['mint']
            maket_data = fetch_maket_data(mint=mint)
            if not maket_data:
                return
            try:
                params = {
                    "ca":data['mint'],
                    "tokenMarketValueHeight":maket_data['high'],
                    "timeToHighMarketValue":maket_data['time_diff']
                }
                response = server_fun_api.updateMaketValueHeightByCa(params)
                response.raise_for_status()
                logging.info(f"代币 {params['ca']} 更新最高市值 => {maket_data['high']}")
                data['market_cap_sol_height_need_update'] = False
                redis_client().set(f"{MINT_NEED_UPDATE_MAKET_CAP}{params['ca']}",json.dumps(data),xx=True)
            except requests.exceptions.RequestException as e:
                # 捕获所有请求相关的异常，包括状态码非200
                logging.error(f"更新最高市值接口报错 请求出错: {e}")
        time.sleep(2)
#请求保存播报记录到数据库中
def save_transaction(item):
    server_fun_api.saveTransaction(item)
    redis_client().set(f"{MINT_NEED_UPDATE_MAKET_CAP}{item['mint']}",json.dumps(subscriptions[item['mint']]),ex=86400)
#请求市场诗句
def fetch_maket_data(mint):
    proxies = {
        "https":proxy_expired.get("proxy")
    }
    now = datetime.now() #当前时间
    start_time = now - timedelta(days=1)#前一天时间
    res = gmgn_api.getKline(token=mint,type="mcapkline",params=f"resolution=1s&from={start_time.timestamp()}&to={now.timestamp()}",proxies=proxies)
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
    
    # 启动交易监听队列任务
    # transactions_task= asyncio.create_task(transactions_message())

    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())

    # 读取配置
    await fetch_config()
    # 等待任务完成
    await asyncio.gather(ws_task,subscribed_new_task,market_cap_sol_height_task,cleanup_task,redis_task)
    
# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
