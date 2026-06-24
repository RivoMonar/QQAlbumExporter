#!/usr/bin/env python3
"""
QQ 绌洪棿鐩稿唽瀵煎嚭鍣?鈥?GUI 鐗堬紙Flask Web锛?

涓€閿惎鍔紝娴忚鍣ㄦ搷浣滐紝灏忕櫧涔熻兘涓婃墜銆?

鍚姩鏂瑰紡锛?
  python app.py
  娴忚鍣ㄨ嚜鍔ㄦ墦寮€ http://localhost:5800
"""

import os, sys, json, time, re, threading, subprocess, webbrowser, logging, signal, requests
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from urllib.parse import unquote

# 澶嶇敤鏍稿績鍔熻兘 鈥?鐢?import module 鏂瑰紡浠ヤ究淇敼鍏朵腑鐨勫叏灞€鍙橀噺
import qqzone_downloader as qzd
from qqzone_downloader import (
    parse_cookies, extract_qq, calc_gtk,
    fetch_qzonetoken, safe_name,
    list_albums, list_photos, list_videos_in_album,
    get_video_url, download_file,
    PROXY
)

# 鈹€鈹€ 閰嶇疆 鈹€鈹€
VERSION = "2.2.3"

# PyInstaller 鎵撳寘鍏煎锛歠rozen 鏃惰祫婧愬湪涓存椂鐩綍锛岀敤鎴锋暟鎹湪 exe 鎵€鍦ㄧ洰褰?
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
    "new_total": 0,  # 澧為噺妯″紡涓嬬殑鏂板鐓х墖鏁?
}

VIDEO_DOWNLOAD_STATE = {
    "running": False, "current": "", "total": 0,
    "done": 0, "success": 0, "failed": 0,
    "finished": False, "albums": [],
}


def set_global_cookie(cookie_str: str):
    """璁剧疆 qqzone_downloader 妯″潡鐨勫叏灞€ Cookie 鍙橀噺"""
    # 娓呮礂锛氬彧淇濈暀 ASCII 鍙墦鍗板瓧绗︼紙Cookie 瑙勮寖瑕佹眰锛?
    clean = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    qzd.G_COOKIE_STR = clean
    qzd.G_COOKIES = parse_cookies(clean)


# 鈹€鈹€ 鐢ㄦ埛璁剧疆 鈹€鈹€

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


# 鍔犺浇宸蹭繚瀛樼殑杈撳嚭鐩綍
_settings = load_settings()
if "output_dir" in _settings:
    app.config['OUTPUT_DIR'] = _settings["output_dir"]


# 鈹€鈹€ 澧為噺涓嬭浇娓呭崟 鈹€鈹€

MANIFEST_FILE = ".manifest.json"


def load_manifest(album_dir: str) -> dict:
    """鍔犺浇宸蹭笅杞芥竻鍗曪紝鑷姩娓呯悊宸插垹闄ゆ枃浠剁殑杩囨湡鏉＄洰"""
    path = os.path.join(album_dir, MANIFEST_FILE)
    manifest = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 娓呴櫎纾佺洏涓婂凡涓嶅瓨鍦ㄧ殑鏂囦欢鐨勮褰?
            cleaned = False
            for key, rel_path in list(raw.items()):
                fp = os.path.join(album_dir, rel_path)
                if os.path.exists(fp):
                    manifest[key] = rel_path
                else:
                    cleaned = True
            if cleaned:
                save_manifest(album_dir, manifest)
        except:
            pass
    return manifest


