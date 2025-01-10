import asyncio
import redis.client
import websockets
import json
import logging
import requests  # 用于发送 Telegram API 请求
import os
from portfolivalueCalculatorJUP import PortfolioValueCalculatorJUP
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import redis
import time
import configparser
from cloudbypass import Proxy
import csv
from gmgn import gmgn
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
# 创建线程池执行器
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

#redis 缓存查询的 代币 dev数据 去重数据 市值数据 
TXHASH_SUBSCRBED = "txhash_subscrbed:"#redis 按订单去重 原子锁
ADDRESS_TOKENS_DATA = "address_tokens_data:" #用户tokens sol 余额 缓存1小时
ADDRESS_SCAN_PARENT = "address_scan_parent:" #缓存搜索过的地址 原子锁，搜索过 缓存7天
mint_zhuanzhang_address={}
exchange_wallets = [] #拉黑的交易所地址，从服务器获取
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

proxy = Proxy("81689111-dat:toeargna")
proxy_expired = {"create_time": time.time(), "proxy": str(proxy.copy().set_expire(60 * 10))}

# 初始化全局变量用于订阅和价格管理
subscriptions = {}
sol_price = {"create_time": None, "price": 0}

# 初始化 gmgn API
gmgn_api = gmgn()

# 全局请求头（初始为空）
headers = {}
# 获取远程配置函数
# 设置 CSV 文件路径
csv_file = 'wallet_parent_chain.csv'
async def fetch_config(server_id = SERVER_ID):
    try:
        response = requests.get(f"{DOMAIN}/api/nodes/{server_id}")
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

        #获取拉黑的交易所地址
        fetch_exchange_wallets()

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
                                await message_queue_1.put(message)  # 识别订单创建
                            elif txType == "buy":
                                try:
                                    amount = message['solAmount']
                                except KeyError:
                                    logging.error(f"下标solAmount {message}")
                                    amount = 0
                                #加入最后活跃时间
                                if mint in subscriptions:
                                    subscriptions[mint].update({
                                        "last_trade_time": time.time(),
                                        "market_cap_sol": message['marketCapSol'],
                                    })
                                    message['amount'] = amount
                                    executor.submit(get_parent_wallet, message['traderPublicKey'])
                            elif txType == "sell":
                                #加入最后活跃时间
                                if mint in subscriptions:
                                    subscriptions[mint].update({
                                        "last_trade_time": time.time(),
                                        "market_cap_sol": message['marketCapSol'],
                                    })
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
                        "market_cap_sol":data['marketCapSol'],
                        "symbol":data['symbol']
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

def get_parent_wallet(wallet_address,level="1", max_depth=3):
    '''
    递归查找转账钱包
    查找7天内转账的 2SOL以上的钱包
    并且这个钱包的余额要大于20SOL
    并且这个钱包没有过代币的交易
    '''
    locked = redis_client.set(f"{ADDRESS_SCAN_PARENT}{wallet_address}",wallet_address, nx=True, ex=86400)
    if not locked:
        logging.error(f"钱包 {wallet_address} 重复搜索...")
        return None
    if max_depth <= 0:
        logging.info(f"最大递归深度达到，停止查找钱包 {wallet_address}")
        return None

    now = datetime.now()  # 当前时间
    start_time = int((now - timedelta(days=7)).timestamp())  # 获取近7日内的转账记录
    try:
        transfer_data = fetch_user_transfer(start_time, now.timestamp(), wallet_address)
    except Exception as e:
        logging.error(f"获取钱包 {wallet_address} 转账数据失败: {e}")
        return None

    parent_wallet = None
    for value in transfer_data:
        sol_amount = value['amount'] / (10 ** value['token_decimals'])
        # 检查转账金额大于等于2SOL且发起地址不是交易所地址
        if sol_amount >= 2 and value['from_address'] not in exchange_wallets:
            # 进一步检查该父钱包余额和是否有代币交易（假设有相关接口）
            parent_balance = fetch_user_account_sol(value['from_address'])['sol']
            if parent_balance >= 20 and not fetch_user_transactions(start_time, now.timestamp(),value['from_address']) and parent_balance < 5000:
                # 此钱包地址符合条件，可能是上级钱包
                parent_wallet = value['from_address']
                # 写入当前钱包和上级钱包信息到 CSV
                write_to_csv(level,wallet_address, fetch_user_account_sol(wallet_address)['sol'], parent_wallet, parent_balance)
                break
    
    if parent_wallet:
        # 找到符合条件的父钱包，进行递归查找
        logging.info(f"找到钱包 {wallet_address} 的上级钱包 {parent_wallet}")
         # 递归时增加层级，比如从 "1" 到 "1.1"
        next_level = f"{level}.1"
        return get_parent_wallet(parent_wallet,level=next_level ,max_depth = max_depth - 1)
    else:
        logging.info(f"未能找到钱包 {wallet_address} 的上级钱包")
        return None
