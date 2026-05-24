# mirror-scout

批量抓取 Docker Hub / GitHub 镜像站并测试在当前环境下的可用性、下载速度的命令行工具。

## 功能

- **自动抓取**：从多个来源网页和 API 中提取候选镜像站 URL
- **真实测速**：通过 Docker Registry v2 API 实际拉取 blob 并计算下载速度
- **并发测试**：多线程并发测速，快速筛选出可用镜像
- **双模式**：支持 Docker 镜像站和 GitHub 加速站两种测速模式
- **自动维护**：测速结果自动保存到 `mirrors-docker.txt` / `mirrors-github.txt`，已有镜像优先保留，新镜像按速度追加

## 依赖

- Python 3.6+
- requests

```bash
pip install requests
```

## 安装

```bash
# 直接下载脚本
wget https://raw.githubusercontent.com/ryys1122/mirror-scout/main/mirror-scout.py

# 安装依赖
pip install requests
```

## 用法

### Docker 镜像站测速（默认模式）

```bash
# 自动抓取 + 已有镜像 + 测速，结果保存到 mirrors-docker.txt
python mirror-scout.py

# 跳过抓取，仅测试已有镜像
python mirror-scout.py --no-scrape

# 网络不好的环境先跳过抓取
python mirror-scout.py --no-scrape

# 自定义抓取来源 + 限制下载量
python mirror-scout.py --source https://example.com/mirrors.md --max-mb 5

# 只显示前 10 名
python mirror-scout.py --top 10
```

### GitHub 加速站测速

```bash
# 结果保存到 mirrors-github.txt
python mirror-scout.py --github

# 网络不通时跳过抓取
python mirror-scout.py --github --no-scrape
```

### 镜像文件说明

- `mirrors-docker.txt` — Docker 镜像站列表（默认模式自动读写）
- `mirrors-github.txt` — GitHub 加速站列表（`--github` 模式自动读写）
- 文件格式：每行一个 URL，`#` 开头为注释
- 每次运行后自动更新：已有且仍可用的镜像保持在前，新发现的按速度降序追加在后

## 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--source` | 内置列表 | 包含镜像站链接的网页，可重复传入 |
| `--mirror` | 无 | 手动指定镜像站 URL，可重复传入 |
| `--timeout` | 10 | 下载超时时间（秒） |
| `--connect-timeout` | 3 | 连接超时时间，DNS + TCP（秒） |
| `--workers` | 8 | 并发测试线程数 |
| `--max-mb` | 1 | 每个镜像最多下载 MB 数 |
| `--github` | False | 启用 GitHub 加速站模式（默认 Docker 模式） |
| `--no-scrape` | False | 跳过网页抓取，仅测试已有和手动指定的镜像 |
| `--top` | 0 | 只显示前 N 个成功的镜像站（0 表示全部） |

## 输出示例

```
Found 45 candidate mirrors
Test image: library/alpine:latest
Max download per mirror: 1 MB

OK   https://swr.cn-north-4.myhuaweicloud.com     12.34 MiB/s  latency 0.234s | tetools: 10.56 MiB/s
OK   https://docker.1panel.dev                      8.21 MiB/s  latency 0.512s | tetools: 7.89 MiB/s
FAIL https://hub.geekery.cn                         Network unreachable
FAIL https://docker-0.unsee.tech                    manifest status 404
...

=== Ranking by download speed ===
Rank  Speed          Latency       Mirror
1     12.34 MiB/s    0.234s        https://swr.cn-north-4.myhuaweicloud.com
2      8.21 MiB/s    0.512s        https://docker.1panel.dev
...

=== Usage examples ===
https://swr.cn-north-4.myhuaweicloud.com
     docker pull:      swr.cn-north-4.myhuaweicloud.com/library/alpine:latest
     singularity pull: docker://swr.cn-north-4.myhuaweicloud.com/library/alpine:latest

OK: 12 / FAIL: 8
Saved 12 mirrors to mirrors-docker.txt (8 kept, +4 new)
```

## 工作原理

1. **加载已有镜像**：从 `mirrors-docker.txt` 或 `mirrors-github.txt` 读取历史可用的镜像站
2. **抓取阶段**：从内置网页来源和 AITYP API 中用正则提取候选 URL，以关键词过滤
3. **DNS 预检**：每个镜像站用线程做 DNS 解析，超时直接跳过
4. **测速阶段**：通过 Docker Registry v2 协议获取 manifest → 解析 blob digest → 流式下载 blob 计算速度；GitHub 模式通过代理站下载测试文件
5. **排名输出**：按下载速度降序排列，自动生成使用命令
6. **保存结果**：已有镜像仍可用的保留原顺序在前，新镜像按速度降序追加在后
