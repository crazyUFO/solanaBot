import requests

# 设置你的 Telegram Bot Token 和聊天 ID
bot_token = '7601466837:AAHd9g8QJik3kLtjyRDq-OuYD9CcCWKAJR4'
chat_id = '@solanapostalert'  # 你可以是个人聊天 ID 或群聊的 ID
message = f''' <b>bold</b>, <strong>bold</strong>
<i>italic</i>, <em>italic</em>
<u>underline</u>, <ins>underline</ins>
<s>strikethrough</s>, <strike>strikethrough</strike>, <del>strikethrough</del>
<span class="tg-spoiler">spoiler</span>, <tg-spoiler>spoiler</tg-spoiler>
<b>bold <i>italic bold <s>italic bold strikethrough <span class="tg-spoiler">italic bold strikethrough spoiler</span></s> <u>underline italic bold</u></i> bold</b>
<a href="http://www.example.com/">inline URL</a>
<a href="tg://user?id=123456789">inline mention of a user</a>
<tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>
<code>inline fixed-width code</code>
<pre>pre-formatted fixed-width code block</pre>
<pre><code class="language-python">pre-formatted fixed-width code block written in the Python programming language</code></pre>

<blockquote expandable>Expandable block quotation started\nExpandable block quotation continued\nExpandable block quotation continued\nHidden by default part of the block quotation started\nExpandable block quotation continued\nThe last line of the block quotation</blockquote> '''

message2 = f'''
<b>🐋🐋🐋🐋鲸鱼钱包🐋🐋🐋🐋</b>

token:\n<code>2hRMCsXi9WSeZQxGTKckqDuDVRkuNbTtSzXVNv62oHkZ</code>

购买的老钱包:\n<code>2hRMCsXi9WSeZQxGTKckqDuDVRkuNbTtSzXVNv62oHkZ</code>

购买金额: {0.8888} SOL
钱包余额: {0.8888} SOL
钱包代币余额总计: {99999} USDT

查看钱包: <a href="https://solscan.io/account/2hRMCsXi9WSeZQxGTKckqDuDVRkuNbTtSzXVNv62oHkZ">SOLSCAN</a> <a href="https://gmgn.ai/sol/address/2hRMCsXi9WSeZQxGTKckqDuDVRkuNbTtSzXVNv62oHkZ">GMGN</a>

查看K线: <a href="https://pump.fun/coin/CvdacfViE9wvhpQThcpt5iENiXrFZZ7z4VMQR7Xypump">PUMP</a> <a href="https://gmgn.ai/sol/token/VqNpWUdf_CvdacfViE9wvhpQThcpt5iENiXrFZZ7z4VMQR7Xypump">GMGN</a>

'''

# 构造 API 请求 URL
url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

# 请求参数
params = {
    'chat_id': chat_id,
    'text': message2,
    "parse_mode":"HTML"
}

# 发送 GET 请求到 Telegram API
response = requests.get(url, params=params)

# 检查请求是否成功
if response.status_code == 200:
    print("Message sent successfully!")
else:
    print(f"Failed to send message. Error: {response.status_code}")
