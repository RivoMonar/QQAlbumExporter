#!/usr/bin/env python3
"""
QQ 缁屾椽妫块惄绋垮斀鐎电厧鍤崳?閳?GUI 閻楀牞绱橣lask Web閿?

娑撯偓闁款喖鎯庨崝顭掔礉濞村繗顫嶉崳銊︽惙娴ｆ粣绱濈亸蹇曟娑旂喕鍏樻稉濠冨閵?

閸氼垰濮╅弬鐟扮础閿?
  python app.py
  濞村繗顫嶉崳銊ㄥ殰閸斻劍澧﹀鈧?http://localhost:5800
"""

import os, sys, json, time, re, threading, subprocess, webbrowser, logging, signal, requests
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from urllib.parse import unquote

# 婢跺秶鏁ら弽绋跨妇閸旂喕鍏?閳?閻?import module 閺傜懓绱℃禒銉ょ┒娣囶喗鏁奸崗鏈佃厬閻ㄥ嫬鍙忕仦鈧崣姗€鍣?
import qqzone_downloader as qzd
from qqzone_downloader import (
    parse_cookies, extract_qq, calc_gtk,
    fetch_qzonetoken, safe_name,
    list_albums, list_photos, list_videos_in_album,
    get_video_url, download_file,
    PROXY
)

# 閳光偓閳光偓 闁板秶鐤?閳光偓閳光偓
VERSION = "2.2.5"

# PyInstaller 閹垫挸瀵橀崗鐓庮啇閿涙瓲rozen 閺冩儼绁┃鎰躬娑撳瓨妞傞惄顔肩秿閿涘瞼鏁ら幋閿嬫殶閹诡喖婀?exe 閹碘偓閸︺劎娲拌ぐ?
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
    "new_total": 0,  # 婢х偤鍣哄Ο鈥崇础娑撳娈戦弬鏉款杻閻撗呭閺?
}

VIDEO_DOWNLOAD_STATE = {
    "running": False, "current": "", "total": 0,
    "done": 0, "success": 0, "failed": 0,
    "finished": False, "albums": [],
}


