#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QQ 空间相册 · 图片与视频一键下载工具

关键修复：
  相册列表 → fcg_list_album_v3（工作正常）
  照片列表 → fcg_list_photo_v2 + albumid（全小写！）
  原图下载 → origin_url 字段

新功能：
  ✅ 选择性下载：1,3,5-8 或 a 全部
  ✅ 多线程并发下载（默认 5 线程）
"""

import os, re, sys, json, time, requests, tempfile, subprocess
from typing import Optional, List
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

OUTPUT_DIR = "qqzone_downloads"
REQUEST_DELAY = 0.3
PROXY = "https://h5.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin"
MAX_WORKERS = 5  # 默认并发线程数

G_COOKIES: dict = {}
G_COOKIE_STR: str = ""
_PROGRESS_LOCK = Lock()


# ═══════════════════════════════════════════════════════════════
# 网络请求
# ═══════════════════════════════════════════════════════════════

def api_get(url: str, params: dict = None, retries: int = 3) -> Optional[dict]:
    if params is None:
        params = {}
    params.setdefault("inCharset", "utf-8")
    params.setdefault("outCharset", "utf-8")

    for attempt in range(1, retries + 1):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://user.qzone.qq.com/",
                "Origin": "https://user.qzone.qq.com",
                "Cookie": G_COOKIE_STR,
            }
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            # 根据 Content-Type 确定编码（服务端已按 inCharset/outCharset=utf-8 返回）
            ct = resp.headers.get("Content-Type", "")
            if "charset=gb" in ct:
                resp.encoding = "gbk"
            else:
                resp.encoding = "utf-8"
            text = resp.text.strip()

            if not text:
                print(f"    ⚠ 响应为空 (Content-Type: {ct})")
                time.sleep(1.5)
                continue

            if text.startswith("_Callback"):
                text = re.sub(r"^_Callback\s*\(\s*", "", text)
                text = re.sub(r"\s*\)\s*$", "", text)

            try:
                data = json.loads(text, strict=False)
            except json.JSONDecodeError:
                # QZone 偶尔返回含非法转义符的 JSON（如 \s、\x）
                # 将非法转义反斜杠转义为 \\ 后重试
                fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
                data = json.loads(fixed, strict=False)
            code = data.get("code", -1)
            if code != 0:
                msg = data.get("message", "")
                if code == -4403:
                    print(f"    ⚠ 权限不足(code=-4403): 对方未公开此相册")
                else:
                    print(f"    ⚠ API {url.split('/')[-1]} 返回 code={code}: {msg}")
                return None
            return data
        except Exception as e:
            print(f"    ⚠ 第 {attempt} 次请求 {url.split('/')[-1]} 失败: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return None


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def calc_gtk(skey: str) -> int:
    return calc_hash(skey, init=5381)


def parse_cookies(s: str) -> dict:
    c = {}
    for item in s.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            c[k.strip()] = v.strip()
    return c


def extract_qq(cookies: dict) -> Optional[str]:
    for key in ("media_p_uin", "p_uin"):
        val = cookies.get(key, "").replace("o", "").lstrip("0")
        if val.isdigit():
            return val
    val = cookies.get("uin", "").replace("o", "").lstrip("0")
    return val if val.isdigit() else None


def safe_name(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r'\s+', " ", name).strip()
    return name[:max_len].rstrip() or "未命名"


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def get_ext(url: str, default: str) -> str:
    path = unquote(url.split("?")[0])
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
                          ".mp4", ".mov", ".avi", ".mkv", ".flv") else default


def parse_range(text: str, max_val: int) -> List[int]:
    """解析用户输入的编号范围，如 '1,3,5-8' → [1,3,5,6,7,8]"""
    result = set()
    for part in text.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                a, b = int(a.strip()), int(b.strip())
                result.update(range(a, min(b, max_val) + 1))
            except ValueError:
                pass
        else:
            try:
                n = int(part)
                if 1 <= n <= max_val:
                    result.add(n)
            except ValueError:
                pass
    return sorted(result)


# ═══════════════════════════════════════════════════════════════
# 下载（支持多线程）
# ═══════════════════════════════════════════════════════════════

def download_file(url: str, path: str, desc: str = "") -> bool:
    """单个文件下载（线程安全）"""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    tmp = path + ".tmp"
    resume = 0
    if os.path.exists(tmp):
        resume = os.path.getsize(tmp)
    try:
        hdrs = {
            "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36",
            "Referer": "https://user.qzone.qq.com/",
            "Cookie": G_COOKIE_STR,
        }
        if resume > 0:
            hdrs["Range"] = f"bytes={resume}-"
        resp = requests.get(url, headers=hdrs, stream=True, timeout=60)
        if resp.status_code == 416:
            os.remove(tmp)
            return download_file(url, path, desc)
        if resp.status_code not in (200, 206):
            with _PROGRESS_LOCK:
                print(f"    ❌ {desc}: HTTP {resp.status_code}")
            return False
        ct = resp.headers.get("Content-Type", "")
        if ct.startswith("image/jpeg") and not path.lower().endswith(('.jpg', '.jpeg')):
            path = path.rsplit('.', 1)[0] + '.jpg'
            tmp = path + ".tmp"
        mode = "ab" if resume > 0 else "wb"
        with open(tmp, mode) as f:
            total = int(resp.headers.get("content-length", 0)) + resume
            done = resume
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
        os.rename(tmp, path)
        mb = os.path.getsize(path) / (1024 * 1024)
        with _PROGRESS_LOCK:
            print(f"    ✅ {desc}: {mb:.1f} MB")
        return True
    except requests.RequestException as e:
        with _PROGRESS_LOCK:
            print(f"    ⚠ {desc}: 中断 - {e}")
        return False


def download_batch(items: List[tuple], max_workers: int = MAX_WORKERS) -> tuple:
    """
    并发下载一批文件。
    items: [(url, filepath, desc), ...]
    返回: (成功数, 总数)
    """
    total = len(items)
    success = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fut_to_idx = {
            executor.submit(download_file, url, fp, desc): i
            for i, (url, fp, desc) in enumerate(items)
        }
        for fut in as_completed(fut_to_idx):
            if fut.result():
                success += 1

    return success, total


# ═══════════════════════════════════════════════════════════════
# qzonetoken
# ═══════════════════════════════════════════════════════════════

def fetch_qzonetoken(host_uin: str) -> str:
    try:
        hdrs = {"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Cookie": G_COOKIE_STR}
        r = requests.get(f"https://user.qzone.qq.com/{host_uin}/infocenter", headers=hdrs, timeout=30)
        r.encoding = "utf-8"
        html = r.text
        for pat in [r'window\.g_qzonetoken\s*=\s*["\']([^"\']+)["\']',
                    r'window\.qzonetoken\s*=\s*["\']([^"\']+)["\']']:
            m = re.search(pat, html)
            if m and m.group(1):
                return m.group(1)
        if "g_qzonetoken = ''" in html:
            return G_COOKIES.get("pt4_token", "")
    except:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════
# 相册列表
# ═══════════════════════════════════════════════════════════════

def list_albums(uin: str, host_uin: str, g_tk: int, qzt: str) -> list:
    albums = []
    page_start = 0
    page_size = 30
    print(f"\n📂 获取相册列表...")
    while True:
        data = api_get(f"{PROXY}/fcg_list_album_v3", {
            "uin": uin, "hostUin": host_uin,
            "pageStart": page_start, "len": page_size,
            "format": "json", "g_tk": g_tk, "qzonetoken": qzt,
        })
        if data is None:
            break
        data_body = data.get("data")
        if not isinstance(data_body, dict):
            break

        # 兼容新旧两种 API 响应格式
        alist = []
        # 新格式: albumListModeSort（直接是相册对象数组）
        for item in (data_body.get("albumListModeSort") or []):
            if isinstance(item, dict) and "id" in item:
                alist.append(item)
        # 旧格式: albumListModeClass[].albumList[]
        if not alist:
            for mc in (data_body.get("albumListModeClass") or []):
                alist.extend(mc.get("albumList", []))

        if not alist:
            break

        for a in alist:
            albums.append({
                "id": a.get("id", ""),
                "name": a.get("name", ""),
                "photo_count": a.get("total", 0),
                "createtime": a.get("createtime", 0),
            })

        total = data_body.get("albumsInUser", 0) or data_body.get("totalAlbumNum", 0)
        print(f"  → {len(albums)}/{total}", end="\r")
        time.sleep(REQUEST_DELAY)

        # 判断是否还有下一页
        next_start = data_body.get("nextPageStartModeSort")
        if len(alist) < page_size:
            break
        if next_start is not None:
            if next_start == 0 or next_start == page_start:
                break
            page_start = next_start
        else:
            break

    # 按创建时间排序（最早的在前）
    albums.sort(key=lambda x: x["createtime"])
    print(f"\n  ✓ 共 {len(albums)} 个相册")
    return albums


# ═══════════════════════════════════════════════════════════════
# 照片列表 (v2 API)
# ═══════════════════════════════════════════════════════════════

def list_photos(uin: str, host_uin: str, album_id: str, g_tk: int, qzt: str, silent: bool = False) -> List[dict]:
    """
    通过 fcg_list_photo_v2 获取相册所有照片。
    关键：参数必须是 albumid（全小写），不是 topicId！
    silent=True 时不打印进度（用于后台扫描）
    """
    photos = []
    page = 1
    page_size = 100

    while True:
        data = api_get(f"{PROXY}/fcg_list_photo_v2", {
            "uin": uin, "hostUin": host_uin,
            "albumid": album_id,
            "pageNum": page, "pageSize": page_size,
            "format": "json", "g_tk": g_tk, "qzonetoken": qzt,
        })
        if data is None:
            if not silent:
                print(f"  ⚠ 无法获取文件列表（相册可能未公开或需登录查看）")
            break

        pics = data.get("data", {}).get("pic", [])
        if not pics:
            break

        for p in pics:
            raw_url = (p.get("origin_url") or p.get("raw") or
                       p.get("url") or p.get("picUrl") or "")
            if raw_url and not raw_url.startswith("http"):
                raw_url = "https://" + raw_url

            entry = {
                "id": p.get("id") or p.get("lloc", "")[:16],
                "name": p.get("name", ""),
                "url": raw_url,
                "width": p.get("width", 0),
                "height": p.get("height", 0),
                "size": p.get("photocubage", 0),
                "is_video": p.get("is_video", False),
                # 视频相关字段
                "vid": p.get("vid", ""),
                "batchId": p.get("batchId", ""),
                "lloc": p.get("lloc", ""),
            }
            photos.append(entry)

        total = data.get("data", {}).get("pageNum", 0)
        page += 1
        if not silent:
            print(f"    → {len(photos)}张", end="\r")
        time.sleep(REQUEST_DELAY)

        if len(pics) < page_size:
            break
        if total > 0 and len(photos) >= total:
            break

    return photos





# ═══════════════════════════════════════════════════════════════
# QQ 扫码登录
# ═══════════════════════════════════════════════════════════════

def calc_hash(s: str, init: int = 5381) -> int:
    """QQ 哈希算法"""
    h = init
    for ch in s:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF


COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qqzone_cookie.txt")


def save_cookie(cookie_str: str):
    """保存 Cookie 到本地文件"""
    try:
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(cookie_str)
        print(f"  💾 Cookie 已保存到 {COOKIE_FILE}（下次自动加载）")
    except Exception as e:
        print(f"  ⚠ Cookie 保存失败: {e}")


def load_cookie() -> str:
    """从本地文件加载 Cookie"""
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except:
            pass
    return ""


def verify_cookie(cookie_str: str) -> bool:
    """验证 Cookie 是否有效（尝试获取相册列表）"""
    try:
        cookies = parse_cookies(cookie_str)
        skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
        if not skey:
            return False
        g_tk = calc_hash(skey)
        uin = ""
        for k in ("media_p_uin", "p_uin"):
            v = cookies.get(k, "").replace("o", "").lstrip("0")
            if v.isdigit():
                uin = v
                break
        if not uin:
            v = cookies.get("uin", "").replace("o", "").lstrip("0")
            if v.isdigit():
                uin = v

        r = requests.get(f"{PROXY}/fcg_list_album_v3", params={
            "uin": uin, "hostUin": uin,
            "pageStart": 0, "len": 3,
            "format": "json", "g_tk": g_tk,
            "inCharset": "utf-8", "outCharset": "utf-8",
        }, headers={
            "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36",
            "Referer": "https://user.qzone.qq.com/",
            "Cookie": cookie_str,
        }, timeout=10)
        d = r.json()
        return d.get("code") == 0
    except:
        return False


# ═══════════════════════════════════════════════════════════════
# 视频导出
# ═══════════════════════════════════════════════════════════════

def list_videos_in_album(uin: str, host_uin: str, album_id: str, g_tk: int, qzt: str) -> list:
    """获取相册中所有视频项（含 vid 用于构建视频页 URL）"""
    photos = list_photos(uin, host_uin, album_id, g_tk, qzt, silent=True)
    videos = []
    for p in photos:
        if p.get("is_video"):
            videos.append(p)
    return videos


def _find_vid(photo: dict) -> str:
    """从照片数据中提取视频 ID（尝试多个可能的字段）"""
    return (photo.get("vid") or
            photo.get("batchId") or
            photo.get("lloc") or
            photo.get("id", ""))


def capture_video_urls(videos: list, cookie_str: str) -> list:
    """
    用 Selenium 批量捕获视频真实下载链接。
    videos: [{id, name, album_name, album_id, uin}, ...]
    返回: [{album, name, url}, ...]
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.microsoft import EdgeChromiumDriverManager
    except ImportError:
        print("⚠ 视频导出需要：pip install selenium webdriver-manager")
        return []

    # 解析 Cookie 字符串为字典列表供 Selenium 注入
    cookies_list = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies_list.append({"name": k.strip(), "value": v.strip(), "domain": ".qq.com"})

    def _create_driver():
        browsers = [
            ("Chrome", ChromeOptions, webdriver.Chrome, ChromeDriverManager),
            ("Edge",   EdgeOptions,   webdriver.Edge,   EdgeChromiumDriverManager),
        ]
        for name, Opts, Driver, DrvMgr in browsers:
            try:
                opts = Opts()
                # 非 headless，用户可以观察捕获过程
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--window-size=1280,720")
                # 启用网络日志以便 CDP 抓取请求
                opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
                if name == "Edge":
                    opts.add_argument("--disable-features=msEdgeWelcomePage")
                try:
                    driver = Driver(
                        service=webdriver.chrome.service.Service(DrvMgr().install())
                        if name == "Chrome" else
                        webdriver.edge.service.Service(DrvMgr().install()),
                        options=opts)
                except TypeError:
                    driver = Driver(
                        executable_path=str(DrvMgr().install()),
                        options=opts)
                return driver
            except Exception:
                continue
        return None

    driver = _create_driver()
    if not driver:
        print("⚠ 无法启动浏览器（Chrome / Edge 均不可用）")
        return []

    results = []
    try:
        # 先访问 qzone 域名注入 Cookie
        driver.get("https://xui.ptlogin2.qq.com/cgi-bin/xlogin?appid=549000912&daid=5&style=35&s_url=https://qzs.qzone.qq.com/qzone/v5/loginsucc.html?para=izone")
        for c in cookies_list:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        time.sleep(1)

        total = len(videos)
        for i, v in enumerate(videos, 1):
            vid = _find_vid(v)
            if not vid:
                print(f"  ⚠ [{i}/{total}] {v.get('name','')} — 无法获取视频 ID (vid={v.get('vid','')}, batchId={v.get('batchId','')}, lloc={v.get('lloc','')[:20] if v.get('lloc') else ''})")
                continue

            desc = v.get("name", "") or vid[:12]
            print(f"  [{i}/{total}] {desc} — vid={vid[:20]}...")
            try:
                page_url = f"https://h5.qzone.qq.com/video/index?vid={vid}"
                driver.get(page_url)

                video_url = ""

                # 方法 1: 等待 <video> 元素
                try:
                    video_el = WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "video"))
                    )
                    video_url = video_el.get_attribute("src") or ""
                    if not video_url:
                        video_url = driver.execute_script(
                            "var v=document.querySelector('video');return v?v.src||v.currentSrc||'':''"
                        )
                except Exception:
                    pass

                # 方法 2: 从 CDP 网络日志提取
                if not video_url:
                    try:
                        logs = driver.get_log("performance")
                        for entry in reversed(logs):
                            msg = json.loads(entry["message"])
                            method = msg.get("message", {}).get("method", "")
                            if method == "Network.responseReceived":
                                resp_url = msg["message"]["params"]["response"]["url"]
                                mime = msg["message"]["params"]["response"].get("mimeType", "")
                                if "video" in mime or resp_url.endswith((".mp4", ".m3u8", ".webm", ".ts")):
                                    video_url = resp_url
                                    break
                    except Exception:
                        pass

                # 方法 3: 页面源码搜索
                if not video_url:
                    import re as _re
                    html = driver.page_source
                    for pat in [
                        r'https?://[^"\'\\s]+\.mp4[^"\'\\s]*',
                        r'https?://[^"\'\\s]+/video/[^"\'\\s]+',
                        r'"video_url"\s*:\s*"(https?://[^"]+)"',
                    ]:
                        m = _re.search(pat, html)
                        if m:
                            video_url = m.group(1) if m.lastindex else m.group(0)
                            break

                if video_url:
                    print(f"    ✅ {video_url[:100]}...")
                    results.append({
                        "album": v.get("album_name", ""),
                        "name": v.get("name", desc),
                        "url": video_url,
                    })
                else:
                    print(f"    ⚠ 未找到视频链接（vid={vid}，页面可能要求登录或视频已删除）")
            except Exception as e:
                print(f"    ⚠ {desc} — {str(e)[:80]}")

            time.sleep(1)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return results
