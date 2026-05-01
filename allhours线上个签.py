import requests
import time
import os
import re
import subprocess
import pandas as pd
from datetime import datetime

# ================== Git 推送配置 ==================
GITHUB_REPO = "Juineii/lngshot_bs0411"        # 请替换为您的仓库名
GITHUB_BRANCH = "main"                          # 分支名（main 或 master）
# GitHub Personal Access Token 优先从环境变量 GITHUB_TOKEN 读取

# 微店商品 API 的 URL 和参数
url = "https://thor.weidian.com/detail/getItemSkuInfo/1.0"
params = {
    "param": '{"itemId":"7728945581"}',  # 替换为你的商品ID
    "wdtoken": "ba054937&_=1774182332591"  # 替换为实际的token值
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Accept": "application/json, */*"
}

# 记录上次的库存数据，键为 (member, sku_id) 元组，值为库存数量
last_stock = {}

# 创建主文件夹用于保存CSV文件
main_log_folder = "D:\\fansign\\ing"
os.makedirs(main_log_folder, exist_ok=True)


# ================== Git 推送函数 ==================
def git_push_update(file_path):
    """
    将指定的 CSV 文件提交并推送到 GitHub
    """
    try:
        # 获取 GitHub Token（优先从环境变量读取）
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            print("⚠️ 环境变量 GITHUB_TOKEN 未设置，跳过 Git 推送")
            return

        # 构建带认证的远程仓库 URL
        remote_url = f"https://{token}@github.com/{GITHUB_REPO}.git"

        # 添加指定 CSV 文件到暂存区
        subprocess.run(['git', 'add', file_path], check=True, capture_output=True)

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
            # 无变化，不提交
            pass

    except subprocess.CalledProcessError as e:
        print(f"❌ Git 操作失败: {e.stderr if e.stderr else e}")
    except Exception as e:
        print(f"❌ 推送过程中发生错误: {e}")


def clean_filename(name):
    name = name.strip()
    cleaned_name = re.sub(r'[\\/*?:"<>|\n\r\t]', '_', name)
    cleaned_name = cleaned_name.strip('.')
    if not cleaned_name:
        cleaned_name = "未命名"
    return cleaned_name


def setup_member_csv(member, title):
    cleaned_member = clean_filename(member)
    cleaned_title = clean_filename(title)
    csv_file = os.path.join(main_log_folder, f"{cleaned_member}_{cleaned_title}.csv")
    return csv_file


def write_to_csv(file_path, data_dict, log_message):
    """
    使用 pandas concat 方式写入 CSV，并触发 Git 推送
    """
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_dict['时间'] = current_time

        # 定义列名
        columns = ['时间', '商品名称', '库存变化', '单笔销量']

        # 1. 如果文件存在，读取现有数据；否则创建空 DataFrame
        if os.path.exists(file_path):
            df_existing = pd.read_csv(file_path, encoding='utf-8-sig')
        else:
            df_existing = pd.DataFrame(columns=columns)

        # 2. 将新数据行转换为 DataFrame 并拼接
        new_row = pd.DataFrame([{
            '时间': data_dict['时间'],
            '商品名称': data_dict['商品名称'],
            '库存变化': data_dict['库存变化'],
            '单笔销量': data_dict['单笔销量']
        }], columns=columns)
        df_updated = pd.concat([df_existing, new_row], ignore_index=True)

        # 3. 保存回 CSV（覆盖原文件），使用 utf-8-sig 编码
        df_updated.to_csv(file_path, index=False, encoding='utf-8-sig')

        # 4. 打印日志（与原格式一致）
        print(f"{current_time} - {log_message}")

        # 5. 触发 Git 推送
        git_push_update(file_path)

    except Exception as e:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{current_time} - ERROR - 无法写入CSV文件: {str(e)}")


def get_member_from_attrs(attr_ids, attr_list):
    attr_id_to_member = {}
    for attr in attr_list:
        attr_title = attr.get("attrTitle")
        if attr_title == "MEMBER":
            attr_values = attr.get("attrValues", [])
            for attr_value in attr_values:
                attr_id = attr_value.get("attrId")
                attr_value_str = attr_value.get("attrValue")
                attr_id_to_member[str(attr_id)] = attr_value_str
            break

    for attr_id in attr_ids:
        str_attr_id = str(attr_id)
        if str_attr_id in attr_id_to_member:
            return attr_id_to_member[str_attr_id]

    return "未知成员"


def fetch_stock_and_member_data():
    try:
        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        sku_infos = data.get("result", {}).get("skuInfos", [])
        attr_list = data.get("result", {}).get("attrList", [])

        if not sku_infos:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{current_time} - ERROR - 未找到 'skuInfos' 数据，可能数据结构发生变化或商品不存在")
            return []

        item_title = data.get("result", {}).get("itemTitle", "未知商品")

        stock_data = []
        for sku in sku_infos:
            sku_info = sku.get("skuInfo", {})
            sku_id = sku_info.get("id", None)
            stock = sku_info.get("stock", None)
            attr_ids = sku.get("attrIds", [])
            member = get_member_from_attrs(attr_ids, attr_list)
            stock_data.append((member, sku_id, item_title, stock))

        return stock_data
    except Exception as e:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{current_time} - ERROR - 请求时发生错误: {str(e)}")
        return []


def monitor_stock_by_member(interval=10):
    global last_stock

    while True:
        try:
            current_data = fetch_stock_and_member_data()

            if current_data:
                for member, sku_id, title, current_stock in current_data:
                    if member == "未知成员":
                        continue

                    csv_file = setup_member_csv(member, title)
                    key = (member, sku_id)

                    if key not in last_stock:
                        last_stock[key] = current_stock
                        excel_data = {
                            '商品名称': f"{title}",
                            '库存变化': f"初始库存: {current_stock}",
                            '单笔销量': 0
                        }
                        log_message = f"成员: {member}, 商品标题: {title}, SKU ID: {sku_id}, 初始库存: {current_stock}"
                        write_to_csv(csv_file, excel_data, log_message)

                    elif current_stock != last_stock[key]:
                        stock_diff = last_stock[key] - current_stock
                        excel_data = {
                            '商品名称': f"{title}",
                            '库存变化': f"{last_stock[key]} -> {current_stock}",
                            '单笔销量': stock_diff
                        }
                        if stock_diff > 0:
                            action = "销售"
                        elif stock_diff < 0:
                            action = "补货"
                        else:
                            action = "无变化"
                        log_message = f"成员: {member}, {action}: {abs(stock_diff)}, 库存变化: {last_stock[key]} -> {current_stock}"
                        write_to_csv(csv_file, excel_data, log_message)
                        last_stock[key] = current_stock

            else:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"{current_time} - ERROR - 无法获取当前商品的库存和标题数据，请检查请求是否正常。")

            time.sleep(interval)

        except KeyboardInterrupt:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{current_time} - 用户终止了库存监控。")
            break
        except Exception as e:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{current_time} - ERROR - 监控时发生错误: {str(e)}")


if __name__ == "__main__":
    monitor_stock_by_member(interval=10)