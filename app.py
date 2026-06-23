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
    list_albums, list_photos, PROXY
)

# ── 配置 ──
app = Flask(__name__)
app.secret_key = "qqzone-gui-secret-key-2026"
app.config['JSON_AS_ASCII'] = False
app.config['OUTPUT_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qqzone_downloads")
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qqzone_cookie.txt")

DOWNLOAD_STATE = {
    "running": False, "current": "", "total": 0,
    "done": 0, "success": 0, "failed": 0,
    "finished": False, "albums": [],
    "new_total": 0,  # 增量模式下的新增照片数
}


def set_global_cookie(cookie_str: str):
    """设置 qqzone_downloader 模块的全局 Cookie 变量"""
    # 清洗：只保留 ASCII 可打印字符（Cookie 规范要求）
    clean = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    qzd.G_COOKIE_STR = clean
    qzd.G_COOKIES = parse_cookies(clean)


# ── 用户设置 ──

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qqzone_settings.json")


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
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        return jsonify({"ok": False, "msg": "请安装：pip install selenium webdriver-manager"})

    def login_thread():
        try:
            opts = Options()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-gpu")
            try:
                driver = webdriver.Chrome(
                    service=webdriver.chrome.service.Service(ChromeDriverManager().install()),
                    options=opts)
            except TypeError:
                driver = webdriver.Chrome(
                    executable_path=str(ChromeDriverManager().install()),
                    options=opts)

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
            driver.quit()
        except Exception as e:
            app.config["QR_RESULT"] = {"ok": False, "msg": f"扫码失败: {str(e)[:80]}"}

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

    albums = list_albums(uin, uin, g_tk, qzt)
    if not albums:
        return jsonify({"ok": False, "msg": "未获取到相册"})

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

            photos = list_photos(uin, uin, alb["id"], g_tk, qzt)
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
                    if not ph.get("url"):
                        DOWNLOAD_STATE["done"] += 1
                        continue
                    ext = ".jpg"
                    path = unquote(ph["url"].split("?")[0])
                    e = os.path.splitext(path)[1].lower()
                    if e in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
                        ext = e
                    fn = safe_name(ph["name"]) or f"{prefix}_{ph['id'][:8]}"
                    fp = os.path.join(adir, sub_dir, f"{existing + pi:04d}_{fn}{ext}")
                    tasks.append((ph, fp, sub_dir))

            # 并发下载
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                fut_to_ph = {}
                for ph, fp, sub_dir in tasks:
                    desc = f"[{origin_idx}] {alb['name']}: {ph.get('name','') or safe_name(ph['id'][:8])}"
                    fut = executor.submit(qzd.download_file, ph["url"], fp)
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
        base = os.path.dirname(os.path.abspath(__file__))
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
