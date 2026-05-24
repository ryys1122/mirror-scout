#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import concurrent.futures as cf
import json
import re
import socket
import threading
import time
from urllib.parse import urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("缺少 requests，请先运行：pip install requests")
    raise

# 禁用 requests 自动重试
_retry = Retry(total=0, backoff_factor=0, status_forcelist=[])
_session = requests.Session()
_session.mount("http://", HTTPAdapter(max_retries=_retry))
_session.mount("https://", HTTPAdapter(max_retries=_retry))


def quick_dns_check(url, connect_timeout):
    """用线程预检 DNS，超时直接返回 False 避免阻塞。"""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False

    port = 443 if parsed.scheme == "https" else 80

    result = [None]

    def resolve():
        try:
            socket.getaddrinfo(host, port)
            result[0] = True
        except Exception:
            result[0] = False

    t = threading.Thread(target=resolve)
    t.daemon = True
    t.start()
    t.join(timeout=connect_timeout)

    return result[0] if result[0] is not None else False


# ── Docker Hub mirror constants ──
TEST_IMAGE = "library/alpine"
AITYP_TEST_IMAGE = "ddn-k8s/docker.io/library/alpine"
TEST_IMAGE2 = "dfam/tetools"
AITYP_TEST_IMAGE2 = "ddn-k8s/docker.io/dfam/tetools"
TEST_TAG = "latest"

DEFAULT_SOURCES = [
    "https://mirror.kentxxq.com/image",
#    "https://status.anye.xyz",
#    "https://docker.mcya.cn",
    "https://ghfast.top/https://raw.githubusercontent.com/dongyubin/DockerHub/main/README.md",
    "https://ghfast.top/https://raw.githubusercontent.com/Loongphy/docker-mirror-speedtest/main/README.md",
    "https://ghfast.top/https://raw.githubusercontent.com/shengjunyang/DockerHub-proxy/main/README.md",
    "https://cloud.tencent.com/developer/article/2485043",
#    "https://zhuanlan.zhihu.com/p/2025958413599798943",
]

MIRROR_FILE_DOCKER = "mirrors-docker.txt"
MIRROR_FILE_GITHUB = "mirrors-github.txt"

AITYP_API_SOURCES = [
    "https://docker.aityp.com/api/v1/latest",
    "https://docker.aityp.com/api/v1/today",
]

# ── 自定义可靠镜像站（始终参与测试，不受抓包影响） ──
RELIABLE_DOCKER_MIRRORS = [
    "https://swr.cn-north-4.myhuaweicloud.com",
    "https://wget.la",
]

RELIABLE_GH_MIRRORS = [
    "https://ghfast.top",
    #"https://mirror.ghproxy.com",
    "https://wget.la"
]

# ── GitHub mirror constants ──
GH_TEST_URL = "https://github.com/samtools/samtools/releases/download/1.22.1/samtools-1.22.1.tar.bz2"
GH_TEST_FILE = "samtools-1.22.1.tar.bz2"

GH_DEFAULT_SOURCES = [
    #"https://mirror.ghproxy.com",
    "https://ghproxy.link",
    "https://github.akams.cn",
    "https://ghfast.top/https://raw.githubusercontent.com/XIU2/UserScript/master/GithubEnhanced-High-Speed-Download.user.js",
]

HEADERS = {
    "User-Agent": "DockerMirrorSpeedTest/1.0",
    "Accept": ",".join([
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.oci.image.index.v1+json",
    ]),
}

URL_RE = re.compile(r"https?://[a-zA-Z0-9._~:/?#@!$&'()*+,;=%-]+")
AUTH_RE = re.compile(r'(?:realm|service|scope)="([^"]*)"')


def normalize_mirror(url):
    url = url.strip().strip("~").rstrip(".,;，。)）]】>\"'")
    if not url:
        return None

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    parsed = urlparse(url)
    if not parsed.netloc:
        return None

    return "%s://%s" % (parsed.scheme, parsed.netloc)


# ── Docker Hub mirror scraping ──

