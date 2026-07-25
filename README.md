# 公众人物公开信息聚合器

这是一个学习用途的基础爬虫。它从你明确指定的公开网页开始，在允许的域名内查找与某位公众人物相关的页面，并将标题、日期、上下文摘要和原始链接保存为 CSV。


## 环境准备

建议使用 Python 3.10 或更高版本。

在 PowerShell 中创建并激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装项目依赖：

```powershell
python -m pip install -r requirements.txt
```

## 使用方法

1. 复制 `config.example.json` 为 `config.json`。
2. 填写人物姓名、别名、起始网页和允许访问的域名。
3. 在 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe crawler.py --config config.json
```

结果默认保存在 `data/public_figure.csv`，可直接用 Excel 打开。

## 配置说明

- `person`：需要检索的公众人物姓名。
- `aliases`：英文名、艺名等公开别名。
- `seed_urls`：爬虫的起始页面。请填写具体的官方网站、机构页面或允许抓取的新闻栏目，不要填写搜索引擎结果页。
- `allowed_domains`：允许继续访问的域名白名单。
- `max_pages`：一次最多检查的页面数，上限为 500。
- `max_pages_per_domain`：每个域名最多检查的页面数，防止单个网站占满全部名额。
- `follow_links`：是否继续访问页面内的链接。人物资料聚合建议设为 `false`，只采集人工核实过的起始页面。
- `delay_seconds`：两次页面访问间隔，程序最低限制为 0.5 秒。
- `output_csv`：结果文件位置。

## 使用边界

- 仅采集无需登录即可查看、与公众身份有关且来源可核实的信息。
- 遵守网站服务条款、版权要求和 `robots.txt`。
- 不绕过验证码、登录、付费墙或其他访问控制。
- 不收集或推断住址、电话、证件、家属行踪、实时位置等敏感信息。
- CSV 中始终保留来源链接；发布内容前应人工核实。

不同网站的正文结构差异很大。当前版本采用通用 HTML 提取，适合先验证流程；后续可以为明确允许采集的网站增加专用解析器。