def set_global_cookie(cookie_str: str):
    """鐠佸墽鐤?qqzone_downloader 濡€虫健閻ㄥ嫬鍙忕仦鈧?Cookie 閸欐﹢鍣?""
    # 濞撳懏绀傞敍姘涧娣囨繄鏆€ ASCII 閸欘垱澧﹂崡鏉跨摟缁楋讣绱機ookie 鐟欏嫯瀵栫憰浣圭湴閿?
    clean = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    qzd.G_COOKIE_STR = clean
    qzd.G_COOKIES = parse_cookies(clean)


# 閳光偓閳光偓 閻劍鍩涚拋鍓х枂 閳光偓閳光偓

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


# 閸旂姾娴囧韫箽鐎涙娈戞潏鎾冲毉閻╊喖缍?
_settings = load_settings()
if "output_dir" in _settings:
    app.config['OUTPUT_DIR'] = _settings["output_dir"]


# 閳光偓閳光偓 婢х偤鍣烘稉瀣祰濞撳懎宕?閳光偓閳光偓

MANIFEST_FILE = ".manifest.json"


def load_manifest(album_dir: str) -> dict:
    """閸旂姾娴囧韫瑓鏉炶姤绔婚崡鏇礉閼奉亜濮╁〒鍛倞瀹告彃鍨归梽銈嗘瀮娴犲墎娈戞潻鍥ㄦ埂閺夛紕娲?""
    path = os.path.join(album_dir, MANIFEST_FILE)
    manifest = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 濞撳懘娅庣壕浣烘磸娑撳﹤鍑℃稉宥呯摠閸︺劎娈戦弬鍥︽閻ㄥ嫯顔囪ぐ?
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
    """娣囨繂鐡ㄩ悡褏澧栧〒鍛礋"""
    path = os.path.join(album_dir, MANIFEST_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def get_photo_key(photo: dict) -> str:
    """閻?lloc + url 閸?60 鐎涙顑佹担婊€璐熼悡褏澧栭崬顖欑閺嶅洩鐦?""
    return (photo.get("lloc", "") or photo.get("url", "") or photo.get("id", ""))[:80]


def count_new_photos(album_dir: str, photos: list) -> int:
    """缂佺喕顓搁張澶婎樋鐏忔垹鍙庨悧鍥х毣閺堫亙绗呮潪?""
    manifest = load_manifest(album_dir)
    if not manifest:
        return len(photos)
    return sum(1 for p in photos if get_photo_key(p) not in manifest)


# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?
# 妞ょ敻娼扮捄顖滄暠
# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?

@app.route("/")
def index():
    return render_template("index.html")


# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?
# API 鐠侯垳鏁?
# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?

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
    # 濞撳懏绀傛稉宥呭讲鐟欎礁鐡х粭?
    cookie_str = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    if not cookie_str:
        return jsonify({"ok": False, "msg": "Cookie 娑撳秷鍏樻稉铏光敄"})

    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies)
    if not uin:
        return jsonify({"ok": False, "msg": "閺冪姵纭堕幓鎰絿 QQ 閸欏嚖绱濈拠閿嬵梾閺屻儲妲搁崥锕€鐣弫鏉戭槻閸?})

    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "缂傚搫鐨惂璇茬秿鐎靛棝鎸?(p_skey/skey)"})

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
        return jsonify({"ok": False, "msg": "鐠囧嘲鐣ㄧ憗鍜冪窗pip install selenium webdriver-manager"})

    def _launch_browser():
        """鐏忔繆鐦?Chrome 閳?Edge 妞ゅ搫绨崥顖氬З濞村繗顫嶉崳顭掔礉鏉╂柨娲?(driver, name)"""
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
                # Edge 妫版繂顦婚敍姘鳖洣閻劑顩诲▎陇绻嶇悰灞芥倻鐎?
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
        raise RuntimeError(f"閺冪姵纭堕崥顖氬З濞村繗顫嶉崳顭掔礄Chrome / Edge 閸у洤銇戠拹銉礆: {last_error}")

    def login_thread():
        driver = None
        browser_name = ""
        try:
            driver, browser_name = _launch_browser()
            print(f"  棣冩灱 閹殿偆鐖滈惂璇茬秿娴ｈ法鏁? {browser_name}")

            # 閻╁瓨甯寸拋鍧楁６ i.qq.com閿涘矁顔€楠炲啿褰撮懛顏勭箒婢跺嫮鎮婇惂璇茬秿濞翠胶鈻?
            driver.get("https://i.qq.com/")

            # 缁涘绶熼惂璇茬秿鐎瑰本鍨氶敍姘閻胶鈥樼拋銈呮倵娴兼俺鍤滈崝銊ㄧ儲鏉烆剙鍩?user.qzone.qq.com/{uin}
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
                app.config["QR_RESULT"] = {"ok": False, "msg": "Cookie 娑撳秴鍙忛敍宀冾嚞鐏忔繆鐦弬鐟扮础 2"}
        except Exception as e:
            app.config["QR_RESULT"] = {"ok": False, "msg": f"閹殿偆鐖滄径杈Е: {str(e)[:80]}"}
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
    """闁偓閸戣櫣娅ヨぐ鏇礉閸掔娀娅?Cookie 閸滃瞼绱︾€?""
    # 閸掔娀娅庨崜宥嗗絹閸?uin 閻劋绨〒鍛处鐎?
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
        return jsonify({"ok": False, "msg": "閺堫亞娅ヨぐ?})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 瀹歌尪绻冮張?})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    try:
        albums = list_albums(uin, uin, g_tk, qzt)
    except Exception as e:
        return jsonify({"ok": False, "msg": f"閼惧嘲褰囬惄绋垮斀閺冭泛鍤柨娆欑礉鐠囬攱顥呴弻銉х秹缂佹粍鍨ㄩ柌宥嗘煀閻ц缍?, "detail": str(e)[:120]})

    if not albums:
        return jsonify({"ok": False, "msg": "鐠囥儴澶勯崣铚傜瑓濞屸剝婀侀惄绋垮斀閿涘苯褰查懗鑺ユ弓瀵偓闁?QQ 缁屾椽妫块幋鏍祲閸愬奔璐熺粚?})

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
        return jsonify({"ok": False, "msg": "鐠囧嘲鍘涢崚閿嬫煀閻╃鍞介崚妤勩€?})

    # selected 娣囨繃瀵旀稉?(origin_idx, album) 閻ㄥ嫬鍨悰?
    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("UIN", "")
    g_tk = app.config.get("G_TK", 0)
    qzt = app.config.get("QZT", "")

    # 绾喕绻?Cookie 瀹歌尪顔曠純?
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            set_global_cookie(f.read().strip())

    # 閺屻儲澹樺鍙夋箒閻╃鍞介惄顔肩秿閻ㄥ嫬鍤遍弫?
    def find_album_dir(base: str, album_name: str) -> str:
        """濡偓閺屻儲妲搁崥锕€鍑￠張澶婃倱閸氬秶娴夐崘宀€娲拌ぐ鏇礉閺堝鍨径宥囨暏"""
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
            # 娴兼ê鍘涙径宥囨暏瀹稿弶婀侀惄顔肩秿
            existing_dir = find_album_dir(os.path.join(app.config['OUTPUT_DIR'], uin), alb["name"])
            if existing_dir:
                adir = existing_dir
            else:
                adir = os.path.join(app.config['OUTPUT_DIR'], uin, f"{origin_idx:02d}_{aname}")
            DOWNLOAD_STATE["current"] = f"閼惧嘲褰? {alb['name']}..."
            os.makedirs(adir, exist_ok=True)

            # 娴?API 閼惧嘲褰囬悡褏澧栭崚妤勩€?
            photos = list_photos(uin, uin, alb["id"], g_tk, qzt)
            if not photos:
                print(f"  閳?{alb['name']}: list_photos 鏉╂柨娲栫粚?)
                DOWNLOAD_STATE["failed"] += 1
                continue

            # 鏉╁洦鎶ょ憴鍡涱暥
            if not download_video:
                photos = [p for p in photos if not p.get("is_video")]

            if not photos:
                continue

                        # 閸旂姾娴囧韫瑓鏉炶姤绔婚崡鏇礉閸撴棃娅庡鎻掔摠閸︺劎娈?
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

            print(f"  {alb['name']}: 閸?{len(photos)} 瀵媴绱濆〒鍛礋瀹稿弶婀?{len(manifest)} 瀵媴绱?
                  f"閺傛澘顤冮悡褏澧?{len(new_photos)} 瀵? +
                  (f"閿涘矁顫嬫０鎴濈殱闂?{len(new_videos)} 瀵? if new_videos else ""))
            existing_total = len(manifest)

            if not new_photos and not (download_video and new_videos):
                DOWNLOAD_STATE["current"] = f"閳?{alb['name']}: 閺冪姵鏌婃晶?
                time.sleep(0.1)
                continue

            tasks = []
            for items, sub_dir, prefix in [
                (new_photos, "閸ュ墽澧?, "photo"),
                (new_videos if download_video else [], "鐟欏棝顣剁亸渚€娼?, "video"),
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

            # 楠炶泛褰傛稉瀣祰
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
        DOWNLOAD_STATE["current"] = "鐎瑰本鍨氶敍?
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


# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?
# 鐟欏棝顣剁€电厧鍤?API
# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?

@app.route("/api/video/albums")
def api_video_albums():
    """鏉╂柨娲栭崥顐ｆ箒鐟欏棝顣堕惃鍕祲閸愬苯鍨悰?""
    cookie_str = ""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    if not cookie_str:
        return jsonify({"ok": False, "msg": "閺堫亞娅ヨぐ?})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 瀹歌尪绻冮張?})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    albums = list_albums(uin, uin, g_tk, qzt)
    if not albums:
        return jsonify({"ok": False, "msg": "閺堫亣骞忛崣鏍у煂閻╃鍞?})

    # 楠炴儼顢戦幍顐ｅ伎閸氼偉顫嬫０鎴犳畱閻╃鍞介敍? 缁捐法鈻奸敍灞剧槨娑擃亞娴夐崘灞藉涧閹殿偂绔村▎鈽呯礆
    from concurrent.futures import ThreadPoolExecutor, as_completed
    print(f"\n棣冨箑 閹殿偅寮跨憴鍡涱暥閻╃鍞?..閿涘牆鍙?{len(albums)} 娑擃亞娴夐崘宀嬬礉楠炴儼顢戦敍?)

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
                print(f"  [{len(results_by_idx):2d}] {a['name']} 閳?{count} 娑擃亣顫嬫０?)

    result = [{"id": a["id"], "name": a["name"], "count": count, "origin_idx": idx, "cover": a.get("cover", "")}
              for idx, (a, count) in sorted(results_by_idx.items())]
    print(f"  閴?閸?{len(result)} 娑擃亞娴夐崘灞芥儓閺堝顫嬫０鎱璶")

    if not result:
        return jsonify({"ok": False, "msg": "鐠囥儴澶勯崣铚傜瑓濞屸剝婀侀崥顐ヮ潒妫版垹娈戦惄绋垮斀"})

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
        return jsonify({"ok": False, "msg": "鐠囧嘲鍘涢崚閿嬫煀鐟欏棝顣堕崚妤勩€?})

    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("VIDEO_UIN", "")
    g_tk = app.config.get("VIDEO_G_TK", 0)
    qzt = app.config.get("VIDEO_QZT", "")

    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    else:
        cookie_str = ""

    # 娴犲海绱︾€涙ɑ鍨?API 閼惧嘲褰囩憴鍡涱暥閸掓銆?
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
        return jsonify({"ok": False, "msg": "閹碘偓闁娴夐崘灞艰厬濞屸剝婀佺憴鍡涱暥"})

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

        # 缁楊兛绔村銉窗娴犲海绱︾€?/ API 閼惧嘲褰囩憴鍡涱暥娑撳娴囬柧鐐复
        VIDEO_DOWNLOAD_STATE["current"] = "濮濓絽婀懢宄板絿鐟欏棝顣舵稉瀣祰闁剧偓甯?.."
        print(f"\n棣冨箑 閼惧嘲褰?{len(all_videos)} 娑擃亣顫嬫０鎴犳畱娑撳娴囬柧鐐复...")
        urls = []
        for i, v in enumerate(all_videos, 1):
            pic_key = v.get("lloc", "")
            if not pic_key:
                continue
            cache_key = (v["album_id"], pic_key)
            video_url = get_video_url(uin, uin, v["album_id"], pic_key, g_tk)
            if video_url:
                desc = v.get("name", "") or pic_key[:12]
                print(f"  閴?[{i}/{len(all_videos)}] {desc}")
                urls.append({
                    "album": v.get("album_name", ""),
                    "name": v.get("name", desc),
                    "url": video_url,
                    "origin_idx": v.get("origin_idx", 0),
                })
            VIDEO_DOWNLOAD_STATE["done"] = i
            time.sleep(0.05)

        if not urls:
            VIDEO_DOWNLOAD_STATE["current"] = "閺堫亣骞忛崣鏍у煂娴犺缍嶇憴鍡涱暥闁剧偓甯?
            VIDEO_DOWNLOAD_STATE["finished"] = True
            VIDEO_DOWNLOAD_STATE["running"] = False
            return

        # 缁楊兛绨╁銉窗婢х偤鍣洪獮璺哄絺娑撳娴?
        VIDEO_DOWNLOAD_STATE["done"] = 0
        VIDEO_DOWNLOAD_STATE["current"] = "濮濓絽婀稉瀣祰..."
        new_count = 0  # 鐎圭偤妾弬鏉款杻娑撳娴囬弫?
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
            adir = os.path.join(output_base, f"{oidx:02d}_{aname}", "鐟欏棝顣?)
            os.makedirs(adir, exist_ok=True)
            fp = os.path.join(adir, f"{idx:03d}_{vname}{ext}")

            # 婢х偤鍣洪敍姘梾閺屻儲妲搁崥锕€鍑℃稉瀣祰
            manifest = load_manifest(os.path.dirname(adir))
            if item["url"] in manifest:
                continue  # 鐠哄疇绻冮敍灞肩瑝鐠佲€冲弳 total
            new_count += 1
            tasks.append((item["url"], fp, adir, f"[{idx}/{len(urls)}] {item['name']}"))

        if not tasks:
            VIDEO_DOWNLOAD_STATE["total"] = VIDEO_DOWNLOAD_STATE["done"]
            VIDEO_DOWNLOAD_STATE["current"] = "閸忋劑鍎村韫瑓鏉炴枻绱濋弮鐘绘付闁插秴顦?
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
                    # 閸愭瑥鍙嗘晶鐐哄櫤濞撳懎宕熼敍鍫滅瑢閻撗呭閸忚京鏁ら崥灞肩缁狙呮窗瑜版洜娈?manifest閿?
                    parent_dir = os.path.dirname(adir)
                    manifest = load_manifest(parent_dir)
                    manifest[url] = os.path.join("鐟欏棝顣?, os.path.basename(fp))
                    save_manifest(parent_dir, manifest)
                else:
                    VIDEO_DOWNLOAD_STATE["failed"] += 1
                VIDEO_DOWNLOAD_STATE["done"] += 1
                time.sleep(0.05)

        VIDEO_DOWNLOAD_STATE["current"] = "鐎瑰本鍨氶敍?
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
    """娴狅絿鎮?QZone 閸ュ墽澧栭敍宀€绮潻鍥Щ閻╂鎽?""
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
    """閸忔娊妫撮張宥呭"""
    DOWNLOAD_STATE["running"] = False
    VIDEO_DOWNLOAD_STATE["running"] = False
    threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/version")
def api_version():
    return jsonify({"version": VERSION})


@app.route("/api/check_update")
def api_check_update():
    """濡偓閺屻儲娲块弬甯窗閸忓牊鐓?VERSION 閺傚洣娆㈤敍鍫濇彥閿涘绱濋崘宥嗙叀 GitHub API閿涘牊婀佺拠锔藉剰閿?""
    current = VERSION.lstrip("v")
    latest = ""
    url = ""
    body = ""

    def parse_ver(v):
        parts = v.split(".")
        return tuple(int(p) for p in parts if p.isdigit())

    # 缁楊兛绔村銉窗娴?GitHub 閸樼喎顫愰弬鍥︽閼惧嘲褰囬張鈧弬鎵閺堫剙褰块敍鍫濇禇閸愬懍绡冮懗鍊燁問闂傤噯绱?
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/RivoMonar/QQAlbumExporter/master/VERSION",
            timeout=8
        )
        if r.status_code == 200:
            latest = r.text.strip().lstrip("v")
    except Exception:
        pass

    # 缁楊兛绨╁銉窗鐞涖儱鍘?Release 鐠囷附鍎?
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
        # VERSION 閺傚洣娆㈤懢宄板絿婢惰精瑙﹂敍灞芥礀闁偓閸?GitHub API
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
        return jsonify({"ok": False, "msg": "閺冪姵纭堕懢宄板絿閺囧瓨鏌婃穱鈩冧紖閿涘矁顕Λ鈧弻銉х秹缂?, "current": VERSION, "has_update": False})

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
    """閹垫挸绱戠化鑽ょ埠閸樼喓鏁撻惄顔肩秿闁瀚ㄧ€电鐦藉?""
    folder = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="闁瀚ㄦ潏鎾冲毉閻╊喖缍?)
        root.destroy()
    except:
        pass

    if folder:
        app.config['OUTPUT_DIR'] = folder
        os.makedirs(folder, exist_ok=True)
        save_settings({"output_dir": folder})
        return jsonify({"ok": True, "output_dir": folder})
    return jsonify({"ok": False, "msg": ""})  # 閸欐牗绉烽柅澶嬪 = 娑撳秵濮ら柨?


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify({"ok": True, "output_dir": app.config['OUTPUT_DIR']})
    # POST: 閹靛濮╃拋鍓х枂鐠侯垰绶為敍鍫滅瘍閹恒儱褰?pick_directory 閻ㄥ嫭娲块弬甯礆
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
    return jsonify({"ok": False, "msg": "鐠侯垰绶炴稉宥堝厴娑撹櫣鈹?})
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
    return jsonify({"ok": False, "msg": "閻╊喖缍嶆稉宥呯摠閸?})


# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?
# 閸氼垰濮?
# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡?

if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    port = 5800

    # 濞夈劌鍞?Ctrl+C 娴兼﹢娉ら柅鈧崙?
    def _on_exit(sig, frame):
        print("\n閳?濮濓絽婀崑婊勵剾...")
        DOWNLOAD_STATE["running"] = False
        VIDEO_DOWNLOAD_STATE["running"] = False
        os._exit(0)
    signal.signal(signal.SIGINT, _on_exit)
    signal.signal(signal.SIGTERM, _on_exit)

    print(f"""
閳烘柡鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫧
閳?    QQ 缁屾椽妫块惄绋垮斀鐎电厧鍤崳?璺?GUI 閻?          閳?
閳?                                         閳?
閳? http://localhost:{port}                  閳?
閳?                                         閳?
閳? 濞村繗顫嶉崳銊ュ嚒閼奉亜濮╅幍鎾崇磻                        閳?
閳烘埃鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ殕
""")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
