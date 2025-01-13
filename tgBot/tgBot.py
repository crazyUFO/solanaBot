from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import requests  # 用于发送 Telegram API 请求

# 你创建的 Bot Token
TOKEN = '7939824480:AAHNi55APfrU4Zh6AfQmwcFMyEizjas9vcU'

def reply_message(update: Update, context: CallbackContext) -> None:
    if getattr(update, 'message', None):  # 安全地检查 message
        print("这是普通消息:", update.message.text)

    elif getattr(update, 'channel_post', None):  # 安全地检查 channel_post
        print(update.channel_post)
        sender_chat_username = update.channel_post.sender_chat.username 
        if sender_chat_username in ['jiaoyisuolahei','jiaoyisuolahei2','qianbaolahei']: #特定频道
            parts = update.channel_post.text.split()
            if len(parts) == 2:
                action = parts[0]  # 动作部分
                identifier = parts[1]  # ID 部分
                if action == '拉黑':
                    status = put_in_black(address=identifier,sender_chat_username=sender_chat_username)
                    if status == 201:
                        update.channel_post.reply_text(f"添加成功")
                    elif status == 409:
                        update.channel_post.reply_text(f"地址已存在")
                    else:
                        update.channel_post.reply_text(f"添加失败")
                else:
                    update.channel_post.reply_text(f"不能识别的命令 {action}")
            else:
              update.channel_post.reply_text(f"命令格式不正确")

def put_in_black(address,sender_chat_username):#拉黑
    data = {"walletAddress":address,"label":"TG操作"}
    if sender_chat_username == 'jiaoyisuolahei' or sender_chat_username == 'jiaoyisuolahei2':#交易所拉黑
        data['type'] = 1
    elif sender_chat_username == 'qianbaolahei':#钱包拉黑
        data['type'] = 2
    response = requests.post(
        "http://hidog.fun/api/exchange-wallets",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data
    )
    return response.status_code     


def main():
    """ 启动机器人并监听消息 """
    updater = Updater(TOKEN)

    dispatcher = updater.dispatcher

    # 设置消息处理器，处理所有的文本消息
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, reply_message))

    # 启动机器人
    updater.start_polling()

    # 运行直到按 Ctrl+C 停止
    updater.idle()

if __name__ == '__main__':
    main()