def scrape_candidates(source_url, timeout, connect_timeout=3):
    mirrors = set()

    try:
        r = _session.get(
            source_url,
            timeout=(connect_timeout, timeout),
            headers={"User-Agent": HEADERS["User-Agent"]},
            verify=True,
        )
        r.raise_for_status()
    except Exception as e:
        print("抓取来源失败: %s -> %s" % (source_url, e))
        return mirrors

    text = r.text

    for item in URL_RE.findall(text):
        nm = normalize_mirror(item)
        if not nm:
            continue

        host = urlparse(nm).netloc.lower()

        if any(x in host for x in [
            "github.com",
            "githubusercontent.com",
            "docker.com",
            "opencontainers.org",
            "schema.org",
            "w3.org",
            "google.com",
            "baidu.com",
        ]):
            continue

        if any(k in host for k in [
            "docker",
            "registry",
            "mirror",
            "hub",
            "daocloud",
            "1ms",
            "xuanyuan",
            "aliyun",
            "tencent",
            "netease",
            "ustc",
            "sjtu",
        ]):
            mirrors.add(nm)

    return mirrors


def scrape_aityp_api(api_url, timeout, connect_timeout=3):
    mirrors = set()

    try:
        r = _session.get(
            api_url,
            timeout=(connect_timeout, timeout),
            headers={"User-Agent": HEADERS["User-Agent"]},
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("抓取 AITYP API 失败: %s -> %s" % (api_url, e))
        return mirrors

    if isinstance(data, dict):
        items = data.get("data") or data.get("results") or data.get("rows") or data.get("list") or []
    elif isinstance(data, list):
        items = data
    else:
        return mirrors

    for item in items:
        if not isinstance(item, dict):
            continue

        mirror = item.get("mirror")
        if not mirror:
            continue

        parts = mirror.split("/")
        if len(parts) < 2:
            continue

        host = parts[0]
        candidate = "https://%s" % host
        mirrors.add(candidate)

    return mirrors


# ── GitHub mirror scraping ──

def scrape_gh_candidates(source_url, timeout, connect_timeout=3):
    """从网页中抓取 GitHub 代理/加速站 URL。"""
    mirrors = set()

    try:
        r = _session.get(
            source_url,
            timeout=(connect_timeout, timeout),
            headers={"User-Agent": HEADERS["User-Agent"]},
            verify=True,
        )
        r.raise_for_status()
    except Exception as e:
        print("抓取 GitHub 来源失败: %s -> %s" % (source_url, e))
        return mirrors

    text = r.text

    for item in URL_RE.findall(text):
        nm = normalize_mirror(item)
        if not nm:
            continue

        host = urlparse(nm).netloc.lower()

        if any(x in host for x in [
            "github.com",
            "githubusercontent.com",
            "google.com",
            "baidu.com",
            "cloudflare.com",
        ]):
            continue

        if any(k in host for k in [
            "gh",
            "mirror",
            "proxy",
            "fast",
            "git",
            "hub",
            "code",
            "asset",
            "release",
        ]):
            mirrors.add(nm)

    return mirrors


# ── 错误信息简化 ──

def _simplify_error(e):
    """将 requests/urllib3 的长异常信息简化为可读的单行消息。"""
    if isinstance(e, requests.exceptions.ConnectionError):
        return "Network unreachable"
    if isinstance(e, requests.exceptions.Timeout):
        return "Connection timeout"
    if isinstance(e, requests.exceptions.SSLError):
        return "SSL error"

    msg = str(e)

    # 简化连接中断（IncompleteRead / Connection broken）
    if "IncompleteRead" in msg or "Connection broken" in msg:
        return "Connection broken (incomplete response)"

    # 简化 DNS 失败
    if "Name or service not known" in msg or "getaddrinfo" in msg.lower():
        return "DNS resolution failed"

    # 我们自己抛的 RuntimeError，保持原样
    if "manifest status" in msg or "blob status" in msg or "digest" in msg:
        return msg

    return msg


# ── Docker Hub mirror testing ──

def get_json(resp):
    try:
        return resp.json()
    except Exception:
        try:
            return json.loads(resp.text)
        except Exception:
            return None


def get_auth_token(mirror, image, timeout):
    """Docker Registry v2 Bearer auth: 拿 401 后走 auth 流程获取匿名 token。"""
    url = "%s/v2/%s/manifests/%s" % (mirror, image, TEST_TAG)
    r = _session.head(url, timeout=timeout, allow_redirects=True)

    if r.status_code == 200:
        return None

    www_auth = r.headers.get("Www-Authenticate", "")
    if not www_auth:
        return None

    parts = AUTH_RE.findall(www_auth)
    if len(parts) < 3:
        return None

    realm, service, scope = parts[0], parts[1], parts[2]

    try:
        r2 = _session.get(
            realm,
            params={"service": service, "scope": scope},
            timeout=timeout,
            headers={"User-Agent": HEADERS["User-Agent"]},
        )
        r2.raise_for_status()
        return r2.json().get("token")
    except Exception:
        return None


def get_manifest(mirror, image, timeout):
    url = "%s/v2/%s/manifests/%s" % (mirror, image, TEST_TAG)

    token = get_auth_token(mirror, image, timeout)
    req_headers = dict(HEADERS)
    if token:
        req_headers["Authorization"] = "Bearer %s" % token

    start = time.time()
    r = _session.get(
        url,
        headers=req_headers,
        timeout=timeout,
        allow_redirects=True,
    )
    latency = time.time() - start

    if r.status_code != 200:
        raise RuntimeError("manifest status %s" % r.status_code)

    manifest = get_json(r)
    if not manifest:
        raise RuntimeError("manifest is not json")

    return manifest, latency, token


def pick_amd64_manifest_digest(manifest):
    manifests = manifest.get("manifests")
    if not manifests:
        return None

    for item in manifests:
        platform = item.get("platform", {})
        if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
            return item.get("digest")

    if len(manifests) > 0:
        return manifests[0].get("digest")

    return None


def pick_blob_digest(manifest):
    if "manifests" in manifest:
        return pick_amd64_manifest_digest(manifest)

    layers = manifest.get("layers") or []
    if layers:
        return layers[0].get("digest")

    config = manifest.get("config") or {}
    return config.get("digest")


def fetch_manifest_by_digest(mirror, image, digest, timeout, token=None):
    url = "%s/v2/%s/manifests/%s" % (mirror, image, digest)

    req_headers = dict(HEADERS)
    if token:
        req_headers["Authorization"] = "Bearer %s" % token

    r = _session.get(
        url,
        headers=req_headers,
        timeout=timeout,
        allow_redirects=True,
    )

    if r.status_code != 200:
        raise RuntimeError("digest manifest status %s" % r.status_code)

    manifest = get_json(r)
    if not manifest:
        raise RuntimeError("digest manifest is not json")

    return manifest


def resolve_blob_digest(mirror, image, manifest, timeout, token=None):
    digest = pick_blob_digest(manifest)
    if not digest:
        raise RuntimeError("no digest found")

    media_type = manifest.get("mediaType", "")
    if "manifest.list" in media_type or "image.index" in media_type or "manifests" in manifest:
        sub_manifest = fetch_manifest_by_digest(mirror, image, digest, timeout, token)
        digest = pick_blob_digest(sub_manifest)

    if not digest:
        raise RuntimeError("no blob digest found")

    return digest


def download_blob_speed(mirror, image, digest, timeout, max_bytes, token=None):
    url = "%s/v2/%s/blobs/%s" % (mirror, image, digest)

    req_headers = {}
    if token:
        req_headers["Authorization"] = "Bearer %s" % token

    downloaded = 0

    r = _session.get(
        url,
        stream=True,
        timeout=timeout,
        headers=req_headers,
        allow_redirects=True,
    )

    try:
        if r.status_code != 200:
            raise RuntimeError("blob status %s" % r.status_code)

        start = time.time()
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue

            downloaded += len(chunk)

            if downloaded >= max_bytes:
                break
    finally:
        r.close()

    elapsed = time.time() - start
    if elapsed <= 0:
        speed = 0.0
    else:
        speed = downloaded / elapsed / 1024.0 / 1024.0

    return downloaded, elapsed, speed


def test_mirror(mirror, timeout, connect_timeout, max_bytes):
    result = {
        "mirror": mirror,
        "ok": False,
        "latency": None,
        "speed_mib": 0.0,
        "bytes": 0,
        "time": None,
        "error": "",
        "ok2": False,
        "speed2_mib": 0.0,
        "error2": "",
    }

    image = TEST_IMAGE
    if "myhuaweicloud.com" in mirror:
        image = AITYP_TEST_IMAGE

    try:
        # 快速 DNS 预检，避免不可达站点阻塞
        if not quick_dns_check(mirror, connect_timeout):
            raise RuntimeError("DNS timeout")

        t = (connect_timeout, timeout)
        manifest, latency, token = get_manifest(mirror, image, t)
        blob_digest = resolve_blob_digest(mirror, image, manifest, t, token)
        downloaded, elapsed, speed = download_blob_speed(
            mirror, image, blob_digest, t, max_bytes, token,
        )

        result["ok"] = True
        result["latency"] = latency
        result["speed_mib"] = speed
        result["bytes"] = downloaded
        result["time"] = elapsed

        image2 = TEST_IMAGE2
        if "myhuaweicloud.com" in mirror:
            image2 = AITYP_TEST_IMAGE2

        try:
            manifest2, _, token2 = get_manifest(mirror, image2, t)
            blob2 = resolve_blob_digest(mirror, image2, manifest2, t, token2)
            dl2, el2, sp2 = download_blob_speed(
                mirror, image2, blob2, t, max_bytes, token2,
            )
            result["ok2"] = True
            result["speed2_mib"] = sp2
        except Exception as e:
            result["error2"] = str(e)

    except Exception as e:
        result["error"] = _simplify_error(e)

    return result


def get_pull_cmds(mirror):
    """根据镜像站 URL 生成 docker/singularity pull 命令示例。"""
    host = urlparse(mirror).netloc

    if "myhuaweicloud.com" in mirror:
        image = AITYP_TEST_IMAGE
    else:
        image = TEST_IMAGE

    return (
        "docker pull %s/%s:%s" % (host, image, TEST_TAG),
        "singularity pull docker://%s/%s:%s" % (host, image, TEST_TAG),
    )


def get_gh_usage(mirror):
    """根据 GitHub 代理站 URL 生成使用示例。"""
    host = urlparse(mirror).netloc
    return (
        "wget  %s/%s" % (mirror, GH_TEST_URL),
        "git clone %s/https://github.com/git/git.git" % mirror,
    )


def print_result_line(r):
    status = "OK" if r["ok"] else "FAIL"

    if r["ok"]:
        s2 = ""
        if r["ok2"]:
            s2 = " | tetools: %.2f MiB/s" % r["speed2_mib"]
        elif r["error2"]:
            s2 = " | tetools: FAIL %s" % r["error2"]
        print(
            "%-4s %-45s %8.2f MiB/s  latency %.3fs%s" %
            (status, r["mirror"], r["speed_mib"], r["latency"], s2)
        )
    else:
        print(
            "%-4s %-45s %s" %
            (status, r["mirror"], r["error"])
        )


def print_gh_result_line(r):
    status = "OK" if r["ok"] else "FAIL"

    if r["ok"]:
        print(
            "%-4s %-45s %8.2f MiB/s  latency %.3fs" %
            (status, r["mirror"], r["speed_mib"], r["latency"])
        )
    else:
        print(
            "%-4s %-45s %s" %
            (status, r["mirror"], r["error"])
        )


# ── GitHub mirror testing ──

def test_gh_mirror(mirror, timeout, connect_timeout, max_bytes):
    """通过代理站下载 GitHub 文件并测速。"""
    result = {
        "mirror": mirror,
        "ok": False,
        "latency": None,
        "speed_mib": 0.0,
        "bytes": 0,
        "time": None,
        "error": "",
    }

    url = "%s/%s" % (mirror, GH_TEST_URL)
    t = (connect_timeout, timeout)

    try:
        if not quick_dns_check(mirror, connect_timeout):
            raise RuntimeError("DNS timeout")

        # 流式完整下载文件，模拟 wget 行为
        r = _session.get(url, stream=True, timeout=t, allow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError("GET status %s" % r.status_code)

        start = time.time()
        downloaded = 0
        for chunk in r.iter_content(chunk_size=128 * 1024):
            if not chunk:
                continue
            downloaded += len(chunk)
            if downloaded >= max_bytes:
                break
        elapsed = time.time() - start
        speed = downloaded / max(elapsed, 0.001) / 1024.0 / 1024.0

        result["ok"] = True
        result["latency"] = elapsed
        result["speed_mib"] = speed
        result["bytes"] = downloaded
        result["time"] = elapsed

    except Exception as e:
        result["error"] = _simplify_error(e)

    return result


# ── 镜像文件读写 ──

def load_mirror_file(path):
    """读取镜像文件，返回有序 URL 列表（跳过空行和 # 注释）。"""
    mirrors = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    mirrors.append(line)
    except FileNotFoundError:
        pass
    return mirrors


def save_mirror_file(path, ok_results, old_mirrors):
    """写入镜像文件：旧文件中仍 ok 的保持原顺序在前，新发现的按速度降序在后。"""
    ok_urls = {r["mirror"] for r in ok_results}
    survivors = [m for m in old_mirrors if m in ok_urls]
    survivors_set = set(survivors)
    newcomers = [r for r in ok_results if r["mirror"] not in survivors_set]

    with open(path, "w") as f:
        for m in survivors:
            f.write(m + "\n")
        for r in newcomers:
            f.write(r["mirror"] + "\n")

    return len(survivors), len(newcomers)


# ── Main ──

def main():
    parser = argparse.ArgumentParser(
        description="抓取 Docker 或 GitHub 镜像站并测试真实下载速度"
    )

    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="包含镜像站链接的网页，可重复传",
    )

    parser.add_argument(
        "--mirror",
        action="append",
        default=[],
        help="手动指定镜像站，可重复传",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="请求超时时间（下载），默认 10 秒",
    )

    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=3,
        help="连接超时时间（DNS+TCP），默认 3 秒",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并发数量，默认 8",
    )

    parser.add_argument(
        "--max-mb",
        type=int,
        default=1,
        help="每个镜像最多下载多少 MB，默认 1",
    )

    parser.add_argument(
        "--github",
        action="store_true",
        default=False,
        help="启用 GitHub 镜像站查找和测试模式（默认查找 Docker 镜像站）",
    )

    parser.add_argument(
        "--reliable-list",
        help="指定包含可靠镜像站列表的文本文件，每行一个 URL",
    )

    parser.add_argument(
        "--no-scrape",
        action="store_true",
        default=False,
        help="跳过网页抓取，仅测试自定义/可靠镜像站（节省时间）",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=0,
        help="最多显示多少个成功的镜像站（0 表示全部显示）",
    )

    args = parser.parse_args()

    mirror_file = MIRROR_FILE_GITHUB if args.github else MIRROR_FILE_DOCKER
    old_mirrors = load_mirror_file(mirror_file)

    mirrors = set()

    # ── 加载自定义可靠镜像站 ──
    if args.github:
        for m in RELIABLE_GH_MIRRORS:
            nm = normalize_mirror(m)
            if nm:
                mirrors.add(nm)
    else:
        for m in RELIABLE_DOCKER_MIRRORS:
            nm = normalize_mirror(m)
            if nm:
                mirrors.add(nm)

    if args.reliable_list:
        try:
            with open(args.reliable_list) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        nm = normalize_mirror(line)
                        if nm:
                            mirrors.add(nm)
            print("从 %s 加载了自定义可靠镜像站" % args.reliable_list)
        except Exception as e:
            print("读取自定义镜像站列表失败: %s" % e)

    for mirror in old_mirrors:
        nm = normalize_mirror(mirror)
        if nm:
            mirrors.add(nm)

    if args.no_scrape:
        # 仅测试 --mirror 和可靠列表，不抓取网页
        for mirror in args.mirror:
            nm = normalize_mirror(mirror)
            if nm:
                mirrors.add(nm)
    else:
        for mirror in args.mirror:
            nm = normalize_mirror(mirror)
            if nm:
                mirrors.add(nm)

    if args.github:
        if not args.no_scrape:
            sources = args.source
            if not sources:
                sources = GH_DEFAULT_SOURCES

            for source in sources:
                mirrors.update(scrape_gh_candidates(source, args.timeout, args.connect_timeout))

        mirrors = sorted(mirrors)

        print("Found %d candidate GitHub mirrors" % len(mirrors))
        print("Test file: %s" % GH_TEST_FILE)
        print("Max download per mirror: %d MB" % args.max_mb)
        print("")

        if not mirrors:
            print("没有找到候选镜像站。你可以用 --mirror 手动添加。")
            return

        max_bytes = args.max_mb * 1024 * 1024
        results = []

        executor = cf.ThreadPoolExecutor(max_workers=args.workers)

        try:
            futures = []
            for mirror in mirrors:
                futures.append(
                    executor.submit(test_gh_mirror, mirror, args.timeout, args.connect_timeout, max_bytes)
                )

            for fut in cf.as_completed(futures):
                r = fut.result()
                results.append(r)
                print_gh_result_line(r)

        finally:
            executor.shutdown(wait=True)

        ok = [x for x in results if x["ok"]]
        bad = [x for x in results if not x["ok"]]

        ok.sort(key=lambda x: x["speed_mib"], reverse=True)
        if args.top > 0:
            ok = ok[:args.top]

        print("")
        print("=== Ranking by download speed  ===" )
        print("%-5s %-14s %-12s %s" % ("Rank", "Speed", "Latency", "Mirror"))

        for idx, r in enumerate(ok, 1):
            print(
                "%-5d %-14s %-12s %s" %
                (
                    idx,
                    "%.2f MiB/s" % r["speed_mib"],
                    "%.3fs" % r["latency"],
                    r["mirror"],
                )
            )

        print("")
        if ok:
            r = ok[0]
            w1, gc = get_gh_usage(r["mirror"])
            print("")
            print("=== Usage examples ===")
            #print("%s" % r["mirror"])
            raw_url = "%s/https://raw.githubusercontent.com/samtools/samtools/refs/heads/develop/README.md" % r["mirror"]
            print("%s" % w1)
            print("wget %s" % raw_url)
            print("%s" % gc)

    else:
        # ── Docker Hub mirror mode (default) ──
        if not args.no_scrape:
            sources = args.source
            if not sources:
                sources = DEFAULT_SOURCES

            for source in sources:
                mirrors.update(scrape_candidates(source, args.timeout, args.connect_timeout))

            for api_url in AITYP_API_SOURCES:
                mirrors.update(scrape_aityp_api(api_url, args.timeout, args.connect_timeout))

        mirrors = sorted(mirrors)

        print("Found %d candidate mirrors" % len(mirrors))
        print("Test image: %s:%s" % (TEST_IMAGE, TEST_TAG))
        print("Max download per mirror: %d MB" % args.max_mb)
        print("")

        if not mirrors:
            print("没有找到候选镜像站。你可以用 --mirror 手动添加。")
            return

        max_bytes = args.max_mb * 1024 * 1024
        results = []

        executor = cf.ThreadPoolExecutor(max_workers=args.workers)

        try:
            futures = []
            for mirror in mirrors:
                futures.append(
                    executor.submit(test_mirror, mirror, args.timeout, args.connect_timeout, max_bytes)
                )

            for fut in cf.as_completed(futures):
                r = fut.result()
                results.append(r)
                print_result_line(r)

        finally:
            executor.shutdown(wait=True)

        ok = [x for x in results if x["ok"]]
        bad = [x for x in results if not x["ok"]]

        ok.sort(key=lambda x: x["speed_mib"], reverse=True)
        if args.top > 0:
            ok = ok[:args.top]

        print("")
        print("=== Ranking by download speed  ===" )
        print("%-5s %-14s %-12s %s" % ("Rank", "Speed", "Latency", "Mirror"))

        for idx, r in enumerate(ok, 1):
            s2 = ""
            if r["ok2"]:
                s2 = " | tetools: %.2f MiB/s" % r["speed2_mib"]
            elif r["error2"]:
                s2 = " | tetools: FAIL"
            print(
                "%-5d %-14s %-12s %s%s" %
                (
                    idx,
                    "%.2f MiB/s" % r["speed_mib"],
                    "%.3fs" % r["latency"],
                    r["mirror"],
                    s2,
                )
            )

        print("")
        if ok:
            r = ok[0]
            docker_cmd, singularity_cmd = get_pull_cmds(r["mirror"])
            print("")
            print("=== Usage examples ===")
            #print("%s" % r["mirror"])
            print("docker pull:      %s" % docker_cmd)
            print("singularity pull: %s" % singularity_cmd)

    print("")
    print("OK: %d / FAIL: %d" % (len(ok), len(bad)))

    n_survived, n_new = save_mirror_file(mirror_file, ok, old_mirrors)
    print("Saved %d mirrors to %s (%d kept, +%d new)" % (n_survived + n_new, mirror_file, n_survived, n_new))


if __name__ == "__main__":
    main()
