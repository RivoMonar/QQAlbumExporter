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

            data = json.loads(text, strict=False)
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
        data_body = data.get("data", {})

        # 兼容新旧两种 API 响应格式
        alist = []
        # 新格式: albumListModeSort（直接是相册对象数组）
        for item in data_body.get("albumListModeSort", []):
            if isinstance(item, dict) and "id" in item:
                alist.append(item)
        # 旧格式: albumListModeClass[].albumList[]
        if not alist:
            for mc in data_body.get("albumListModeClass", []):
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

def list_photos(uin: str, host_uin: str, album_id: str, g_tk: int, qzt: str) -> List[dict]:
    """
    通过 fcg_list_photo_v2 获取相册所有照片。
    关键：参数必须是 albumid（全小写），不是 topicId！
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

            photos.append({
                "id": p.get("id") or p.get("lloc", "")[:16],
                "name": p.get("name", ""),
                "url": raw_url,
                "width": p.get("width", 0),
                "height": p.get("height", 0),
                "size": p.get("photocubage", 0),
                "is_video": p.get("is_video", False),
            })

        total = data.get("data", {}).get("pageNum", 0)
        page += 1
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


def qrcode_login() -> tuple:
    """
    用 Selenium 打开 QQ 登录页，扫码登录。
    返回: (cookies_dict, cookie_str)
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("⚠ 请先安装依赖：pip install selenium webdriver-manager")
        return {}, ""

    print("\n📱 正在启动浏览器进行扫码登录...")
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")

    try:
        driver = webdriver.Chrome(
            service=webdriver.chrome.service.Service(
                ChromeDriverManager().install()),
            options=opts)
    except TypeError:
        # Selenium 3 兼容
        driver = webdriver.Chrome(
            executable_path=str(ChromeDriverManager().install()),
            options=opts)


    # 直接访问 i.qq.com，让平台自己处理登录流程
    driver.get("https://i.qq.com/")
    print("  ✅ 浏览器已打开，请用手机 QQ 扫描二维码")
    print("  ⏳ 扫码后会自动跳转并获取 Cookie...")

    # 等待登录完成：扫码确认后会自动跳转到 user.qzone.qq.com/{uin}
    try:
        WebDriverWait(driver, 120).until(
            lambda d: "user.qzone.qq.com" in d.current_url and "ptlogin" not in d.current_url
        )
        import time

        # 等待页面完全加载、Cookie 全部就位
        time.sleep(3)

        # 使用 CDP 获取全部 Cookie（含 HttpOnly 的 p_skey）
        try:
            cdp_cookies = driver.execute_cdp_cmd("Network.getAllCookies", {})
            cookies_dict = {}
            for c in cdp_cookies.get("cookies", []):
                if c["name"] not in cookies_dict:
                    cookies_dict[c["name"]] = c["value"]
        except:
            # 回退到普通方式
            selenium_cookies = driver.get_cookies()
            cookies_dict = {}
            for c in selenium_cookies:
                if c["name"] not in cookies_dict:
                    cookies_dict[c["name"]] = c["value"]

        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())

        if "p_skey" in cookies_dict or "skey" in cookies_dict:
            print(f"  ✅ 扫码登录成功！({len(cookies_dict)} 个 Cookie)")
            driver.quit()
            return cookies_dict, cookie_str
        else:
            print(f"  ⚠ 缺少 p_skey（已有: {list(cookies_dict.keys())[:10]}）")

    except Exception as e:
        print(f"  ❌ 扫码异常: {e}")

    driver.quit()
    return {}, ""


