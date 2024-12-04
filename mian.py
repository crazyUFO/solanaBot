import asyncio
import websockets
import json
import aiohttp
import logging
import requests  # 用于发送 Telegram API 请求
import os
from logging.handlers import TimedRotatingFileHandler
# 常量定义
SINGLE_SOL = 0.5  # 单次买入阈值
DAY_NUM = 3  # 间隔天数
BLANCE = 100  # 账户余额阈值
TELEGRAM_BOT_TOKEN = '7914406898:AAHP3LuMY2R647rK3gI0qsiJp0Fw8J-aW_E'  # Telegram 机器人的 API Token
TELEGRAM_CHAT_ID = '-1002340584623'  # 你的 Telegram 用户或群组 ID

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

log_filename = os.path.join(LOG_DIR, "app.log")

# 创建一个TimedRotatingFileHandler，日志每12小时轮换一次，保留最近7天的日志
handler = TimedRotatingFileHandler(
    log_filename,
    when="h",  # 按小时轮换
    interval=12,  # 每12小时轮换一次
    backupCount=2,  # 保留最近14个轮换的日志文件（即7天的日志）
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
# 异步队列用于存放 WebSocket 消息
message_queue = asyncio.Queue()

# 异步函数：处理 WebSocket
async def websocket_handler():
    try:
        async with websockets.connect(WS_URL) as ws:
            # 连接成功后，发送订阅消息一次
            payload = {
                "method": "subscribeNewToken",
            }
            await ws.send(json.dumps(payload))
            logging.info("订阅请求已发送")

            # 持续接收消息并放入队列
            while True:
                data = await ws.recv()  # 等待并接收新的消息
                logging.info(f"接收到 WebSocket 消息: {data}")
                await message_queue.put(data)  # 将消息放入队列中等待处理

    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"WebSocket 连接意外关闭: {e}. 正在重连...")
        await asyncio.sleep(5)  # 等待 5 秒后重新连接
    except Exception as e:
        logging.error(f"发生了意外错误: {e}. 正在重连...")
        await asyncio.sleep(5)  # 等待 5 秒后重新连接

# 异步函数：从队列中获取消息并处理
async def process_message():
    async with aiohttp.ClientSession() as session:  # 创建一个会话，用于所有请求
        while True:
            # 从队列中获取消息并处理
            data = await message_queue.get()
            try:
                big_data = json.loads(data)

                if "mint" not in big_data:
                    continue

                mint_address = big_data["mint"]
                
                
                # 添加延迟，避免请求过于频繁
                await asyncio.sleep(8)  # 延迟 3 秒
                logging.info(f"处理代币: {mint_address} 开始请求详情")
                await start(session, mint_address)  # 直接开始处理请求，而不是等待20条数据

            except Exception as e:
                logging.error(f"处理消息时出错: {e}")

# 异步处理代币活动请求
async def start(session, mint_address):
    logging.info(f"请求代币活动数据: {mint_address}")
    async with session.get(
        f"https://pro-api.solscan.io/v2.0/token/defi/activities?address={mint_address}&source[]=6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&page=1&page_size=10&sort_by=block_time&sort_order=desc",
        #f"https://pro-api.solscan.io/v2.0/token/defi/activities?address={mint_address}&page=1&page_size=10&sort_by=block_time&sort_order=desc", 
        headers=headers
    ) as response:
        if response.status == 200:
            response_data = await response.json()
            logging.info(f"获取代币活动数据成功: {response_data}")

            if response_data.get('success') and response_data.get('data'):
                arr = response_data['data']

                # 根据条件过滤数据并根据 'from_address' 去重，保留第一个出现的条目
                seen_addresses = set()
                defi_detail = []

                for item in arr:
                    if item['routers']['token1'] == 'So11111111111111111111111111111111111111111' and (item['routers']['amount1'] / 1000000000) >= SINGLE_SOL:
                        if item['from_address'] not in seen_addresses:
                            defi_detail.append(item)
                            seen_addresses.add(item['from_address'])

                if defi_detail:
                    logging.info(f"符合条件的代币活动: {json.dumps(defi_detail)}")

                for item in defi_detail:
                    await check_user_transactions(session, item,mint_address)

        else:
            logging.error(f"请求代币活动数据失败: {response.status} - {await response.text()}")

