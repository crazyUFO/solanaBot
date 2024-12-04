from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import re

# 模拟保存用户设置的接口函数
async def save_user_setting(user_id, setting_name, value):
    # 模拟接口调用，实际中应该是API请求或数据库保存
    print(f"用户 {user_id} 设置了 {setting_name}: {value}")
    # 这里可以调用实际接口来保存设置
    return True  # 假设保存成功

# 定义 "/start" 命令的处理函数
async def start(update: Update, context):
    await update.message.reply_text("可输入 /set 进行自定义设置")

# 定义 "/set" 命令的处理函数
async def set(update: Update, context):
    # 创建一级菜单
    keyboard = [
        [InlineKeyboardButton("tokens的数量>=", callback_data='tokenNum')],
        [InlineKeyboardButton("余额SOL的数量>=", callback_data='solNum')],
        [InlineKeyboardButton("多久没交易(天)>=", callback_data='dayNum')],
        [InlineKeyboardButton("单笔买入(sol)>=", callback_data='sigleNum')],
        # [InlineKeyboardButton("监听开关", callback_data='isOff')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("设置监听参数\n默认参数:\n tokens >= 10000 \n 或 \n sol余额 >= 100 \n --------------------- \n 交易间隔 >= 3(天) \n 单笔买入 >= 0.5(sol)", reply_markup=reply_markup)
msg_map={
    "trade_days":"交易间隔",
    "tokens":"tokens代币余额",
    "sol_balance":"SOL余额",
    "single_trade":"单笔买入"
}
#用户输入的正则
def is_valid_number(input_string: str) -> bool:
    pattern = r'^\d+(\.\d+)?$'
    return bool(re.match(pattern, input_string))
# 用户输入处理函数
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 获取用户ID
    user_id = update.message.chat_id
    user_message = update.message.text

    if not 'waiting_for_setting' in context.user_data:
        await update.message.reply_text("没有在进行任何设置。")
        return
    setting_name = context.user_data['waiting_for_setting']  # 获取当前设置名称
    if not is_valid_number(user_message):
        await update.message.reply_text(f"{msg_map[setting_name]} 的参数设置错误")
        return
    await save_user_setting(user_id, setting_name, user_message)
    await update.message.reply_text(f"你成功设置了监听参数 {msg_map[setting_name]} 为 {user_message}")
    del context.user_data['waiting_for_setting']  # 清除状态

# 各个按钮回调函数
async def tokenNum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 用户点击了 tokens 数量按钮
    await update.callback_query.answer()  # 确保回调被确认
    await update.callback_query.message.reply_text("请输入 tokens 的数量：")
    context.user_data['waiting_for_setting'] = 'tokens'  # 设置用户正在设置 tokens 数量

async def solNum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 用户点击了 sol 余额按钮
    await update.callback_query.answer()  # 确保回调被确认
    await update.callback_query.message.reply_text("请输入 SOL 余额：")
    context.user_data['waiting_for_setting'] = 'sol_balance'  # 设置用户正在设置 SOL 余额

async def dayNum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 用户点击了交易间隔按钮
    await update.callback_query.answer()  # 确保回调被确认
    await update.callback_query.message.reply_text("请输入交易间隔（天数）：")
    context.user_data['waiting_for_setting'] = 'trade_days'  # 设置用户正在设置交易间隔

async def sigleNum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 用户点击了单笔交易按钮
    await update.callback_query.answer()  # 确保回调被确认
    await update.callback_query.message.reply_text("请输入单笔买入的 SOL 数量：")
    context.user_data['waiting_for_setting'] = 'single_trade'  # 设置用户正在设置单笔买入

async def isOff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 用户点击了开关按钮
    await update.callback_query.answer()  # 确保回调被确认
    await update.callback_query.message.reply_text("请输入开关状态（开或关）：")
    context.user_data['waiting_for_setting'] = 'switch_status'  # 设置用户正在设置开关状态

# 主函数：初始化机器人并添加命令和消息处理器
def main():
    # 替换为从 BotFather 获取的 Token
    token = "8099568962:AAGXfnBs8tXQ5DomqW1eTHg5k938vClfPjM"
    app = ApplicationBuilder().token(token).build()

    # 添加处理器
    app.add_handler(CommandHandler("set", set))  # 处理 /set 命令
    app.add_handler(CommandHandler("start", start))  # 处理 /start 命令
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))  # 处理用户输入
    app.add_handler(CallbackQueryHandler(tokenNum, pattern='tokenNum'))  # tokens 数量按钮
    app.add_handler(CallbackQueryHandler(solNum, pattern='solNum'))  # SOL 余额按钮
    app.add_handler(CallbackQueryHandler(dayNum, pattern='dayNum'))  # 交易间隔按钮
    app.add_handler(CallbackQueryHandler(sigleNum, pattern='sigleNum'))  # 单笔交易按钮
    app.add_handler(CallbackQueryHandler(isOff, pattern='isOff'))  # 开关按钮

    # 启动机器人
    print("机器人已启动！按 Ctrl+C 停止。")
    app.run_polling()

if __name__ == "__main__":
    main()