def main():
    global G_COOKIES, G_COOKIE_STR

    print(r"""
╔══════════════════════════════════════════╗
║     QQ 空间相册 · 照片视频下载工具       ║
║         多线程并发 · 可选相册            ║
╚══════════════════════════════════════════╝
""")

    # ── 登录 ──
    # 尝试加载已保存的 Cookie
    saved_cookie = load_cookie()
    if saved_cookie and verify_cookie(saved_cookie):
        G_COOKIES = parse_cookies(saved_cookie)
        G_COOKIE_STR = saved_cookie
        print("  ✅ 使用已保存的 Cookie（上次登录有效）")
    else:
        if saved_cookie:
            print("  ⚠ 已保存的 Cookie 已过期")

        print("\n📌 登录方式：")
        print("  1. 扫码登录 — 自动打开浏览器，手机 QQ 扫二维码")
        print("  2. 粘贴 Cookie — 手动从浏览器复制")
        choice = input("请输入 [1]: ").strip()

        if choice != "2":
            # 扫码登录（Selenium）
            G_COOKIES, G_COOKIE_STR = qrcode_login()
            if not G_COOKIES:
                print("\n⚠ 扫码登录失败，请选择方式 2 粘贴 Cookie：")
                choice = "2"

        if choice == "2" or not G_COOKIES:
            print("\n📌 请粘贴 Cookie（粘贴后按两次 Enter）：")
            print("=" * 60)
            print("  获取步骤：")
            print("    ① 浏览器登录 https://user.qzone.qq.com")
            print("    ② F12 → 网络(Network) → 筛选 qzone.qq.com")
            print("    ③ 点任意请求 → 请求头 → 复制 Cookie 值")
            print("    ④ 粘贴到下方：")
            print("=" * 60)
            lines = []
            try:
                while True:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line and lines:
                        break
                    if line:
                        lines.append(line)
            except (EOFError, KeyboardInterrupt):
                pass
            cookie_raw = " ".join(lines).strip()
            if not cookie_raw:
                print("❌ 未提供 Cookie"); sys.exit(1)
            G_COOKIES = parse_cookies(cookie_raw)
            G_COOKIE_STR = cookie_raw

        # 保存 Cookie
        save_cookie(G_COOKIE_STR)
    print(f"  ✓ 解析到 {len(G_COOKIES)} 个 Cookie 项")

    # ── g_tk ──
    skey = (G_COOKIES.get("p_skey") or G_COOKIES.get("media_p_skey") or G_COOKIES.get("skey") or "")
    if not skey:
        print("❌ 缺少签名密钥"); sys.exit(1)
    g_tk = calc_gtk(skey)
    src = next(k for k in ("p_skey", "media_p_skey", "skey") if k in G_COOKIES)
    print(f"🔑 g_tk = {g_tk} (基于 {src})")

    my_uin = extract_qq(G_COOKIES)
    if not my_uin:
        my_uin = input("请输入你的 QQ 号: ").strip()
    print(f"\n👤 你的 QQ: {my_uin}")

    # ── 并发数 ──
    threads_input = input(f"⏩ 下载线程数 [默认 {MAX_WORKERS}]: ").strip()
    max_workers = MAX_WORKERS
    if threads_input.isdigit() and 1 <= int(threads_input) <= 20:
        max_workers = int(threads_input)
    print(f"  → 使用 {max_workers} 线程并发下载")

    # ── qzonetoken ──
    qzt = fetch_qzonetoken(my_uin)
    print(f"  qzonetoken = {qzt[:20] if qzt else '(空)'}")

    # ── 相册列表 ──
    albums = list_albums(my_uin, my_uin, g_tk, qzt)
    if not albums:
        print("\n⚠ 未找到相册"); sys.exit(1)

    print(f"\n📚 共 {len(albums)} 个相册：")
    for i, a in enumerate(albums, 1):
        print(f"  [{i:2d}] {a['name']}  ({a['photo_count']}个文件)")

    # ── 相册选择 ──
    print("\n📥 选择要下载的相册（支持格式：a=全部, 1,3 或 5-8 或 1,3,5-8）")
    choice = input("请输入 [默认 a]: ").strip().lower()
    if choice and choice != "a":
        indices = parse_range(choice, len(albums))
        if indices:
            albums = [albums[i-1] for i in indices]
            print(f"  → 已选 {len(albums)} 个相册")
    else:
        print(f"  → 全部 {len(albums)} 个相册")

    dl_video = input("🎬 下载视频？(注：QZone v8 视频仅能下载封面缩略图) [Y/n]: ").strip().lower() != "n"

    base_dir = os.path.join(OUTPUT_DIR, my_uin)
    ensure_dir(base_dir)
    tp = sv = tv = sv2 = 0
    total_videos = 0

    print(f"\n📥 保存路径: {os.path.abspath(base_dir)}\n")

    # ── 遍历相册 ──
    for idx, alb in enumerate(albums, 1):
        aname = safe_name(alb["name"]) or f"album_{alb['id'][:8]}"
        adir = os.path.join(base_dir, f"{idx:02d}_{aname}")
        print(f"📁 [{idx}/{len(albums)}] {alb['name']}")

        # ── 获取所有文件（含视频） ──
        print(f"  📥 获取文件列表...")
        items = list_photos(my_uin, my_uin, alb["id"], g_tk, qzt)
        files = items  # list_photos 返回所有文件，含 is_video 标记

        if files:
            # 分离照片和视频
            photo_items = [f for f in files if not f.get('is_video')]
            video_items = [f for f in files if f.get('is_video')] if dl_video else []

            if photo_items:
                pd = os.path.join(adir, "图片")
                ensure_dir(pd)
                batch = []
                for pi, ph in enumerate(photo_items, 1):
                    if not ph.get("url"):
                        continue
                    ext = get_ext(ph["url"], ".jpg")
                    fn = safe_name(ph["name"]) or f"photo_{ph['id'][:8]}"
                    fp = os.path.join(pd, f"{pi:04d}_{fn}{ext}")
                    batch.append((ph["url"], fp, f"[{idx}-{pi}]"))
                s, t = download_batch(batch, max_workers=max_workers)
                sv += s; tp += t
                print(f"    📷 照片 {s}/{t}")

            if video_items:
                vd = os.path.join(adir, "视频")
                ensure_dir(vd)
                batch = []
                for vi, v in enumerate(video_items, 1):
                    if not v.get("url"):
                        continue
                    ext = get_ext(v["url"], ".mp4")
                    fn = safe_name(v["name"]) or f"video_{v['id'][:8]}"
                    fp = os.path.join(vd, f"{vi:04d}_{fn}{ext}")
                    batch.append((v["url"], fp, f"[{idx}-V{vi}]"))
                s, t = download_batch(batch, max_workers=max_workers)
                sv2 += s; tv += t
                print(f"    🎬 视频 {s}/{t}")

            total_videos += len(video_items)
        else:
            print(f"  ⚠ 未获取到文件")

    print(f"\n✅ 完成！照片 {sv}/{tp}，视频 {sv2}/{tv}")
    print(f"📂 {os.path.abspath(base_dir)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠ 用户中断")
        sys.exit(1)