# 异步请求用户交易记录和余额
async def check_user_transactions(session, item,mint_address):
    logging.info(f"请求用户交易记录: {item['from_address']}")
    async with session.get(
        f"https://pro-api.solscan.io/v2.0/account/defi/activities?address={item['from_address']}&activity_type[]=ACTIVITY_TOKEN_SWAP&activity_type[]=ACTIVITY_AGG_TOKEN_SWAP&page=1&page_size=40&sort_by=block_time&sort_order=desc",
        # f"https://pro-api.solscan.io/v2.0/account/transactions?address={item['from_address']}&before={item['trans_id']}&limit=10", 
        headers=headers
    ) as response:
        if response.status == 200:
            response_data = await response.json()
            logging.info(f"获取用户交易记录成功: {response_data}")
            if response_data.get('success') and len(response_data.get('data', [])) >= 2:
                arr = response_data['data']
                time1 = arr[0]
                time2 = arr[1]
                # 遍历数据
                for i in range(len(arr)):
                    if arr[i]['trans_id'] == item['trans_id']:  # 对比
                        logging.info(f"从用户活动中找到了 {item['trans_id']} hash签名")
                        # 取出当前数据和下一条数据
                        time1 = arr[i]
                        time2 = arr[i + 1] if i + 1 < len(arr) else None  # 防止越界
                        break  # 结束循环
                time_diff = (time1['block_time'] - time2['block_time']) / 86400  # 将区块时间转换为天数
                logging.info(f"间隔天数：{time_diff}")
                if time_diff >= DAY_NUM:
                    logging.info(f"---------检测到用户交易数据----------------")
                    logging.info(f"{item['from_address']} 在过去 {DAY_NUM} 天内没有代币交易，突然进行了交易。")
                    logging.info("---------检测结束---------------")
                    
                    # 检查用户账户余额
                    await check_user_balance(session, item,mint_address)

        else:
            logging.error(f"请求用户交易记录失败: {response.status} - {await response.text()}")

# 异步请求用户的账户余额
async def check_user_balance(session, item,mint_address):
    logging.info(f"请求账户详情: {item['from_address']}")
    async with session.get(
        f"https://pro-api.solscan.io/v2.0/account/detail?address={item['from_address']}", 
        headers=headers
    ) as response:
        if response.status == 200:
            response_data = await response.json()
            logging.info(f"获取账户详情成功: {response_data}")

            if response_data.get('success') and response_data.get('data'):
                data = response_data['data']
                if data['lamports'] / 1000000000 >= BLANCE:
                    logging.info(f"账户 {item['from_address']} 余额超过 {BLANCE} SOL，符合通知条件！")
                    
                    # 发送通知到 Telegram
                    message = f'''
<b>🐋🐋🐋🐋鲸鱼钱包🐋🐋🐋🐋</b>

token:\n<code>{mint_address}</code>

购买的老钱包:\n<code>{item['from_address']}</code>

购买金额: {item['routers']['amount1'] / 1000000000} SOL
钱包余额: {data['lamports'] / 1000000000} SOL

查看钱包: <a href="https://solscan.io/account/{item['from_address']}"><b>SOLSCAN</b></a> <a href="https://gmgn.ai/sol/address/{item['from_address']}"><b>GMGN</b></a>

查看K线: <a href="https://pump.fun/coin/{mint_address}"><b>PUMP</b></a> <a href="https://gmgn.ai/sol/token/{mint_address}"><b>GMGN</b></a>

交易哈希: <a href="https://solscan.io/tx/{item['trans_id']}"><b>SOLSCAN</b></a>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
                        '''
                    send_telegram_notification(message)
        else:
            logging.error(f"请求账户详情失败: {response.status} - {await response.text()}")

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

# 主程序
async def main():
    # 启动 WebSocket 连接处理
    ws_task = asyncio.create_task(websocket_handler())

    # 启动处理队列的任务
    process_task = asyncio.create_task(process_message())

    # 等待任务完成
    await asyncio.gather(ws_task, process_task)

# 启动 WebSocket 处理程序
if __name__ == '__main__':
    asyncio.run(main())
