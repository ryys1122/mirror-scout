# mirror-scout

批量抓取 Docker Hub / GitHub 镜像站并测试在当前环境下的可用性、下载速度的命令行工具。

## 功能

- **自动抓取**：从多个来源网页和 API 中提取候选镜像站 URL
- **真实测速**：通过 Docker Registry v2 API 实际拉取 blob 并计算下载速度
- **并发测试**：多线程并发测速，快速筛选出可用镜像
- **双模式**：支持 Docker 镜像站和 GitHub 加速站两种测速模式

## 依赖

- Python 3.6+
- requests

```bash
pip install requests
```

## 用法

### Docker 镜像站测速（默认模式）

```bash
# 自动抓取候选镜像站并测速
python mirror-scout.py

# 跳过抓取，仅测试手动指定的镜像站
python mirror-scout.py --no-scrape --mirror https://docker.1panel.dev

# 自定义抓取来源 + 限制下载量
python mirror-scout.py --source https://example.com/mirrors.md --max-mb 5

# 只显示前 10 名
python mirror-scout.py --top 10
```

### GitHub 加速站测速

```bash
python mirror-scout.py --github
```

### 使用自定义可靠镜像列表

```bash
# mirrors.txt 中每行一个 URL，# 开头的行为注释
python mirror-scout.py --reliable-list mirrors.txt
```

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
| `--reliable-list` | 无 | 自定义可靠镜像站列表文件路径 |
| `--no-scrape` | False | 跳过网页抓取，仅测试手动指定的镜像 |
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

=== Pull commands for OK mirrors ===
1     https://swr.cn-north-4.myhuaweicloud.com
      docker pull:      swr.cn-north-4.myhuaweicloud.com/library/alpine:latest
      singularity pull: docker://swr.cn-north-4.myhuaweicloud.com/library/alpine:latest
```

## 工作原理

1. **抓取阶段**：从内置网页来源和 AITYP API 中用正则提取候选 URL，以关键词过滤（含 `docker`、`registry`、`mirror` 的域名）
2. **DNS 预检**：每个镜像站用线程做 DNS 解析，超时直接跳过
3. **测速阶段**：通过 Docker Registry v2 协议获取 manifest → 解析 blob digest → 流式下载 blob 计算速度；GitHub 模式则通过代理站下载测试文件
4. **排名输出**：按下载速度降序排列，自动生成镜像的使用命令

