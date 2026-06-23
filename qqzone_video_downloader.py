#!/usr/bin/env python3
"""
QQ 空间视频下载器 — Selenium 浏览器自动化版

两步走：
  Step 1: 通过 API 扫描所有相册，找出所有视频
  Step 2: 用 Selenium 打开 QZone 视频播放页，提取真实视频 URL，下载

特点：
  ✅ 自动适配 Chrome / Edge / Firefox（webdriver-manager）
  ✅ 无头模式：后台静默运行
  ✅ 断点续传

安装：
  pip install selenium webdriver-manager

使用：
  先 python qqzone_downloader.py 下载照片
  再 python qqzone_video_downloader.py 下载视频
"""

import os, sys, json, time, re, requests
from urllib.parse import unquote

OUTPUT_DIR = "qqzone_videos"
PROXY = "https://h5.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin"

# ── Selenium 延迟导入（只在需要时才检查）─
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False


# ═══════════════════════════════════════════════════════════════
# 基础工具
# ═══════════════════════════════════════════════════════════════

def parse_cookies(s: str) -> dict:
    c = {}
    for item in s.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            c[k.strip()] = v.strip()
    return c


def calc_gtk(skey: str) -> int:
    h = 5381
    for ch in skey:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF


def safe_name(name: str, max_len=80) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name[:max_len].strip() or "未命名"


def parse_range(text: str, max_val: int) -> list:
    """解析编号范围，如 '1,3,5-8' → [1,3,5,6,7,8]"""
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
# Step 1: API 扫描视频
# ═══════════════════════════════════════════════════════════════

def scan_video_counts(cookie_raw: str, target: str) -> list:
    """
    扫描相册，统计每个相册的视频数量。
    返回: [{idx, id, name, video_count}, ...]
    """
    cookies = parse_cookies(cookie_raw)
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or ""
    g_tk = calc_gtk(skey) if skey else 0

    headers = {
        "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36",
        "Referer": "https://user.qzone.qq.com/",
        "Cookie": cookie_raw,
    }

    print("📂 扫描相册中...")
    # 获取相册列表（分页）
    all_albums = []
    page_start = 0
    while True:
        r = requests.get(f"{PROXY}/fcg_list_album_v3", params={
            "uin": target, "hostUin": target,
            "pageStart": page_start, "len": 30,
            "format": "json", "g_tk": g_tk,
            "inCharset": "utf-8", "outCharset": "utf-8",
        }, headers=headers, timeout=15)
        d = r.json()
        albs = d["data"].get("albumListModeSort", [])
        if not albs:
            break
        all_albums.extend(albs)
        next_start = d["data"].get("nextPageStartModeSort", 0)
        if not next_start or next_start == page_start or len(albs) < 30:
            break
        page_start = next_start

    # 扫描每个相册的视频数
    album_list = []
    for idx, a in enumerate(all_albums, 1):
        aid = a["id"]
        total = a.get("total", 0)
        vcount = 0
        if total > 0:
            print(f"  [{idx}] {a['name']}...", end="\r")
            try:
                r2 = requests.get(f"{PROXY}/fcg_list_photo_v2", params={
                    "uin": target, "hostUin": target,
                    "albumid": aid, "pageNum": 1, "pageSize": 500,
                    "format": "json", "g_tk": g_tk,
                    "inCharset": "utf-8", "outCharset": "utf-8",
                }, headers=headers, timeout=15)
                raw = r2.content
                for enc in ["utf-8", "gbk"]:
                    try:
                        text = raw.decode(enc)
                        d2 = json.loads(text)
                        break
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                else:
                    vcount = 0
                pics = d2.get("data", {}).get("pic", [])
                vcount = len([p for p in pics if p.get("is_video")])
            except requests.RequestException:
                vcount = 0

        album_list.append({"idx": idx, "id": aid, "name": a["name"], "video_count": vcount})
        print(f"  [{idx}] {a['name']}: {vcount} 个视频" + " " * 10)

    return album_list


