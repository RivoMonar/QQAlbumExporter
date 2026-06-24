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

def api_get(url: str, params: dict = None, retries: int = 3, silent: bool = False) -> Optional[dict]:
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
                if not silent:
                    print(f"    ⚠ 响应为空 (Content-Type: {ct})")
                time.sleep(1.5)
                continue

            if text.startswith("_Callback"):
                text = re.sub(r"^_Callback\s*\(\s*", "", text)
                text = re.sub(r"\s*\)\s*$", "", text)

            try:
                # 用 raw_decode 解析第一个 JSON 对象（容错 Extra data 和非法转义）
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(text)
            except Exception:
                try:
                    # 修复非法反斜杠转义后重试
                    fixed = re.sub(r'\\(?![\\/bfnrtu"])', r'\\\\', text)
                    data, _ = decoder.raw_decode(fixed)
                except Exception:
                    # 仍失败：尝试只取第一个 { } 之间的内容
                    m = re.search(r'\{.*\}', text, re.DOTALL)
                    if m:
                        try:
                            data, _ = decoder.raw_decode(m.group(0))
                        except Exception:
                            raise
                    else:
                        raise
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
            if not silent:
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
# 视频 URL 获取 (floatview API)
# ═══════════════════════════════════════════════════════════════

def get_video_url(uin: str, host_uin: str, album_id: str, pic_key: str,
                  g_tk: int) -> str:
    """
    通过 floatview API 获取视频的真实下载 URL。
    pic_key 为照片的 lloc 值。
    """
    url = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/cgi_floatview_photo_list_v2"
    params = {
        "g_tk": g_tk, "t": str(int(time.time() * 1000)),
        "topicId": album_id, "picKey": pic_key,
        "shootTime": "", "cmtOrder": "1", "fupdate": "1",
        "plat": "qzone", "source": "qzone",
        "cmtNum": "10", "likeNum": "5",
        "inCharset": "utf-8", "outCharset": "utf-8",
        "offset": "0", "number": "15",
        "uin": uin, "hostUin": host_uin,
        "appid": "4", "isFirst": "1", "sortOrder": "1",
    }
    data = api_get(url, params, retries=1, silent=True)
    if data is None:
        return ""
    for p in (data.get("data", {}).get("photos") or []):
        vi = p.get("video_info")
        if vi:
            return vi.get("download_url", "") or vi.get("video_url", "")
    return ""


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
            "filter": "1", "handset": "4", "needUserInfo": "1",
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
            cover = a.get("pre", "")
            if cover and not cover.startswith("http"):
                cover = "https://" + cover
            # 调试：打印第一个相册的 pre
            if not hasattr(list_albums, "_debug_pre"):
                print(f"  [DEBUG] first album pre: {repr(cover[:120]) if cover else 'EMPTY'}")
                list_albums._debug_pre = True
            albums.append({
                "id": a.get("id", ""),
                "name": a.get("name", ""),
                "photo_count": a.get("total", 0),
                "createtime": a.get("createtime", 0),
                "cover": cover,
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
    """获取相册中所有视频项——复用已验证的 list_photos"""
    photos = list_photos(uin, host_uin, album_id, g_tk, qzt, silent=True)
    return [p for p in photos if p.get("is_video")]


