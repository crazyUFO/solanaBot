import requests
class ServerFun:
    def __init__(self,domain=""):
        # 使用 API 密钥和账户地址初始化
        self.domain = domain
        self.headers = {"Content-Type": "application/json"}

    def saveTransaction(self, data: dict) -> dict:
        """
        Gets info on a token.
        """
        if not data:
            return "data 参数无效"
        url = f"{self.domain}/api/wallet-transactions"
        params = {
            "ca": data['mint'],
            "walletAddress": data['traderPublicKey'],
            "purchaseAmount": data['amount'],
            "tokenMarketValue": data['market_cap'],
            "tokenMarketValueHeight": data['market_cap'],
            "blackMarketRatio": data['alert_data'],
            "type": data['type'],
            "transactionSignature": data['signature'],
            "tokenSymbol": data['symbol'],
            "isSentToExchange": data['isSentToExchange'],
            "data":data
        }
        response = requests.post(
            url,
            headers=self.headers,
            json=params
        )
        return response
    
    def getExchangeWallets(self) -> dict:
        """
        获取拉黑的交易所地址
        """
        url = f"{self.domain}/api/exchange-wallets"
        response = requests.get(url)
        return response
    
    def getConfigById(self,server_id: int = None) -> dict:
        """
        获取拉黑的交易所地址
        """
        if not server_id:
           return "server_id 参数无效"
        url = f"{self.domain}/api/nodes/{server_id}"
        response = requests.get(url)
        return response
        
    
    