def collect_videos(albums: list, cookie_raw: str, target: str) -> list:
    """
    从指定相册列表中收集所有视频的详细信息。
    返回: [{album_name, name, batchId, lloc, url, album_id}, ...]
    """
    cookies = parse_cookies(cookie_raw)
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or ""
    g_tk = calc_gtk(skey) if skey else 0

    headers = {
        "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36",
        "Referer": "https://user.qzone.qq.com/",
        "Cookie": cookie_raw,
    }

    videos = []
    for a in albums:
        aid = a["id"]
        r2 = requests.get(f"{PROXY}/fcg_list_photo_v2", params={
            "uin": target, "hostUin": target,
            "albumid": aid, "pageNum": 1, "pageSize": 500,
            "format": "json", "g_tk": g_tk,
            "inCharset": "utf-8", "outCharset": "utf-8",
        }, headers=headers, timeout=30)

        raw = r2.content
        for enc in ["utf-8", "gbk"]:
            try:
                text = raw.decode(enc)
                d2 = json.loads(text)
                break
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        else:
            print(f"  ⚠ {a['name']}: 跳过（解析失败）")
            continue

        pics = d2.get("data", {}).get("pic", [])
        vs = [p for p in pics if p.get("is_video")]
        print(f"  → {a['name']}: {len(vs)} 个视频")
        for v in vs:
            videos.append({
                "album_name": a["name"],
                "album_id": aid,
                "name": v.get("name", "") or f"video_{v.get('batchId','')}",
                "batchId": str(v.get("batchId", "")),
                "lloc": v.get("lloc", ""),
                "url": v.get("url", ""),
            })

    return videos


# ═══════════════════════════════════════════════════════════════
# Step 2: Selenium 捕获视频 URL
# ═══════════════════════════════════════════════════════════════

