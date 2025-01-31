#老鲸鱼的模版
def tg_message_html_1(item):
# <b>代币市值:{market_cap:.4f}</b>
# <b>黑盘占比:{alert_data:.2f}%</b>
    msg = '''
<b>🐋🐋🐋🐋{title}🐋🐋🐋🐋</b>

<b>代币地址:</b>
<code>{mint}</code>

<b>钱包地址:</b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f}</b>
<b>钱包余额:{sol:.4f}</b>
<b>代币余额:{total_balance:.4f}</b>

<b>钱包信息:</b>
<b><a href="https://solscan.io/account/{traderPublicKey}">SOLSCAN</a> <a href="https://gmgn.ai/sol/address/{traderPublicKey}">GMGN</a></b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a> <a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<b>交易签名:<a href="https://solscan.io/tx/{signature}">查看</a></b>
<code>{signature}</code>
    '''.format(
        title=item.get("title"),
        mint=item.get("mint"),
        traderPublicKey=item.get("traderPublicKey"),
        amount=float(item.get("solAmount", 0.0)),
        sol=float(item.get("sol", 0.0)),
        # market_cap = float(item.get('market_cap',0)),
        # alert_data = float(item.get('alert_data',0)) * 100,
        total_balance=float(item.get("total_balance", 0.0)),
        signature=item.get("signature")
    )
    return msg


#老鲸鱼暴击的模版2
def tg_message_html_2(info):
#     <b>总盈亏: {total_profit:.4f} USDT</b>
# <b>30d盈亏: {realized_profit_30d:.4f} USDT</b>
# <b>7d盈亏: {realized_profit_7d:.4f} USDT</b>
    msg = '''
<b>🐋🐋🐋🐋{title}🐋🐋🐋🐋</b>

<b>token:</b>
<code>{mint}</code>

<b>购买的老钱包:</b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f} SOL</b>
<b>钱包余额: {balance:.4f} SOL</b>



<b>链上查看钱包: <a href="https://solscan.io/account/{traderPublicKey}">详情</a></b>
<b>GMGN查看钱包: <a href="https://gmgn.ai/sol/address/{traderPublicKey}">详情</a></b>
<b>交易详情:<a href="https://solscan.io/tx/{signature}">查看</a></b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a></b> <b><a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<a href="https://t.me/pepeboost_sol_bot?start=8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>PEPE一键买入</b></a>

<a href="https://t.me/sol_dbot?start=ref_73848156_8rH1o8mhtjtH14kccygYkfBsp9ucQfnMuFJBCECJpump"><b>DBOX一键买入</b></a>
    '''.format(
        mint = info.get("mint"),
        title=info.get("title"),
        amount=info.get('solAmount',0),
        signature = info.get('signature'),
        traderPublicKey=info.get("traderPublicKey"),
        balance=float(info.get("balance", 0)),
        #total_profit=float(info.get("total_profit", 0)),
        #realized_profit_30d=float(info.get("realized_profit_30d", 0)),
        #realized_profit_7d=float(info.get("realized_profit_7d", 0)),
    )
    return msg
#老鲸鱼暴击的模版
def tg_message_html_3(info):
# <b>黑盘占比:{alert_data:.2f}%</b>
    msg = '''
<b>💥💥💥💥{title}💥💥💥💥</b>

<b>代币地址:</b>
<code>{mint}</code>

<b>钱包地址:</b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f}</b>
<b>代币市值:{market_cap:.4f}</b>


<b>钱包信息:</b>
<b><a href="https://solscan.io/account/{traderPublicKey}">SOLSCAN</a> <a href="https://gmgn.ai/sol/address/{traderPublicKey}">GMGN</a></b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a> <a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<b>交易签名:<a href="https://solscan.io/tx/{signature}">查看</a></b>
<code>{signature}</code>
    '''.format(
        mint = info.get("mint"),
        title=info.get("title"),
        amount=float(info.get('solAmount',0)),
        #realized_profit = float(info.get('realized_profit',0)),
        #realized_pnl = float(info.get('realized_pnl',0)) * 100,#盈利百分比
        #alert_data = float(info.get('alert_data',0)) * 100,
        market_cap = float(info.get('market_cap',0)),
        signature = info.get('signature'),
        traderPublicKey=info.get("traderPublicKey"),
    )
    return msg
#新版15天钱包模板
def tg_message_html_4(info):
    # <b>黑盘占比:{alert_data:.2f}%</b>
    msg = '''
<b>🔥🔥🔥🔥{title}🔥🔥🔥🔥</b>

<b>代币地址:</b>
<code>{mint}</code>

<b>上次钱包:<a href="https://solscan.io/account/{traderPublicKeyOld}">SOLSCAN</a> <a href="https://gmgn.ai/sol/address/{traderPublicKeyOld}">GMGN</a></b>
<code>{traderPublicKeyOld}</code>
<b>本次钱包:<a href="https://solscan.io/account/{traderPublicKey}">SOLSCAN</a> <a href="https://gmgn.ai/sol/address/{traderPublicKey}">GMGN</a></b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f}</b>
<b>代币市值:{market_cap:.4f}</b>


📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a> <a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<b>交易详情:<a href="https://solscan.io/tx/{signature}">查看</a></b>
<code>{signature}</code>
    '''.format(
        mint = info.get("mint"),
        title=info.get("title"),
        amount=float(info.get('solAmount',0)),
        market_cap = float(info.get('market_cap',0)),
        #alert_data = float(info.get('alert_data',0)) * 100,
        signature = info.get('signature'),
        traderPublicKey=info.get("traderPublicKey"),
        traderPublicKeyOld = info.get("traderPublicKeyOld","--"),
    )
    return msg

#新版老钱包转账
def tg_message_html_5(info):
    msg = '''
<b>🌟🌟🌟🌟{title}🌟🌟🌟🌟</b>

<b>代币地址:</b>
<code>{mint}</code>

<b>上级钱包:<a href="https://solscan.io/account/{traderPublicKeyParent}">SOLSCAN</a> <a href="https://gmgn.ai/sol/address/{traderPublicKeyParent}">GMGN</a></b>
<code>{traderPublicKeyParent}</code>
<b>购买钱包:<a href="https://solscan.io/account/{traderPublicKey}">SOLSCAN</a> <a href="https://gmgn.ai/sol/address/{traderPublicKey}">GMGN</a></b>
<code>{traderPublicKey}</code>

<b>购买金额:{amount:.4f}</b>
<b>代币市值:{market_cap:.4f}</b>

📈<b>查看K线: <a href="https://pump.fun/coin/{mint}">PUMP</a> <a href="https://gmgn.ai/sol/token/{mint}">GMGN</a></b>

<b>交易详情:<a href="https://solscan.io/tx/{signature}">查看</a></b>
<code>{signature}</code>
    '''.format(
        mint = info.get("mint"),
        title=info.get("title"),
        amount=float(info.get('solAmount',0)),
        total_balance = float(info.get('total_balance',0)),
        sol = float(info.get('sol',0)),
        market_cap = float(info.get('market_cap',0)),
        signature = info.get('signature'),
        traderPublicKey=info.get("traderPublicKey"),
        traderPublicKeyParent = info.get("traderPublicKeyParent","--"),
    )
    return msg