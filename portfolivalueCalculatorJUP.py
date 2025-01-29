import concurrent.futures
from helius import BalancesAPI
import requests
import time

class PortfolioValueCalculatorJUP:
    def __init__(self,account_address="",balances_api_key=""):
        # 使用 API 密钥和账户地址初始化
        self.account_address = account_address
        self.balances_api_key = balances_api_key
        self.balances_api = BalancesAPI(self.balances_api_key)
        self.nativeBalance = 0
        self.tokens = []
        
    def get_non_zero_balances(self):
        """
        获取并过滤掉余额为零的代币。
        返回包含 mint 地址和余额的代币列表。
        """
        data = self.balances_api.get_balances(self.account_address)
        self.nativeBalance = data['nativeBalance']
        # 过滤出余额不为零的代币，并根据 decimals 调整余额
        non_zero_balances = [
            {
                "mint": token["mint"],
                "amount": token["amount"] / (10 ** token.get("decimals", 0)),  # 处理缺失的 decimals 字段
            }
            for token in data["tokens"]
            if token["amount"] > 0
        ]
        self.tokens = non_zero_balances
        return non_zero_balances

    def chunk_mints(self, tokens, chunk_size=20):
        """
        将 mint 地址分割成更小的组。
        """
        return [tokens[i:i + chunk_size] for i in range(0, len(tokens), chunk_size)]

    def fetch_price_chunk(self, chunk, retries=3):
        """
        获取一组 mint 地址的代币价格。
        在失败时会重试指定的次数。
        """
        mint_list = ",".join(chunk)
        url = f"https://api.jup.ag/price/v2?ids={mint_list}"

        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=10)  # 设置超时防止请求挂起
                response.raise_for_status()  # 如果返回的状态码不是 200，会抛出异常
                data = response.json()
                token_prices = data.get("data", {})
                return {mint: float(price.get('price',0)) for mint, price in token_prices.items() if price}
            except requests.exceptions.RequestException as e:
                print(f"第 {attempt + 1} 次请求失败，代币 {chunk}，错误: {e}")
                if attempt < retries - 1:
                    time.sleep(2)  # 等待 2 秒后重试
                else:
                    print(f"代币 {chunk} 在 {retries} 次尝试后仍然失败。")
        return {}

    def get_prices_for_mints(self, mint_chunks):
        """
        获取所有 mint 地址对应的代币价格，使用并行请求加速。
        """
        prices = {}

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = list(executor.map(self.fetch_price_chunk, mint_chunks))
        
        # 合并所有请求结果到 prices 字典中
        for result in results:
            prices.update(result)

        return prices

    def calculate_total_value(self):
        """
        根据非零余额和代币价格计算投资组合的总价值。
        """
        non_zero_balances = self.get_non_zero_balances()
        
        # 提取 mint 地址
        mints = [token["mint"] for token in non_zero_balances]

        # 将 mint 地址分割成小块，以便并行请求价格
        mint_chunks = self.chunk_mints(mints, chunk_size=100)

        # 获取所有 mint 地址的代币价格
        mint_prices = self.get_prices_for_mints(mint_chunks)

        # 计算投资组合的总价值
        total_value = 0
        for token in non_zero_balances:
            mint = token["mint"]
            amount = token["amount"]
            price = mint_prices.get(mint, 0)  # 如果没有找到价格，则默认为 0
            total_value += amount * price

        return total_value

    def get_sol(self):
        return self.nativeBalance / (10 **9)
    
    def get_tokens(self):
        return self.tokens