def capture_video_urls(videos: list, cookie_raw: str, browser="chrome",
                       headless=True) -> list:
    """
    用 Selenium 逐个打开视频页面，提取真实视频 URL。
    返回: [(album_name, name, video_url), ...]
    """
    if not SELENIUM_OK:
        print("❌ 请安装 selenium: pip install selenium webdriver-manager")
        return []

    print(f"\n🚀 启动 {browser.upper()} (headless={headless})...")

    # 创建驱动（Selenium 4）
    def _init_driver(driver_cls, exec_path, opts):
        exec_path = str(exec_path)
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.edge.service import Service as EdgeService
        from selenium.webdriver.firefox.service import Service as FirefoxService
        
        if driver_cls == webdriver.Chrome:
            return driver_cls(service=ChromeService(exec_path), options=opts)
        elif driver_cls == webdriver.Edge:
            return driver_cls(service=EdgeService(exec_path), options=opts)
        elif driver_cls == webdriver.Firefox:
            return driver_cls(service=FirefoxService(exec_path), options=opts)
        return driver_cls(executable_path=exec_path, options=opts)

    if browser == "chrome":
        opts = ChromeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")
        if headless:
            opts.add_argument("--headless=new")
        driver = _init_driver(webdriver.Chrome, ChromeDriverManager().install(), opts)

    elif browser == "edge":
        opts = EdgeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        if headless:
            opts.add_argument("--headless=new")
        driver = _init_driver(webdriver.Edge, EdgeChromiumDriverManager().install(), opts)

    elif browser == "firefox":
        opts = FirefoxOptions()
        if headless:
            opts.add_argument("--headless")
        driver = _init_driver(webdriver.Firefox, GeckoDriverManager().install(), opts)
    else:
        print(f"❌ 不支持的浏览器: {browser}")
        return []

    # 注入 Cookie
    cookies = parse_cookies(cookie_raw)
    try:
        # 先访问 h5.qzone.qq.com 域（视频播放页）
        driver.get("https://h5.qzone.qq.com")
        time.sleep(3)

        # 用 JavaScript 注入所有 Cookie（可绕过 Selenium 对 * 的限制）
        js = ""
        for key, value in cookies.items():
            if value:
                # 对值中的特殊字符做转义
                val = value.replace("\\", "\\\\").replace("'", "\\'")
                js += f"document.cookie='{key}={val}; domain=.qq.com; path=/';"
        driver.execute_script(js)

        # 刷新页面验证登录态
        driver.get("https://user.qzone.qq.com/807876867/infocenter")
        time.sleep(3)

        if "login" in driver.current_url.lower() or "ptlogin" in driver.current_url:
            print("⚠ Cookie 已过期，请重新登录后获取新 Cookie")
            driver.quit()
            return []
    except Exception as e:
        print(f"⚠ Cookie 注入失败: {e}")
        driver.quit()
        return []

    results = []
    total = len(videos)

    for i, v in enumerate(videos, 1):
        album = v.get("album_name", "")
        name = v.get("name", "")
        batch_id = v.get("batchId", "")
        lloc = v.get("lloc", "")

        print(f"\n[{i}/{total}] {album} - {name}")

        # 尝试 vid = batchId
        vid_candidates = [batch_id]

        # 如果 batchId 过长，可能是毫秒时间戳，截取秒级
        if len(batch_id) > 11 and batch_id.isdigit():
            vid_candidates.append(batch_id[:10])

        # 尝试从 URL 中提取 video-specific ID
        url_m = re.search(r'/V51uwTNb3zEQOZ4J5BMb3L42AP(\w+)/', v.get("url", ""))
        if url_m:
            vid_candidates.append(url_m.group(1))

        found = False
        for vid in vid_candidates:
            if not vid:
                continue

            page_url = f"https://h5.qzone.qq.com/video/index?vid={vid}"
            print(f"  → 打开: vid={vid}")

            try:
                driver.get(page_url)
                time.sleep(5)  # 等待 React 渲染 + 动态加载

                # 处理 alert（如 "视频播放失败"）
                try:
                    alert = driver.switch_to.alert
                    print(f"    ⚠ alert: {alert.text[:80]}")
                    alert.accept()
                    time.sleep(1)
                except:
                    pass

                # 找 <video> 元素（等待动态加载）
                video_url = ""
                for _ in range(15):
                    try:
                        video_el = driver.find_element(By.TAG_NAME, "video")
                        video_url = video_el.get_attribute("src") or ""
                        if not video_url:
                            video_url = driver.execute_script(
                                "var v=document.querySelector('video');return v?v.src||v.currentSrc||'':''"
                            ) or ""
                        if video_url:
                            print(f"  → ✅ <video> src={video_url[:80]}...")
                            break
                    except:
                        pass
                    time.sleep(1)

                # 从页面源码搜索
                if not video_url:
                    html = driver.page_source
                    for m in re.finditer(
                        r'(https?://[^"\'\\s]+\.(?:mp4|m3u8|webm|ts)[^"\'\\s]*)',
                        html
                    ):
                        video_url = m.group(1)
                        print(f"  → ✅ 从 HTML 发现: {video_url[:80]}...")
                        break
                        break

                if video_url:
                    print(f"  → ✅ {video_url[:100]}...")
                    results.append((album, name, video_url))
                    found = True
                    break
                else:
                    print(f"  → ⚠ 未找到 video 标签 (vid={vid})")

            except Exception as e:
                print(f"  → ⚠ 页面加载失败: {e}")

        if not found:
            print(f"  → ❌ 所有 vid 均未找到视频 URL")

        time.sleep(1)

    driver.quit()
    return results


# ═══════════════════════════════════════════════════════════════
# 下载
# ═══════════════════════════════════════════════════════════════