def save_manifest(album_dir: str, manifest: dict):
    """淇濆瓨鐓х墖娓呭崟"""
    path = os.path.join(album_dir, MANIFEST_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def get_photo_key(photo: dict) -> str:
    """鐢?lloc + url 鍓?60 瀛楃浣滀负鐓х墖鍞竴鏍囪瘑"""
    return (photo.get("lloc", "") or photo.get("url", "") or photo.get("id", ""))[:80]


def count_new_photos(album_dir: str, photos: list) -> int:
    """缁熻鏈夊灏戠収鐗囧皻鏈笅杞?""
    manifest = load_manifest(album_dir)
    if not manifest:
        return len(photos)
    return sum(1 for p in photos if get_photo_key(p) not in manifest)


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# 椤甸潰璺敱
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

@app.route("/")
def index():
    return render_template("index.html")


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# API 璺敱
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

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
    # 娓呮礂涓嶅彲瑙佸瓧绗?
    cookie_str = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    if not cookie_str:
        return jsonify({"ok": False, "msg": "Cookie 涓嶈兘涓虹┖"})

    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies)
    if not uin:
        return jsonify({"ok": False, "msg": "鏃犳硶鎻愬彇 QQ 鍙凤紝璇锋鏌ユ槸鍚﹀畬鏁村鍒?})

    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "缂哄皯鐧诲綍瀵嗛挜 (p_skey/skey)"})

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
        return jsonify({"ok": False, "msg": "璇峰畨瑁咃細pip install selenium webdriver-manager"})

    def _launch_browser():
        """灏濊瘯 Chrome 鈫?Edge 椤哄簭鍚姩娴忚鍣紝杩斿洖 (driver, name)"""
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
                # Edge 棰濆锛氱鐢ㄩ娆¤繍琛屽悜瀵?
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
        raise RuntimeError(f"鏃犳硶鍚姩娴忚鍣紙Chrome / Edge 鍧囧け璐ワ級: {last_error}")

    def login_thread():
        driver = None
        browser_name = ""
        try:
            driver, browser_name = _launch_browser()
            print(f"  馃枼 鎵爜鐧诲綍浣跨敤: {browser_name}")

            # 鐩存帴璁块棶 i.qq.com锛岃骞冲彴鑷繁澶勭悊鐧诲綍娴佺▼
            driver.get("https://i.qq.com/")

            # 绛夊緟鐧诲綍瀹屾垚锛氭壂鐮佺‘璁ゅ悗浼氳嚜鍔ㄨ烦杞埌 user.qzone.qq.com/{uin}
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
                app.config["QR_RESULT"] = {"ok": False, "msg": "Cookie 涓嶅叏锛岃灏濊瘯鏂瑰紡 2"}
        except Exception as e:
            app.config["QR_RESULT"] = {"ok": False, "msg": f"鎵爜澶辫触: {str(e)[:80]}"}
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
    """閫€鍑虹櫥褰曪紝鍒犻櫎 Cookie 鍜岀紦瀛?""
    # 鍒犻櫎鍓嶆彁鍙?uin 鐢ㄤ簬娓呯紦瀛?
    uin = ""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = parse_cookies(f.read().strip())
            uin = extract_qq(cookies) or ""
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
        return jsonify({"ok": False, "msg": "鏈櫥褰?})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 宸茶繃鏈?})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    try:
        albums = list_albums(uin, uin, g_tk, qzt)
    except Exception as e:
        return jsonify({"ok": False, "msg": f"鑾峰彇鐩稿唽鏃跺嚭閿欙紝璇锋鏌ョ綉缁滄垨閲嶆柊鐧诲綍", "detail": str(e)[:120]})

    if not albums:
        return jsonify({"ok": False, "msg": "璇ヨ处鍙蜂笅娌℃湁鐩稿唽锛屽彲鑳芥湭寮€閫?QQ 绌洪棿鎴栫浉鍐屼负绌?})

    result = []
    for idx, a in enumerate(albums, 1):
        result.append({
            "id": a["id"], "name": a["name"],
            "count": a["photo_count"], "origin_idx": idx,
            "cover": a.get("cover", ""),
        })
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
        return jsonify({"ok": False, "msg": "璇峰厛鍒锋柊鐩稿唽鍒楄〃"})

    # selected 淇濇寔涓?(origin_idx, album) 鐨勫垪琛?
    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("UIN", "")
    g_tk = app.config.get("G_TK", 0)
    qzt = app.config.get("QZT", "")

    # 纭繚 Cookie 宸茶缃?
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            set_global_cookie(f.read().strip())

    # 鏌ユ壘宸叉湁鐩稿唽鐩綍鐨勫嚱鏁?
    def find_album_dir(base: str, album_name: str) -> str:
        """妫€鏌ユ槸鍚﹀凡鏈夊悓鍚嶇浉鍐岀洰褰曪紝鏈夊垯澶嶇敤"""
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
            # 浼樺厛澶嶇敤宸叉湁鐩綍
            existing_dir = find_album_dir(os.path.join(app.config['OUTPUT_DIR'], uin), alb["name"])
            if existing_dir:
                adir = existing_dir
            else:
                adir = os.path.join(app.config['OUTPUT_DIR'], uin, f"{origin_idx:02d}_{aname}")
            DOWNLOAD_STATE["current"] = f"鑾峰彇: {alb['name']}..."
            os.makedirs(adir, exist_ok=True)

            # 浠?API 鑾峰彇鐓х墖鍒楄〃
            photos = list_photos(uin, uin, alb["id"], g_tk, qzt)
            if not photos:
                print(f"  鈿?{alb['name']}: list_photos 杩斿洖绌?)
                DOWNLOAD_STATE["failed"] += 1
                continue

            # 杩囨护瑙嗛
            if not download_video:
                photos = [p for p in photos if not p.get("is_video")]

            if not photos:
                continue

                        # 鍔犺浇宸蹭笅杞芥竻鍗曪紝鍓旈櫎宸插瓨鍦ㄧ殑
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

            print(f"  {alb['name']}: 鍏?{len(photos)} 寮狅紝娓呭崟宸叉湁 {len(manifest)} 寮狅紝"
                  f"鏂板鐓х墖 {len(new_photos)} 寮? +
                  (f"锛岃棰戝皝闈?{len(new_videos)} 寮? if new_videos else ""))
            existing_total = len(manifest)

            if not new_photos and not (download_video and new_videos):
                DOWNLOAD_STATE["current"] = f"鈴?{alb['name']}: 鏃犳柊澧?
                time.sleep(0.1)
                continue

            tasks = []
            for items, sub_dir, prefix in [
                (new_photos, "鍥剧墖", "photo"),
                (new_videos if download_video else [], "瑙嗛灏侀潰", "video"),
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

                    path = unquote(download_url.split("?")[0])
                    e = os.path.splitext(path)[1].lower()
                    ext = e if e in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp") else ".jpg"

                    fn = safe_name(ph["name"]) or f"{prefix}_{ph['id'][:8]}"
                    fp = os.path.join(adir, sub_dir, f"{existing + pi:04d}_{fn}{ext}")
                    tasks.append((download_url, fp, sub_dir, ph))

            # 骞跺彂涓嬭浇
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

        if DOWNLOAD_STATE["done"] == 0:
            DOWNLOAD_STATE["total"] = 0
        DOWNLOAD_STATE["current"] = "瀹屾垚锛?
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


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# 瑙嗛瀵煎嚭 API
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

@app.route("/api/video/albums")
def api_video_albums():
    """杩斿洖鍚湁瑙嗛鐨勭浉鍐屽垪琛?""
    cookie_str = ""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    if not cookie_str:
        return jsonify({"ok": False, "msg": "鏈櫥褰?})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 宸茶繃鏈?})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    albums = list_albums(uin, uin, g_tk, qzt)
    if not albums:
        return jsonify({"ok": False, "msg": "鏈幏鍙栧埌鐩稿唽"})

    # 骞惰鎵弿鍚棰戠殑鐩稿唽锛? 绾跨▼锛屾瘡涓浉鍐屽彧鎵竴娆★級
    from concurrent.futures import ThreadPoolExecutor, as_completed
    print(f"\n馃幀 鎵弿瑙嗛鐩稿唽...锛堝叡 {len(albums)} 涓浉鍐岋紝骞惰锛?)

    def _scan(idx, a):
        try:
            vids = list_videos_in_album(uin, uin, a["id"], g_tk, qzt)
            return (idx, a, len(vids) if vids else 0, None)
        except Exception as e:
            return (idx, a, 0, str(e)[:60])

    results_by_idx = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_scan, idx, a): idx for idx, a in enumerate(albums, 1)}
        for fut in as_completed(futs):
            idx, a, count, err = fut.result()
            if err:
                continue
            if count > 0:
                results_by_idx[idx] = (a, count)
                print(f"  [{len(results_by_idx):2d}] {a['name']} 鈥?{count} 涓棰?)

    result = [{"id": a["id"], "name": a["name"], "count": count, "origin_idx": idx, "cover": a.get("cover", "")}
              for idx, (a, count) in sorted(results_by_idx.items())]
    print(f"  鉁?鍏?{len(result)} 涓浉鍐屽惈鏈夎棰慭n")

    if not result:
        return jsonify({"ok": False, "msg": "璇ヨ处鍙蜂笅娌℃湁鍚棰戠殑鐩稿唽"})

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
        return jsonify({"ok": False, "msg": "璇峰厛鍒锋柊瑙嗛鍒楄〃"})

    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("VIDEO_UIN", "")
    g_tk = app.config.get("VIDEO_G_TK", 0)
    qzt = app.config.get("VIDEO_QZT", "")

    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    else:
        cookie_str = ""

    # 浠庣紦瀛樻垨 API 鑾峰彇瑙嗛鍒楄〃
    all_videos = []
    for origin_idx, alb in selected:
        photos = list_photos(uin, uin, alb["id"], g_tk, qzt)
        for p in photos:
            if p.get("is_video"):
                p["album_name"] = alb["name"]
                p["album_id"] = alb["id"]
                p["origin_idx"] = origin_idx
                p["uin"] = uin
                all_videos.append(p)

    if not all_videos:
        return jsonify({"ok": False, "msg": "鎵€閫夌浉鍐屼腑娌℃湁瑙嗛"})

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

        # 绗竴姝ワ細浠庣紦瀛?/ API 鑾峰彇瑙嗛涓嬭浇閾炬帴
        VIDEO_DOWNLOAD_STATE["current"] = "姝ｅ湪鑾峰彇瑙嗛涓嬭浇閾炬帴..."
        print(f"\n馃幀 鑾峰彇 {len(all_videos)} 涓棰戠殑涓嬭浇閾炬帴...")
        urls = []
        for i, v in enumerate(all_videos, 1):
            pic_key = v.get("lloc", "")
            if not pic_key:
                continue
            cache_key = (v["album_id"], pic_key)
            video_url = get_video_url(uin, uin, v["album_id"], pic_key, g_tk)
            if video_url:
                desc = v.get("name", "") or pic_key[:12]
                print(f"  鉁?[{i}/{len(all_videos)}] {desc}")
                urls.append({
                    "album": v.get("album_name", ""),
                    "name": v.get("name", desc),
                    "url": video_url,
                    "origin_idx": v.get("origin_idx", 0),
                })
            VIDEO_DOWNLOAD_STATE["done"] = i
            time.sleep(0.05)

        if not urls:
            VIDEO_DOWNLOAD_STATE["current"] = "鏈幏鍙栧埌浠讳綍瑙嗛閾炬帴"
            VIDEO_DOWNLOAD_STATE["finished"] = True
            VIDEO_DOWNLOAD_STATE["running"] = False
            return

        # 绗簩姝ワ細澧為噺骞跺彂涓嬭浇
        VIDEO_DOWNLOAD_STATE["done"] = 0
        VIDEO_DOWNLOAD_STATE["current"] = "姝ｅ湪涓嬭浇..."
        new_count = 0  # 瀹為檯鏂板涓嬭浇鏁?
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
            adir = os.path.join(output_base, f"{oidx:02d}_{aname}", "瑙嗛")
            os.makedirs(adir, exist_ok=True)
            fp = os.path.join(adir, f"{idx:03d}_{vname}{ext}")

            # 澧為噺锛氭鏌ユ槸鍚﹀凡涓嬭浇
            manifest = load_manifest(os.path.dirname(adir))
            if item["url"] in manifest:
                continue  # 璺宠繃锛屼笉璁″叆 total
            new_count += 1
            tasks.append((item["url"], fp, adir, f"[{idx}/{len(urls)}] {item['name']}"))

        if not tasks:
            VIDEO_DOWNLOAD_STATE["total"] = VIDEO_DOWNLOAD_STATE["done"]
            VIDEO_DOWNLOAD_STATE["current"] = "鍏ㄩ儴宸蹭笅杞斤紝鏃犻渶閲嶅"
            VIDEO_DOWNLOAD_STATE["finished"] = True
            VIDEO_DOWNLOAD_STATE["running"] = False
            return

        VIDEO_DOWNLOAD_STATE["total"] = VIDEO_DOWNLOAD_STATE["done"] + len(tasks)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_to_task = {}
            for url, fp, adir, desc in tasks:
                fut = executor.submit(qzd.download_file, url, fp)
                fut_to_task[fut] = (url, fp, adir, desc)

            for fut in as_completed(fut_to_task):
                url, fp, adir, desc = fut_to_task[fut]
                VIDEO_DOWNLOAD_STATE["current"] = desc
                if fut.result():
                    VIDEO_DOWNLOAD_STATE["success"] += 1
                    # 鍐欏叆澧為噺娓呭崟锛堜笌鐓х墖鍏辩敤鍚屼竴绾х洰褰曠殑 manifest锛?
                    parent_dir = os.path.dirname(adir)
                    manifest = load_manifest(parent_dir)
                    manifest[url] = os.path.join("瑙嗛", os.path.basename(fp))
                    save_manifest(parent_dir, manifest)
                else:
                    VIDEO_DOWNLOAD_STATE["failed"] += 1
                VIDEO_DOWNLOAD_STATE["done"] += 1
                time.sleep(0.05)

        VIDEO_DOWNLOAD_STATE["current"] = "瀹屾垚锛?
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


@app.route("/api/img_proxy")
def api_img_proxy():
    """浠ｇ悊 QZone 鍥剧墖锛岀粫杩囬槻鐩楅摼"""
    url = request.args.get("url", "")
    if not url or not url.startswith("http"):
        return "", 404
    try:
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Referer": "https://user.qzone.qq.com/",
            "Cookie": qzd.G_COOKIE_STR,
        }, timeout=10)
        if r.status_code == 200 and len(r.content) > 100:
            ct = r.headers.get("Content-Type", "image/jpeg")
            return r.content, 200, {"Content-Type": ct, "Cache-Control": "max-age=3600"}
    except Exception:
        pass
    return "", 404
def api_shutdown():
    """鍏抽棴鏈嶅姟"""
    DOWNLOAD_STATE["running"] = False
    VIDEO_DOWNLOAD_STATE["running"] = False
    threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/version")
def api_version():
    return jsonify({"version": VERSION})


@app.route("/api/check_update")
def api_check_update():
    """妫€鏌ユ洿鏂帮細鍏堟煡 VERSION 鏂囦欢锛堝揩锛夛紝鍐嶆煡 GitHub API锛堟湁璇︽儏锛?""
    current = VERSION.lstrip("v")
    latest = ""
    url = ""
    body = ""

    def parse_ver(v):
        parts = v.split(".")
        return tuple(int(p) for p in parts if p.isdigit())

    # 绗竴姝ワ細浠?GitHub 鍘熷鏂囦欢鑾峰彇鏈€鏂扮増鏈彿锛堝浗鍐呬篃鑳借闂級
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/RivoMonar/QQAlbumExporter/master/VERSION",
            timeout=8
        )
        if r.status_code == 200:
            latest = r.text.strip().lstrip("v")
    except Exception:
        pass

    # 绗簩姝ワ細琛ュ厖 Release 璇︽儏
    if latest:
        try:
            r2 = requests.get(
                "https://api.github.com/repos/RivoMonar/QQAlbumExporter/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=8
            )
            if r2.status_code == 200:
                data = r2.json()
                url = data.get("html_url", "")
                body = (data.get("body") or "")[:500]
        except Exception:
            pass
    else:
        # VERSION 鏂囦欢鑾峰彇澶辫触锛屽洖閫€鍒?GitHub API
        try:
            r = requests.get(
                "https://api.github.com/repos/RivoMonar/QQAlbumExporter/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                latest = data.get("tag_name", "").lstrip("v")
                url = data.get("html_url", "")
                body = (data.get("body") or "")[:500]
        except Exception:
            pass

    if not latest:
        return jsonify({"ok": False, "msg": "鏃犳硶鑾峰彇鏇存柊淇℃伅锛岃妫€鏌ョ綉缁?, "current": VERSION, "has_update": False})

    has_update = parse_ver(latest) > parse_ver(current)
    return jsonify({
        "ok": True,
        "current": VERSION,
        "latest": "v" + latest,
        "has_update": has_update,
        "url": url or f"https://github.com/RivoMonar/QQAlbumExporter/releases",
        "body": body,
    })


@app.route("/api/pick_directory")
def api_pick_directory():
    """鎵撳紑绯荤粺鍘熺敓鐩綍閫夋嫨瀵硅瘽妗?""
    folder = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="閫夋嫨杈撳嚭鐩綍")
        root.destroy()
    except:
        pass

    if folder:
        app.config['OUTPUT_DIR'] = folder
        os.makedirs(folder, exist_ok=True)
        save_settings({"output_dir": folder})
        return jsonify({"ok": True, "output_dir": folder})
    return jsonify({"ok": False, "msg": ""})  # 鍙栨秷閫夋嫨 = 涓嶆姤閿?


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify({"ok": True, "output_dir": app.config['OUTPUT_DIR']})
    # POST: 鎵嬪姩璁剧疆璺緞锛堜篃鎺ュ彈 pick_directory 鐨勬洿鏂帮級
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
    return jsonify({"ok": False, "msg": "璺緞涓嶈兘涓虹┖"})
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
    return jsonify({"ok": False, "msg": "鐩綍涓嶅瓨鍦?})


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# 鍚姩
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    port = 5800

    # 娉ㄥ唽 Ctrl+C 浼橀泤閫€鍑?
    def _on_exit(sig, frame):
        print("\n鈴?姝ｅ湪鍋滄...")
        DOWNLOAD_STATE["running"] = False
        VIDEO_DOWNLOAD_STATE["running"] = False
        os._exit(0)
    signal.signal(signal.SIGINT, _on_exit)
    signal.signal(signal.SIGTERM, _on_exit)

    print(f"""
鈺斺晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晽
鈺?    QQ 绌洪棿鐩稿唽瀵煎嚭鍣?路 GUI 鐗?          鈺?
鈺?                                         鈺?
鈺? http://localhost:{port}                  鈺?
鈺?                                         鈺?
鈺? 娴忚鍣ㄥ凡鑷姩鎵撳紑                        鈺?
鈺氣晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨暆
""")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
