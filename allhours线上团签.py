import requests
import time
import os
import re
import subprocess
import pandas as pd
from datetime import datetime

# ================== Git 推送配置 ==================
GITHUB_REPO = "Juineii/xdinaryheroes_xb0417"        # 请替换为您的仓库名
GITHUB_BRANCH = "main"                          # 分支名（main 或 master）
# GitHub Personal Access Token 优先从环境变量 GITHUB_TOKEN 读取

# 微店商品 API 的 URL 和参数
url = "https://thor.weidian.com/detail/getItemSkuInfo/1.0"
params = {
    "param": '{"itemId":"7734186234"}',  # 替换为你的商品ID
    "wdtoken": "c9a6734f&_=1762222730161"  # 替换为实际的token值
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Accept": "application/json, */*"
}

# 记录上次的库存数据，键为 SKU ID，值为库存数量
last_stock = {}
total_sales = {}

# CSV 文件名
CSV_FILE = "DONGHAE北京签售.csv"


# ================== Git 推送函数 ==================
def git_push_update():
    """
    将最新的 CSV 文件提交并推送到 GitHub
    """
    try:
        # 获取 GitHub Token（优先从环境变量读取）
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            print("⚠️ 环境变量 GITHUB_TOKEN 未设置，跳过 Git 推送")
            return

        # 构建带认证的远程仓库 URL
        remote_url = f"https://{token}@github.com/{GITHUB_REPO}.git"

        # 添加 CSV 文件到暂存区
        subprocess.run(['git', 'add', CSV_FILE], check=True, capture_output=True)

        # 检查是否有文件变化（避免空提交）
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
        if result.returncode != 0:
            # 有变化，提交
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"自动更新数据 {timestamp}"
            subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)

            # 推送到 GitHub（指定分支）
            subprocess.run(
                ['git', 'push', remote_url, f'HEAD:{GITHUB_BRANCH}'],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"✅ 已推送到 GitHub: {commit_msg}")
        else:
            print("⏭️ CSV 文件无变化，跳过推送")

    except subprocess.CalledProcessError as e:
        print(f"❌ Git 操作失败: {e.stderr if e.stderr else e}")
    except Exception as e:
        print(f"❌ 推送过程中发生错误: {e}")


# ================== CSV 存储函数（pandas） ==================
def record_to_csv(timestamp, product_name, stock_change_desc, single_sale):
    """
    使用 pandas 将库存变化记录追加到 CSV 文件，并触发 Git 推送
    timestamp: 时间字符串
    product_name: 商品名称（标题）
    stock_change_desc: 库存变化描述（如"初始库存: 100" 或 "50 -> 48"）
    single_sale: 单笔销量变化
    """
    try:
        columns = ["时间", "商品名称", "库存变化", "单笔销量"]

        # 如果文件存在，读取现有数据；否则创建空 DataFrame
        if os.path.exists(CSV_FILE):
            df_existing = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
        else:
            df_existing = pd.DataFrame(columns=columns)

        # 将新数据行转换为 DataFrame 并拼接
        new_row = pd.DataFrame([[timestamp, product_name, stock_change_desc, single_sale]], columns=columns)
        df_updated = pd.concat([df_existing, new_row], ignore_index=True)

        # 保存回 CSV（覆盖原文件），使用 utf-8-sig 编码
        df_updated.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

        # 触发 Git 推送
        git_push_update()

    except Exception as e:
        print(f"❌ 写入CSV失败: {e}")


def fetch_stock_and_titles():
    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        # 提取 SKU 信息
        sku_infos = data.get("result", {}).get("skuInfos", [])
        if not sku_infos:
            print("未找到 'skuInfos' 数据，可能数据结构发生变化或商品不存在")
            return []

        stock_data = []
        for sku in sku_infos:
            sku_info = sku.get("skuInfo", {})
            sku_id = sku_info.get("id", None)
            title = sku_info.get("title", "未知标题")
            stock = sku_info.get("stock", None)
            stock_data.append((sku_id, title, stock))

        return stock_data
    except Exception as e:
        print("请求时发生错误: %s" % str(e))
        return []


def monitor_stock(interval=10):
    global last_stock, total_sales
    print("开始监控多个商品的库存变化...")

    while True:
        try:
            current_data = fetch_stock_and_titles()

            if current_data:
                for sku_id, title, current_stock in current_data:
                    # 时间戳用于 CSV 存储
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    if sku_id not in last_stock:
                        # 初始化库存和总销量
                        last_stock[sku_id] = current_stock
                        total_sales[sku_id] = 0

                        # CSV 记录初始库存
                        stock_change_desc = f"初始库存: {current_stock}"
                        record_to_csv(now_str, title, stock_change_desc, 0)

                        # 打印内容（与原格式一致）
                        print(f"商品标题: {title}, SKU ID: {sku_id}, 初始库存: {current_stock}")

                    elif current_stock != last_stock[sku_id]:
                        # 库存变化时计算销量
                        stock_diff = last_stock[sku_id] - current_stock
                        if stock_diff > 0:
                            total_sales[sku_id] += stock_diff

                        # CSV 记录库存变化
                        stock_change_desc = f"{last_stock[sku_id]} -> {current_stock}"
                        record_to_csv(now_str, title, stock_change_desc, stock_diff)

                        # 打印内容（与原格式一致）
                        print(f"库存变化: {last_stock[sku_id]} -> {current_stock}, 销量: {stock_diff},")

                        # 更新记录
                        last_stock[sku_id] = current_stock

            else:
                print("无法获取当前商品的库存和标题数据，请检查请求是否正常。")

            time.sleep(interval)

        except KeyboardInterrupt:
            print("用户终止了库存监控。")
            break
        except Exception as e:
            print(f"监控时发生错误: {str(e)}")


if __name__ == "__main__":
    monitor_stock(interval=10)