def download_video(url: str, filepath: str, desc: str = "") -> bool:
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return True
    tmp = filepath + ".tmp"
    resume = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    try:
        hdrs = {"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36",
                "Referer": "https://user.qzone.qq.com/"}
        if resume > 0:
            hdrs["Range"] = f"bytes={resume}-"
        resp = requests.get(url, headers=hdrs, stream=True, timeout=120)
        if resp.status_code == 416:
            os.remove(tmp)
            return download_video(url, filepath, desc)
        if resp.status_code not in (200, 206):
            print(f"    ❌ {desc}: HTTP {resp.status_code}")
            return False
        with open(tmp, "ab" if resume > 0 else "wb") as f:
            total = int(resp.headers.get("content-length", 0)) + resume
            done = resume
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if done - resume > 5*1024*1024:
                        print(f"    ⏳ {desc}: {done//1024//1024}MB/{total//1024//1024}MB", end="\r")
        os.rename(tmp, filepath)
        mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"    ✅ {desc}: {mb:.1f} MB")
        return True
    except Exception as e:
        print(f"    ⚠ {desc}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    print(r"""
╔══════════════════════════════════════════╗
║     QQ 空间视频下载 · Selenium 版        ║
╚══════════════════════════════════════════╝
""")

    # ── Cookie ──
    print("📌 粘贴 Cookie（两次回车结束）：")
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

    # ── 提取 QQ 号 ──
    cookies = parse_cookies(cookie_raw)
    my_uin = ""
    for key in ("media_p_uin", "p_uin"):
        val = cookies.get(key, "").replace("o", "").lstrip("0")
        if val.isdigit():
            my_uin = val
            break
    if not my_uin:
        val = cookies.get("uin", "").replace("o", "").lstrip("0")
        if val.isdigit():
            my_uin = val
    target = input(f"请输入目标 QQ 号 [默认 {my_uin}]: ").strip() or my_uin

    # ── Step 1: 扫描相册视频数 ──
    album_list = scan_video_counts(cookie_raw, target)

    total_videos = sum(a["video_count"] for a in album_list)
    print(f"\n📚 共 {len(album_list)} 个相册，{total_videos} 个视频")

    # ── 相册选择 ──
    print("\n📥 选择要下载视频的相册（支持格式：a=全部, 1,3 或 5-8 或 1,3,5-8）")
    choice = input("请输入 [默认 a]: ").strip().lower()
    if choice and choice != "a":
        indices = parse_range(choice, len(album_list))
        if indices:
            album_list = [album_list[i-1] for i in indices]
            print(f"  → 已选 {len(album_list)} 个相册")
    else:
        print(f"  → 全部 {len(album_list)} 个相册")

    # ── 收集视频详情 ──
    print(f"\n📂 收集视频详情...")
    videos = collect_videos(album_list, cookie_raw, target)
    print(f"\n🎬 共 {len(videos)} 个视频待捕获")
    if not videos:
        print("⚠ 所选相册中无视频"); sys.exit(1)

    # ── Step 2: Selenium 捕获 ──
    if not SELENIUM_OK:
        print("\n⚠ 需要安装 Selenium 才能捕获视频 URL")
        print("   pip install selenium webdriver-manager")
        sys.exit(1)

    browsers = []
    for b in ["chrome", "edge", "firefox"]:
        try:
            if b == "chrome":
                ChromeDriverManager().install()
            elif b == "edge":
                EdgeChromiumDriverManager().install()
            elif b == "firefox":
                GeckoDriverManager().install()
            browsers.append(b)
        except:
            pass

    print(f"\n  检测到浏览器: {', '.join(browsers)}")
    choice = input(f"请选择 [{browsers[0] if browsers else 'chrome'}]: ").strip().lower()
    browser = choice if choice in browsers else (browsers[0] if browsers else "chrome")

    headless = input("后台运行？[Y/n]: ").strip().lower() != "n"
    if headless:
        print("  → 静默运行中，你可以做其他事情...")

    results = capture_video_urls(videos, cookie_raw, browser, headless)

    # ── Step 3: 下载 ──
    if results:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print(f"\n{'='*60}")
        print(f"📥 下载 {len(results)} 个视频到 {OUTPUT_DIR}/")
        print(f"{'='*60}\n")

        for i, (album, name, url) in enumerate(results, 1):
            aname = safe_name(album)
            vname = safe_name(name) or f"video_{i}"
            fname = f"{i:03d}_{aname}_{vname}.mp4"
            fpath = os.path.join(OUTPUT_DIR, fname)
            download_video(url, fpath, desc=f"[{i}/{len(results)}] {vname}")

        print(f"\n✅ 完成！保存到: {os.path.abspath(OUTPUT_DIR)}")
    else:
        print("\n❌ 未捕获到任何视频 URL")
        print("建议：设置 headless=n，观察浏览器中视频是否能正常打开")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠ 用户中断")
        sys.exit(1)
