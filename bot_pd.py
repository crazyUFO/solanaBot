from flask import Flask, request, jsonify
import telegram

# 初始化 Telegram Bot
BOT_TOKEN = "7601466837:AAHd9g8QJik3kLtjyRDq-OuYD9CcCWKAJR4"  # 替换为你的 Telegram Bot Token
CHANNEL_ID = "@solanapostalert"  # 或者使用 Chat ID，例如：-100xxxxxxxxxx
bot = telegram.Bot(token=BOT_TOKEN)

app = Flask(__name__)


@app.route('/send_message', methods=['POST'])
async def send_message():
    try:
        print(request)
        # 确保 JSON 数据被正确解析
        data = request.json
        
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid JSON data'}), 400
        
        message = data.get('message')

         # 使用 Telegram Bot 发送消息
        await bot.send_message(chat_id=CHANNEL_ID, text=message)

        return jsonify({'status': 'success', 'message': 'Message sent successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000)