# 打开 CSV 文件并初始化表头
def init_csv():
    with open(csv_file, mode='w', newline='',encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(["钱包层级","钱包地址", "钱包余额 (SOL)", "上级钱包地址", "上级钱包余额 (SOL)"])

# 写入 CSV 文件
def write_to_csv(level,wallet_address, wallet_balance, parent_wallet_address, parent_wallet_balance):
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([level, wallet_address, wallet_balance, parent_wallet_address, parent_wallet_balance])
#请求用户转账记录
def fetch_user_transfer(start_time,end_time,address):
    url = f"https://pro-api.solscan.io/v2.0/account/transfer?address={address}&token=So11111111111111111111111111111111111111111&block_time[]={start_time}&block_time[]={end_time}&exclude_amount_zero=true&flow=in&page=1&page_size=10&sort_by=block_time&sort_order=desc"   
    response= requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        return response_data.get('data', [])
    return []
# 查看用户一段时间的交易记录
def fetch_user_transactions(start_time,end_time,address):
    url = f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={address}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&block_time[]={start_time}&block_time[]={end_time}&page=1&page_size=10&sort_by=block_time&sort_order=desc"
    response= requests.get(url,headers=headers)
    if response.status_code == 200:
        response_data =  response.json()
        return response_data.get('data', [])
    return []
#单独的sol取出接口
def fetch_user_account_sol(address):
    data = redis_client.get(f"{ADDRESS_TOKENS_DATA}{address}")
    if data and "sol" in json.loads(data):
        logging.info(f"用户 {address} sol 缓存")
        return json.loads(data)  
    response = requests.get(f"https://pro-api.solscan.io/v2.0/account/detail?address={address}", headers=headers)
    if response.status_code == 200:
        response_data =  response.json().get('data')
        data = {"sol":response_data.get('lamports') / 10**9}
        redis_client.set(f"{ADDRESS_TOKENS_DATA}{address}",json.dumps(data),ex=3600)
        logging.info(f"用户 {address}  sol 余额已缓存")
        return data
    logging.info(f"用户 {address}  solana 余额接口调用失败了")
    return {"sol":0}
#获得交易所地址
def fetch_exchange_wallets():
    logging.info("获取拉黑的交易所地址...")
    response = requests.get(f"{DOMAIN}/api/exchange-wallets")
    if response.status_code == 200:
        data = response.json()['data']
        global exchange_wallets
        exchange_wallets = [entry["walletAddress"] for entry in data] 



# 主程序
async def main():
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动处理队列的任务
    process_task = asyncio.create_task(process_message())
    
    # 启动订阅清理任务
    cleanup_task = asyncio.create_task(cleanup_subscriptions())
    # 读取配置
    await fetch_config()
    init_csv()
    # 等待任务完成
    await asyncio.gather(ws_task,process_task,cleanup_task)
    
# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
