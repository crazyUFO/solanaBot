from datetime import datetime, timedelta
# 获取今天的日期并设置时间为 00:00:00
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# 昨天的 00:00:00
yesterday_start = today - timedelta(days=1)

# 转换为时间戳
yesterday_start_timestamp = int(yesterday_start.timestamp())
print("昨天 00:00:00 的时间戳（秒级）：", yesterday_start_timestamp,today.timestamp())
