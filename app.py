#!/usr/bin/env python3
"""
QQ 空间相册导出器 — GUI 版（Flask Web）

一键启动，浏览器操作，小白也能上手。

启动方式：
  python app.py
  浏览器自动打开 http://localhost:5800
"""

import os, sys, json, time, re, threading, subprocess, webbrowser, logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from urllib.parse import unquote

# 复用核心功能 — 用 import module 方式以便修改其中的全局变量
import qqzone_downloader as qzd
from qqzone_downloader import (
    parse_cookies, extract_qq, calc_gtk,
    fetch_qzonetoken, safe_name,
    list_albums, list_photos, list_videos_in_album, capture_video_urls,
    get_video_url, download_file,
    PROXY
)

# ── 配置 ──
# PyInstaller 打包兼容：frozen 时资源在临时目录，用户数据在 exe 所在目录
if getattr(sys, 'frozen', False):
    RESOURCE_DIR = sys._MEIPASS
    USER_DIR = os.path.dirname(sys.executable)
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    USER_DIR = RESOURCE_DIR

app = Flask(__name__,
            template_folder=os.path.join(RESOURCE_DIR, 'templates'),
            static_folder=os.path.join(RESOURCE_DIR, 'static'))
app.secret_key = "qqzone-gui-secret-key-2026"
app.config['JSON_AS_ASCII'] = False
app.config['OUTPUT_DIR'] = os.path.join(USER_DIR, "qqzone_downloads")
COOKIE_FILE = os.path.join(USER_DIR, "qqzone_cookie.txt")

DOWNLOAD_STATE = {
    "running": False, "current": "", "total": 0,
    "done": 0, "success": 0, "failed": 0,
    "finished": False, "albums": [],
    "new_total": 0,  # 增量模式下的新增照片数
}

VIDEO_DOWNLOAD_STATE = {
    "running": False, "current": "", "total": 0,
    "done": 0, "success": 0, "failed": 0,
    "finished": False, "albums": [],
}


def set_global_cookie(cookie_str: str):
    """设置 qqzone_downloader 模块的全局 Cookie 变量"""
    # 清洗：只保留 ASCII 可打印字符（Cookie 规范要求）
    clean = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    qzd.G_COOKIE_STR = clean
    qzd.G_COOKIES = parse_cookies(clean)


# ── 用户设置 ──

SETTINGS_FILE = os.path.join(USER_DIR, "qqzone_settings.json")


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_settings(s: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# 加载已保存的输出目录
_settings = load_settings()
if "output_dir" in _settings:
    app.config['OUTPUT_DIR'] = _settings["output_dir"]


# ── 增量下载清单 ──

MANIFEST_FILE = ".manifest.json"


def load_manifest(album_dir: str) -> dict:
    """加载已下载的照片清单"""
    path = os.path.join(album_dir, MANIFEST_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_manifest(album_dir: str, manifest: dict):
    """保存照片清单"""
    path = os.path.join(album_dir, MANIFEST_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def get_photo_key(photo: dict) -> str:
    """用完整 URL 作为照片唯一标识"""
    return photo.get("url", photo.get("id", ""))


def count_new_photos(album_dir: str, photos: list) -> int:
    """统计有多少照片尚未下载"""
    manifest = load_manifest(album_dir)
    if not manifest:
        return len(photos)
    return sum(1 for p in photos if get_photo_key(p) not in manifest)


# ═══════════════════════════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════

@app.route("/api/check_cookie")
def api_check_cookie():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
        if cookie_str:
            cookies = parse_cookies(cookie_str)
            uin = extract_qq(cookies) or ""
            skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
            if skey and uin:
                return jsonify({"has_cookie": True, "uin": uin})
    return jsonify({"has_cookie": False})


@app.route("/api/login_by_cookie", methods=["POST"])
def api_login_by_cookie():
    data = request.get_json()
    cookie_str = (data or {}).get("cookie", "").strip()
    # 清洗不可见字符
    cookie_str = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    if not cookie_str:
        return jsonify({"ok": False, "msg": "Cookie 不能为空"})

    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies)
    if not uin:
        return jsonify({"ok": False, "msg": "无法提取 QQ 号，请检查是否完整复制"})

    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "缺少登录密钥 (p_skey/skey)"})

    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        f.write(cookie_str)
    set_global_cookie(cookie_str)

    return jsonify({"ok": True, "uin": uin})


