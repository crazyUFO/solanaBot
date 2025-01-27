from collections import defaultdict
import re
# 在模块级别编译正则表达式
pattern = re.compile(r'[\u4e00-\u9fff]+')
#跨度检测方法
def check_historical_frequency(mint, txhash, step, min_amount, max_amount,max_allowed_count,total_count,data,logging):
    '''
    从txhash开始，往前推step个交易，按时间戳归类，筛选出金额在指定范围内的交易
    mint: 检测的盘
    txhash: 单子的签名
    step: 检测的跨度
    min_amount: 最小金额
    max_amount: 最大金额
    max_allowed_count 允许出现的次数
    total_count 计次范围，超出max_allowed_count范围增加一次
    data 是存放订单的数组
    logging 日志写入方法
    '''
    logging.info(f"代币 {mint} 开始跨度扫描....")
    count = 0 
    
    # 找到指定 txhash 签名的交易所在的下标
    tx_index = None
    for i, tx in enumerate(data):
        if tx['signature'] == txhash:
            tx_index = i
            break
    
    if not  tx_index:
        logging.error("订单列表未找到指定的交易签名。")
        return False
    # 定义回溯窗口的起始和结束下标
    start_index = max(0, tx_index - step)
    end_index = tx_index

    # 按时间戳归类交易（按秒分组，允许200ms误差）
    timestamp_groups = defaultdict(list)
    for i in range(start_index, end_index):
        tx = data[i]
        # 获取秒级时间戳（去除毫秒部分）
        current_timestamp = tx['create_time_stamp'] // 1000  # 转换为秒级时间戳
        
        # 判断时间戳是否与当前秒相差200ms以内
        group_found = False
        for timestamp in timestamp_groups:
            # 如果交易时间与当前时间戳的差值小于200ms，归入上一秒
            if abs(tx['create_time_stamp'] - timestamp * 1000) <= 100:
                timestamp_groups[timestamp].append(tx)
                group_found = True
                break
        
        # 如果没有找到匹配的组，则创建新的组
        if not group_found:
            timestamp_groups[current_timestamp].append(tx)

    # 筛选出每组时间戳中金额在指定范围内的交易
    for timestamp, tx_group in timestamp_groups.items():
        filtered_group = [tx for tx in tx_group if min_amount <= tx['solAmount'] <= max_amount]
        if filtered_group and len(filtered_group) >= max_allowed_count:  # 如果该时间戳组有符合条件的交易
            count+=1  
    logging.info(f"跨度检测1 代币 {mint} 签名 {txhash} 检测范围 从{start_index} 至{end_index} 检测金额范围 {min_amount}-{max_amount} 总共有{count}组数据 允许{total_count}组数据 结果{count > total_count}")
    return count > total_count


#跨度检测方法二
def check_historical_frequency2(mint, txhash, step, amount,total_count,data,logging):
    '''
    从txhash开始，往前推step个交易，按时间戳归类，筛选出金额大于amount的元素
    mint: 检测的盘
    txhash: 单子的签名
    step: 检测的跨度
    amount: 限制金额
    total_count 计次范围，超出max_allowed_count范围增加一次
    data 是存放订单的数组
    logging 日志写入方法
    '''
    logging.info(f"代币 {mint} 开始跨度2档扫描....")
    count = 0 
    
    # 找到指定 txhash 签名的交易所在的下标
    tx_index = None
    for i, tx in enumerate(data):
        if tx['signature'] == txhash:
            tx_index = i
            break
    
    if not  tx_index:
        logging.error("订单列表未找到指定的交易签名。")
        return False
    # 定义回溯窗口的起始和结束下标
    start_index = max(0, tx_index - step)
    end_index = tx_index

    for i in range(start_index, end_index):
        tx = data[i]
        if tx['solAmount'] > amount:
            count+=1
    logging.info(f"跨度检测2 代币 {mint} 签名 {txhash} 检测范围 从{start_index} 至{end_index} 检测金额 {amount}sol 总共有{count}个数据 允许{total_count}个数据 结果{count > total_count}")
    return count > total_count
#把所有字典的key变成大写
def flatten_dict(d, parent_key='', sep='_'):
    """
    Flatten the nested dictionary and convert all keys to uppercase.
    
    :param d: The dictionary to flatten.
    :param parent_key: The key that will be prefixed to the nested keys.
    :param sep: The separator to use between parent and child keys.
    :return: A flattened dictionary with all keys in uppercase.
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k.upper()}" if parent_key else k.upper()
        if isinstance(v, dict):
            # Recursively flatten the nested dictionary
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
#检测中文
def is_chinese(string):
    # 检查字符串中是否含有中文
    return bool(pattern.search(string))

