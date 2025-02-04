from collections import defaultdict
import re
import json
# 在模块级别编译正则表达式
pattern = re.compile(r'[\u4e00-\u9fff]+')
#持有者检测-转账时间一致性检测
def transfer_time_consistency_check(data,time_range,allowed_times):
    '''
    持有者检测-转账时间一致性检测
    data 是数据
    allowed_times 是允许次数
    max_time_diff 为时间差，time_range是时间范围，比如1秒时间差，
    和1秒内的区别 1秒内也就是不允许有时间差就是0，那么设置2秒内，就是允许1秒时间差
    '''
    # 定义允许的最大时间差（2秒）
    max_time_diff = time_range - 1

    # 创建一个字典，根据时间戳分类
    grouped_data = []

    # 用来存储当前分类的时间戳（可以是第一个元素的时间戳）
    current_group = []

    # 遍历数据，将其根据 timestamp 分类
    for item in data:
        timestamp = item['native_transfer']['timestamp']
        
        # 如果当前分组为空，或当前元素与当前分组的最后元素时间差小于等于 max_time_diff
        if not current_group:
            current_group.append(item)
        else:
            last_item = current_group[-1]
            last_timestamp = last_item['native_transfer']['timestamp']
            time_diff = abs(timestamp - last_timestamp)
            
            if time_diff <= max_time_diff:
                current_group.append(item)  # 加入当前组
            else:
                grouped_data.append(current_group)  # 结束当前组，并开始新的一组
                current_group = [item]  # 新的分组开始

    # 将最后一个分组加入结果
    if current_group:
        grouped_data.append(current_group)
    for item in grouped_data:
        if len(item) > allowed_times:
            return True
    return False

#购买一致性检测
def purchase_consistency_check(data,amount_range,time_range,allowed_times,sol_usd):
    '''
    持有者检测-购买一致性检测
    data 是数据
    amount_range 是[min,max] 以sol计
    time_range 是时间范围，比如设置1秒就是1秒内，是不允许有时间差的，设置2秒，就是允许有1秒时间差
    sol_usd 是sol的usd市价
    allowed_times 是允许次数
    max_time_diff 为时间差，time_range是时间范围，比如1秒时间差，
    和1秒内的区别 1秒内也就是不允许有时间差就是0，那么设置2秒内，就是允许1秒时间差
    '''
    # 定义允许的最大时间差（2秒）
    
    max_time_diff = time_range - 1 

    # 创建一个字典，根据时间戳分类
    grouped_data = []

    # 用来存储当前分类的时间戳（可以是第一个元素的时间戳）
    current_group = []

    # 遍历数据，将其根据 timestamp 分类
    for item in data:
        cost_sol = item['cost'] / sol_usd #计算 转账金额的sol
        if cost_sol >= amount_range[0] and cost_sol<=amount_range[1]:
            timestamp = item['start_holding_at']
            # 如果当前分组为空，或当前元素与当前分组的最后元素时间差小于等于 max_time_diff
            if not current_group:
                current_group.append(item)
            else:
                last_item = current_group[-1]
                last_timestamp = last_item['start_holding_at']
                time_diff = abs(timestamp - last_timestamp)
                
                if time_diff <= max_time_diff:
                    current_group.append(item)  # 加入当前组
                else:
                    grouped_data.append(current_group)  # 结束当前组，并开始新的一组
                    current_group = [item]  # 新的分组开始

    # 将最后一个分组加入结果
    if current_group:
        grouped_data.append(current_group)
    for item in grouped_data:
        if len(item) > allowed_times:
            return True
    return False
#大额交易检测
def large_transaction_check(data,max_amount,sol_usd):
    '''
    data 是数据
    max_amount 是检测上限金额
    sol_usd 是sol的usd市价
    '''
    for item in data:
        cost_sol = item['cost'] / sol_usd
        if cost_sol > max_amount:
            return True
    return False
#相似度检测
def similarity_check(data,phishing_wallet_enabled,phishing_wallet_count,insider_trading_edabled,insider_trading_count,source_wallet_enabled,source_wallet_count,dev_team_enabled,dev_team_count,total_enabled,total_count):
    '''
    当total_enabled 开启时，计算几个条件加起来的总数不大于total_count
    当只有某些标签勾选的时候，只计算这些数量不大于设置值
    data, #数据
    phishing_wallet_enabled,#钓鱼钱包开关
    phishing_wallet_count,# 允许的条数
    insider_trading_edabled,#老鼠仓开关
    insider_trading_count,#允许条数
    source_wallet_enabled,#同源钱包开关
    source_wallet_count,#允许条数
    dev_team_enabled,#dev团队开关
    dev_team_count,#允许条数
    total_enabled,#总数开关 与其他几项互斥
    total_count#允许条数
    '''
    grouped_data = defaultdict(list)#通源钱包
    sum_data = []  # 小标签加起来的总数
    transfer_in = []  # 钓鱼钱包
    rat_trader = []  # 确定老鼠仓
    dev_team = []  # 开发团队
    seen_wallet_tags = set()  # 用来记录已经添加过的 wallet_tag_v2
    for item in data:
        from_address = item['native_transfer']['from_address']
        grouped_data[from_address].append(item)

        maker_token_tags = item.get('maker_token_tags', [])
        wallet_tag_v2 = item.get('wallet_tag_v2', '')

        # 钓鱼钱包
        if 'transfer_in' in maker_token_tags:
            transfer_in.append(item)
            if wallet_tag_v2 not in seen_wallet_tags:
                sum_data.append(item)
                seen_wallet_tags.add(wallet_tag_v2)

        # 老鼠仓
        if 'rat_trader' in maker_token_tags or item.get('is_suspicious', False):
            rat_trader.append(item)
            if wallet_tag_v2 not in seen_wallet_tags:
                sum_data.append(item)
                seen_wallet_tags.add(wallet_tag_v2)

        # 代币创建者 / 开发团队
        if any(tag in maker_token_tags for tag in ('creator', 'dev_team')):
            dev_team.append(item)
            if wallet_tag_v2 not in seen_wallet_tags:
                sum_data.append(item)
                seen_wallet_tags.add(wallet_tag_v2)
    #去重数据
    print(f"总数：{json.dumps(sum_data, indent=4, ensure_ascii=False)}")
    print(f"钓鱼钱包：{json.dumps(transfer_in, indent=4, ensure_ascii=False)}")
    print(f"老鼠仓：{json.dumps(rat_trader, indent=4, ensure_ascii=False)}")
    print(f"dev_team：{json.dumps(dev_team, indent=4, ensure_ascii=False)}")
    print(f"通源钱包：{json.dumps(grouped_data, indent=4, ensure_ascii=False)}")


    if total_enabled and len(sum_data) > total_count:#总开关开启时
        return True
    else:#计算单独开关
        if phishing_wallet_enabled and len(transfer_in) > phishing_wallet_count: #钓鱼钱包
            return True
        if insider_trading_edabled and len(rat_trader) > insider_trading_count: #老鼠仓
            return True
        if source_wallet_enabled: #同一个转账来源
            for from_address, items in grouped_data.items(): 
                if len(items) > source_wallet_count: return True
        if dev_team_enabled and len(dev_team) > dev_team_count:
            return True
    return False




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