@app.route("/api/qrcode_login")
def api_qrcode_login():
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.microsoft import EdgeChromiumDriverManager
    except ImportError:
        return jsonify({"ok": False, "msg": "请安装：pip install selenium webdriver-manager"})

    def _launch_browser():
        """尝试 Chrome → Edge 顺序启动浏览器，返回 (driver, name)"""
        browsers = [
            ("Chrome", ChromeOptions, webdriver.Chrome, ChromeDriverManager),
            ("Edge",   EdgeOptions,   webdriver.Edge,   EdgeChromiumDriverManager),
        ]
        last_error = None
        for name, Opts, Driver, DrvMgr in browsers:
            try:
                opts = Opts()
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-gpu")
                # Edge 额外：禁用首次运行向导
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
                return driver, name
            except Exception as e:
                last_error = str(e)[:100]
                continue
        raise RuntimeError(f"无法启动浏览器（Chrome / Edge 均失败）: {last_error}")

    def login_thread():
        driver = None
        browser_name = ""
        try:
            driver, browser_name = _launch_browser()
            print(f"  🖥 扫码登录使用: {browser_name}")

            # 直接访问 i.qq.com，让平台自己处理登录流程
            driver.get("https://i.qq.com/")

            # 等待登录完成：扫码确认后会自动跳转到 user.qzone.qq.com/{uin}
            WebDriverWait(driver, 120).until(
                lambda d: "user.qzone.qq.com" in d.current_url and "ptlogin" not in d.current_url
            )
            time.sleep(3)

            try:
                cdp = driver.execute_cdp_cmd("Network.getAllCookies", {})
                cookies_dict = {c["name"]: c["value"] for c in cdp.get("cookies", [])}
            except:
                cookies_dict = {c["name"]: c["value"] for c in driver.get_cookies()}

            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
            uin = extract_qq(cookies_dict) or ""

            if "p_skey" in cookies_dict and uin:
                with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                    f.write(cookie_str)
                app.config["QR_RESULT"] = {"ok": True, "uin": uin}
            else:
                app.config["QR_RESULT"] = {"ok": False, "msg": "Cookie 不全，请尝试方式 2"}
        except Exception as e:
            app.config["QR_RESULT"] = {"ok": False, "msg": f"扫码失败: {str(e)[:80]}"}
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    app.config["QR_RESULT"] = None
    threading.Thread(target=login_thread, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """退出登录，删除 Cookie"""
    if os.path.exists(COOKIE_FILE):
        os.remove(COOKIE_FILE)
    qzd.G_COOKIE_STR = ""
    qzd.G_COOKIES = {}
    app.config["QR_RESULT"] = None
    app.config["ALBUMS"] = []
    app.config["PHOTO_CACHE"] = {}
    app.config["VIDEO_URL_CACHE"] = {}
    return jsonify({"ok": True})


@app.route("/api/qrcode_status")
def api_qrcode_status():
    r = app.config.get("QR_RESULT")
    if r is None:
        return jsonify({"status": "waiting"})
    return jsonify({"status": "done", **r})


@app.route("/api/albums")
def api_albums():
    cookie_str = ""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()

    if not cookie_str:
        return jsonify({"ok": False, "msg": "未登录"})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 已过期"})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    try:
        albums = list_albums(uin, uin, g_tk, qzt)
    except Exception as e:
        return jsonify({"ok": False, "msg": f"获取相册时出错，请检查网络或重新登录", "detail": str(e)[:120]})

    if not albums:
        # 登录成功但无相册：可能是空间未开通或相册为空
        return jsonify({"ok": False, "msg": "该账号下没有相册，可能未开通 QQ 空间或相册为空"})

    result = []
    for idx, a in enumerate(albums, 1):
        result.append({
            "id": a["id"],
            "name": a["name"],
            "count": a["photo_count"],
            "origin_idx": idx,
        })
    # 存储时带上原始序号
    app.config["ALBUMS"] = [(idx, a) for idx, a in enumerate(albums, 1)]
    app.config["UIN"] = uin
    app.config["G_TK"] = g_tk
    app.config["QZT"] = qzt
    return jsonify({"ok": True, "albums": result, "uin": uin})


@app.route("/api/download/start", methods=["POST"])
def api_download_start():
    global DOWNLOAD_STATE
    data = request.get_json() or {}
    indices = data.get("indices", [])
    download_video = data.get("download_video", True)
    max_workers = min(max(int(data.get("max_workers", 5)), 1), 20)
    albums_with_idx = app.config.get("ALBUMS", [])

    if not albums_with_idx:
        return jsonify({"ok": False, "msg": "请先刷新相册列表"})

    # selected 保持为 (origin_idx, album) 的列表
    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("UIN", "")
    g_tk = app.config.get("G_TK", 0)
    qzt = app.config.get("QZT", "")

    # 确保 Cookie 已设置
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            set_global_cookie(f.read().strip())

    # 查找已有相册目录的函数
    def find_album_dir(base: str, album_name: str) -> str:
        """检查是否已有同名相册目录，有则复用"""
        aname = safe_name(album_name) or ""
        if not aname or not os.path.isdir(base):
            return ""
        for d in sorted(os.listdir(base)):
            if d.endswith("_" + aname):
                return os.path.join(base, d)
        return ""

    DOWNLOAD_STATE = {
        "running": True, "current": "", "total": sum(alb["photo_count"] for _, alb in selected),
        "done": 0, "success": 0, "failed": 0, "finished": False,
        "albums": [alb["name"] for _, alb in selected],
        "new_total": 0,
    }

    def run():
        global DOWNLOAD_STATE
        from concurrent.futures import ThreadPoolExecutor, as_completed

        for origin_idx, alb in selected:
            if not DOWNLOAD_STATE["running"]:
                break
            aname = safe_name(alb["name"]) or f"album_{alb['id'][:8]}"
            # 优先复用已有目录
            existing_dir = find_album_dir(os.path.join(app.config['OUTPUT_DIR'], uin), alb["name"])
            if existing_dir:
                adir = existing_dir
            else:
                adir = os.path.join(app.config['OUTPUT_DIR'], uin, f"{origin_idx:02d}_{aname}")
            DOWNLOAD_STATE["current"] = f"获取: {alb['name']}..."
            os.makedirs(adir, exist_ok=True)

            # 优先从缓存取照片列表
            photo_cache = app.config.setdefault("PHOTO_CACHE", {})
            if alb["id"] in photo_cache:
                photos = photo_cache[alb["id"]]
            else:
                photos = list_photos(uin, uin, alb["id"], g_tk, qzt)
                photo_cache[alb["id"]] = photos
            if not photos:
                print(f"  ⚠ {alb['name']}: list_photos 返回空")
                DOWNLOAD_STATE["failed"] += 1
                continue

            # 过滤视频
            if not download_video:
                photos = [p for p in photos if not p.get("is_video")]

            if not photos:
                continue

                        # 加载已下载清单，剔除已存在的
            manifest = load_manifest(adir)
            new_photos = []
            new_videos = []
            for ph in photos:
                key = get_photo_key(ph)
                if key not in manifest:
                    if ph.get("is_video"):
                        new_videos.append(ph)
                    else:
                        new_photos.append(ph)

            print(f"  {alb['name']}: 共 {len(photos)} 张，清单已有 {len(manifest)} 张，"
                  f"新增照片 {len(new_photos)} 张" +
                  (f"，视频封面 {len(new_videos)} 张" if new_videos else ""))
            existing_total = len(manifest)

            if not new_photos and not (download_video and new_videos):
                DOWNLOAD_STATE["current"] = f"⏭ {alb['name']}: 无新增"
                for _ in photos:
                    DOWNLOAD_STATE["done"] += 1
                time.sleep(0.3)
                continue

            tasks = []
            for items, sub_dir, prefix in [
                (new_photos, "图片", "photo"),
                (new_videos if download_video else [], "视频封面", "video"),
            ]:
                if not items:
                    continue
                os.makedirs(os.path.join(adir, sub_dir), exist_ok=True)
                existing = sum(1 for k, v in manifest.items() if v.startswith(sub_dir + "/"))
                for pi, ph in enumerate(items, 1):
                    download_url = ph.get("url", "")
                    if not download_url:
                        DOWNLOAD_STATE["done"] += 1
                        continue

                    # 视频：通过 floatview API 获取真实下载 URL
                    if sub_dir == "视频封面":
                        real_url = get_video_url(uin, uin, alb["id"], ph.get("lloc", ""), g_tk)
                        if real_url:
                            download_url = real_url
                        ext = ".mp4"
                    else:
                        path = unquote(download_url.split("?")[0])
                        e = os.path.splitext(path)[1].lower()
                        ext = e if e in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp") else ".jpg"

                    fn = safe_name(ph["name"]) or f"{prefix}_{ph['id'][:8]}"
                    fp = os.path.join(adir, sub_dir, f"{existing + pi:04d}_{fn}{ext}")
                    tasks.append((download_url, fp, sub_dir, ph))

            # 并发下载
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                fut_to_ph = {}
                for dl_url, fp, sub_dir, ph in tasks:
                    desc = f"[{origin_idx}] {alb['name']}: {ph.get('name','') or safe_name(ph['id'][:8])}"
                    fut = executor.submit(qzd.download_file, dl_url, fp)
                    fut_to_ph[fut] = (ph, fp, sub_dir, desc)

                for fut in as_completed(fut_to_ph):
                    ph, fp, sub_dir, desc = fut_to_ph[fut]
                    DOWNLOAD_STATE["current"] = desc
                    if fut.result():
                        key = get_photo_key(ph)
                        manifest[key] = os.path.join(sub_dir, os.path.basename(fp))
                        DOWNLOAD_STATE["success"] += 1
                    else:
                        DOWNLOAD_STATE["failed"] += 1
                    DOWNLOAD_STATE["done"] += 1
                    time.sleep(0.05)

            save_manifest(adir, manifest)

        DOWNLOAD_STATE["current"] = "完成！"
        DOWNLOAD_STATE["finished"] = True
        DOWNLOAD_STATE["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True, "total": DOWNLOAD_STATE["total"]})


@app.route("/api/download/progress")
def api_download_progress():
    return jsonify(DOWNLOAD_STATE)


@app.route("/api/download/stop", methods=["POST"])
def api_download_stop():
    DOWNLOAD_STATE["running"] = False
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# 视频导出 API
# ═══════════════════════════════════════════════════════════════

@app.route("/api/video/albums")
def api_video_albums():
    """返回含有视频的相册列表（并行扫描 + 预缓存视频链接）"""
    cookie_str = ""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    if not cookie_str:
        return jsonify({"ok": False, "msg": "未登录"})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 已过期"})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    albums = list_albums(uin, uin, g_tk, qzt)
    if not albums:
        return jsonify({"ok": False, "msg": "未获取到相册"})

    # 并行扫描 — 重建缓存
    video_cache = {}
    photo_cache = {}
    app.config["VIDEO_URL_CACHE"] = video_cache
    app.config["PHOTO_CACHE"] = photo_cache
    print(f"\n🎬 扫描视频相册...（共 {len(albums)} 个相册，5 线程并行）")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _scan_one(a):
        try:
            vids = list_videos_in_album(uin, uin, a["id"], g_tk, qzt)
            return (a, vids, None)
        except Exception as e:
            return (a, [], str(e)[:60])

    result = []

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_scan_one, a): a for a in albums}
        for fut in as_completed(futs):
            a, vids, err = fut.result()
            if err:
                continue
            if vids:
                idx = albums.index(a) + 1
                result.append({
                    "id": a["id"], "name": a["name"],
                    "count": len(vids), "origin_idx": idx,
                })
                print(f"  [{len(result):2d}] {a['name']} — {len(vids)} 个视频")
                # 缓存视频列表和预取视频 URL
                photo_cache[a["id"]] = vids
                for v in vids:
                    pic_key = v.get("lloc", "")
                    if pic_key and (a["id"], pic_key) not in video_cache:
                        vurl = get_video_url(uin, uin, a["id"], pic_key, g_tk)
                        if vurl:
                            video_cache[(a["id"], pic_key)] = vurl

    # 按 origin_idx 排序
    result.sort(key=lambda x: x["origin_idx"])
    print(f"  ✓ 共 {len(result)} 个相册含有视频\n")

    if not result:
        return jsonify({"ok": False, "msg": "该账号下没有含视频的相册"})

    app.config["VIDEO_ALBUMS"] = [(r["origin_idx"], next(a for a in albums if a["id"] == r["id"])) for r in result]
    app.config["VIDEO_UIN"] = uin
    app.config["VIDEO_G_TK"] = g_tk
    app.config["VIDEO_QZT"] = qzt
    return jsonify({"ok": True, "albums": result, "uin": uin})


