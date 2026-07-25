import time
import requests
from bs4 import BeautifulSoup

# 读取待检查的网址列表
with open("links.txt", "r", encoding="utf-8") as file:
    links = file.readlines()

# 创建爬取报告；w 表示每次运行都重新生成
with open("crawl_results.txt", "w", encoding="utf-8") as result_file:

    # 依次处理 links.txt 中的每个网址
    for link in links:
        # 删除每行首尾的空格和换行符
        url = link.strip()

        # 跳过空行
        if not url:
            continue

        try:
            # 访问当前网页
            response = requests.get(url, timeout=10)
            # 如果状态码表示请求失败，就抛出异常，交给下面的 except 处理
            response.raise_for_status()


            # raise_for_status() 不处理 999 这类非标准状态码，
            # 因此额外规定：状态码大于等于 400 就视为失败
            if response.status_code >= 400:
                raise requests.HTTPError(
                    f"服务器返回非成功状态码：{response.status_code}"
                )

            # 解析网页返回的 HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # 有 <title> 时提取标题，否则使用“无标题”
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            else:
                title = "无标题"

            # 在终端显示状态码、标题和网址
            print(response.status_code, title, url)

            # 把爬取结果写入报告文件
            result_file.write(
                f"状态码：{response.status_code} | 标题：{title} | 网址：{url}\n"
            )

        except requests.RequestException as error:
            # 某个网址失败时记录错误，继续处理下一个网址
            print("访问失败：", url)
            result_file.write(f"访问失败 | 网址：{url} | 错误：{error}\n")

        # 每访问一个网页后暂停1秒
        time.sleep(1)