@app.route("/api/video/download/start", methods=["POST"])
def api_video_download_start():
    global VIDEO_DOWNLOAD_STATE
    data = request.get_json() or {}
    indices = data.get("indices", [])
    max_workers = min(max(int(data.get("max_workers", 3)), 1), 10)
    albums_with_idx = app.config.get("VIDEO_ALBUMS", [])

    if not albums_with_idx:
        return jsonify({"ok": False, "msg": "请先刷新视频列表"})

    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("VIDEO_UIN", "")
    g_tk = app.config.get("VIDEO_G_TK", 0)
    qzt = app.config.get("VIDEO_QZT", "")

    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    else:
        cookie_str = ""

    # 从缓存或 API 获取视频列表
    photo_cache = app.config.get("PHOTO_CACHE", {})
    all_videos = []
    for origin_idx, alb in selected:
        if alb["id"] in photo_cache:
            photos = photo_cache[alb["id"]]
        else:
            photos = list_photos(uin, uin, alb["id"], g_tk, qzt)
            photo_cache[alb["id"]] = photos
        for p in photos:
            if p.get("is_video"):
                p["album_name"] = alb["name"]
                p["album_id"] = alb["id"]
                p["origin_idx"] = origin_idx
                p["uin"] = uin
                all_videos.append(p)

    if not all_videos:
        return jsonify({"ok": False, "msg": "所选相册中没有视频"})

    # 使用缓存中的视频链接（api_video_albums 已预取）
    video_cache = app.config.get("VIDEO_URL_CACHE", {})
    photo_cache = app.config.get("PHOTO_CACHE", {})

    VIDEO_DOWNLOAD_STATE = {
        "running": True, "current": "", "total": len(all_videos),
        "done": 0, "success": 0, "failed": 0,
        "finished": False, "albums": [alb["name"] for _, alb in selected],
    }

    def run():
        global VIDEO_DOWNLOAD_STATE
        from concurrent.futures import ThreadPoolExecutor, as_completed

        output_base = os.path.join(app.config['OUTPUT_DIR'], uin)
        os.makedirs(output_base, exist_ok=True)

        # 第一步：从缓存 / API 获取视频下载链接
        VIDEO_DOWNLOAD_STATE["current"] = "正在获取视频下载链接..."
        print(f"\n🎬 获取 {len(all_videos)} 个视频的下载链接...")
        urls = []
        for i, v in enumerate(all_videos, 1):
            pic_key = v.get("lloc", "")
            if not pic_key:
                continue
            cache_key = (v["album_id"], pic_key)
            # 优先从缓存取
            if cache_key in video_cache:
                video_url = video_cache[cache_key]
            else:
                video_url = get_video_url(uin, uin, v["album_id"], pic_key, g_tk)
                if video_url:
                    video_cache[cache_key] = video_url
            if video_url:
                desc = v.get("name", "") or pic_key[:12]
                print(f"  ✅ [{i}/{len(all_videos)}] {desc}")
                urls.append({
                    "album": v.get("album_name", ""),
                    "name": v.get("name", desc),
                    "url": video_url,
                    "origin_idx": v.get("origin_idx", 0),
                })
            VIDEO_DOWNLOAD_STATE["done"] = i
            time.sleep(0.05)

        if not urls:
            VIDEO_DOWNLOAD_STATE["current"] = "未获取到任何视频链接"
            VIDEO_DOWNLOAD_STATE["finished"] = True
            VIDEO_DOWNLOAD_STATE["running"] = False
            return

        # 第二步：并发下载
        VIDEO_DOWNLOAD_STATE["total"] = len(urls)
        VIDEO_DOWNLOAD_STATE["done"] = 0
        VIDEO_DOWNLOAD_STATE["current"] = "正在下载..."
        tasks = []
        for idx, item in enumerate(urls, 1):
            aname = safe_name(item["album"]) or "unknown"
            oidx = item.get("origin_idx", 0)
            vname = safe_name(item["name"]) or f"video_{idx}"
            ext = ".mp4"
            path_part = item["url"].split("?")[0]
            e = os.path.splitext(path_part)[1].lower()
            if e in (".mp4", ".webm", ".ts", ".mov"):
                ext = e
            adir = os.path.join(output_base, f"{oidx:02d}_{aname}", "视频")
            os.makedirs(adir, exist_ok=True)
            fp = os.path.join(adir, f"{idx:03d}_{vname}{ext}")
            tasks.append((item["url"], fp, f"[{idx}/{len(urls)}] {item['name']}"))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_to_task = {}
            for url, fp, desc in tasks:
                fut = executor.submit(qzd.download_file, url, fp)
                fut_to_task[fut] = (fp, desc)

            for fut in as_completed(fut_to_task):
                fp, desc = fut_to_task[fut]
                VIDEO_DOWNLOAD_STATE["current"] = desc
                if fut.result():
                    VIDEO_DOWNLOAD_STATE["success"] += 1
                else:
                    VIDEO_DOWNLOAD_STATE["failed"] += 1
                VIDEO_DOWNLOAD_STATE["done"] += 1
                time.sleep(0.05)

        VIDEO_DOWNLOAD_STATE["current"] = "完成！"
        VIDEO_DOWNLOAD_STATE["finished"] = True
        VIDEO_DOWNLOAD_STATE["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True, "total": VIDEO_DOWNLOAD_STATE["total"]})


@app.route("/api/video/download/progress")
def api_video_download_progress():
    return jsonify(VIDEO_DOWNLOAD_STATE)


@app.route("/api/video/download/stop", methods=["POST"])
def api_video_download_stop():
    VIDEO_DOWNLOAD_STATE["running"] = False
    return jsonify({"ok": True})


@app.route("/api/pick_directory")
def api_pick_directory():
    """打开系统原生目录选择对话框"""
    folder = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="选择输出目录")
        root.destroy()
    except:
        pass

    if folder:
        app.config['OUTPUT_DIR'] = folder
        os.makedirs(folder, exist_ok=True)
        save_settings({"output_dir": folder})
        return jsonify({"ok": True, "output_dir": folder})
    return jsonify({"ok": False, "msg": ""})  # 取消选择 = 不报错


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify({"ok": True, "output_dir": app.config['OUTPUT_DIR']})
    # POST: 手动设置路径（也接受 pick_directory 的更新）
    data = request.get_json() or {}
    out_dir = data.get("output_dir", "").strip()
    if out_dir:
        base = USER_DIR
        if not os.path.isabs(out_dir) and "/" not in out_dir and "\\" not in out_dir:
            out_dir = os.path.join(base, out_dir)
        app.config['OUTPUT_DIR'] = out_dir
        os.makedirs(out_dir, exist_ok=True)
        save_settings({"output_dir": out_dir})
        return jsonify({"ok": True, "output_dir": out_dir})
    return jsonify({"ok": False, "msg": "路径不能为空"})
    return jsonify({"ok": True, "output_dir": app.config['OUTPUT_DIR']})


@app.route("/api/open_output")
def api_open_output():
    path = app.config['OUTPUT_DIR']
    if os.path.isdir(path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "msg": str(e)})
    return jsonify({"ok": False, "msg": "目录不存在"})


# ═══════════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    port = 5800
    print(f"""
╔══════════════════════════════════════════╗
║     QQ 空间相册导出器 · GUI 版           ║
║                                          ║
║  http://localhost:{port}                  ║
║                                          ║
║  浏览器已自动打开                        ║
╚══════════════════════════════════════════╝
""")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
