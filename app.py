#!/usr/bin/env python3
"""
QQ 缂佸本妞藉Λ鍧楁儎缁嬪灝鏂€閻庣數鍘ч崵顓㈠闯?闁?GUI 闁绘鐗炵槐姗ask Web闁?

濞戞挴鍋撻梺娆惧枛閹酣宕濋…鎺旂婵炴潙绻楅～宥夊闯閵婏附鎯欏ù锝嗙玻缁辨繄浜歌箛鏇燁仱濞戞梻鍠曢崗妯荤▔婵犲啫顤侀柕?

闁告凹鍨版慨鈺呭棘閻熸壆纭€闁?
  python app.py
  婵炴潙绻楅～宥夊闯閵娿劌娈伴柛鏂诲妽婢э箑顕ｉ埀?http://localhost:5800
"""

import os, sys, json, time, re, threading, subprocess, webbrowser, logging, signal, requests
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from urllib.parse import unquote

# 濠㈣泛绉堕弫銈夊冀缁嬭法濡囬柛鏃傚枙閸?闁?闁?import module 闁哄倻鎳撶槐鈩冪閵夈倗鈹掑ǎ鍥跺枟閺佸ジ宕楅張浣冨幀闁汇劌瀚崣蹇曚沪閳ь剟宕ｅ鈧崳?
import qqzone_downloader as qzd
from qqzone_downloader import (
    parse_cookies, extract_qq, calc_gtk,
    fetch_qzonetoken, safe_name,
    list_albums, list_photos, list_videos_in_album,
    get_video_url, download_file,
    PROXY
)

# 闁冲厜鍋撻柍鍏夊亾 闂佹澘绉堕悿?闁冲厜鍋撻柍鍏夊亾
VERSION = "2.2.7"

# PyInstaller 闁瑰灚鎸哥€垫﹢宕楅悡搴晣闁挎稒鐡瞨ozen 闁哄啯鍎肩粊顐⑩攦閹邦剚韬☉鎾崇摠濡炲倿鎯勯鑲╃Э闁挎稑鐬奸弫銈夊箣闁垮娈堕柟璇″枛濠€?exe 闁圭鍋撻柛锔哄妿濞叉媽銇?
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
    "new_total": 0,  # 濠⒀呭仱閸ｅ搫螣閳ュ磭纭€濞戞挸顑囧▓鎴﹀棘閺夋鏉婚柣鎾楀懎顣婚柡?
}

VIDEO_DOWNLOAD_STATE = {
    "running": False, "current": "", "total": 0,
    "done": 0, "success": 0, "failed": 0,
    "finished": False, "albums": [],
}


def set_global_cookie(cookie_str: str):
    """閻犱礁澧介悿?qqzone_downloader 婵☆垪鈧櫕鍋ラ柣銊ュ閸欏繒浠﹂埀?Cookie 闁告瑦锕㈤崳?""
    # 婵炴挸鎳忕粈鍌炴晬濮橆剙娑уǎ鍥ㄧ箘閺嗏偓 ASCII 闁告瑯鍨辨晶锕傚础閺夎法鎽熺紒妤嬭缁辨ookie 閻熸瑥瀚€垫牜鎲版担鍦勾闁?
    clean = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    qzd.G_COOKIE_STR = clean
    qzd.G_COOKIES = parse_cookies(clean)


# 闁冲厜鍋撻柍鍏夊亾 闁活潿鍔嶉崺娑氭媼閸撗呮瀭 闁冲厜鍋撻柍鍏夊亾

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


# 闁告梻濮惧ù鍥ь啅闊厾绠介悗娑欘焽濞堟垶娼忛幘鍐叉瘔闁烩晩鍠栫紞?
_settings = load_settings()
if "output_dir" in _settings:
    app.config['OUTPUT_DIR'] = _settings["output_dir"]


# 闁冲厜鍋撻柍鍏夊亾 濠⒀呭仱閸ｇ儤绋夌€ｎ厽绁版繛鎾虫噹瀹?闁冲厜鍋撻柍鍏夊亾

MANIFEST_FILE = ".manifest.json"


def load_manifest(album_dir: str) -> dict:
    """闁告梻濮惧ù鍥ь啅闊厾鐟撻弶鐐跺Г缁斿宕￠弴顏嗙闁煎浜滄慨鈺併€掗崨顖涘€炵€瑰憡褰冮崹褰掓⒔閵堝棙鐎ù鐘插濞堟垶娼婚崶銊﹀焸闁哄绱曞ú?""
    path = os.path.join(album_dir, MANIFEST_FILE)
    manifest = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 婵炴挸鎳樺▍搴ｅ娴ｇ儤纾稿☉鎾筹工閸戔剝绋夊鍛憼闁革负鍔庡▓鎴﹀棘閸ワ附顐介柣銊ュ椤斿洩銇?
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
    """濞ｅ洦绻傞悺銊╂偂瑜忔晶鏍с€掗崨顓炵"""
    path = os.path.join(album_dir, MANIFEST_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def get_photo_key(photo: dict) -> str:
    """闁?lloc + url 闁?60 閻庢稒顨堥浣规媴濠娾偓鐠愮喖鎮¤婢ф牠宕娆戭伇闁哄秴娲╅惁?""
    return (photo.get("lloc", "") or photo.get("url", "") or photo.get("id", ""))[:80]


def count_new_photos(album_dir: str, photos: list) -> int:
    """缂備胶鍠曢鎼佸嫉婢跺妯嬮悘蹇斿灩閸欏酣鎮ч崶褏姣ｉ柡鍫簷缁楀懏娼?""
    manifest = load_manifest(album_dir)
    if not manifest:
        return len(photos)
    return sum(1 for p in photos if get_photo_key(p) not in manifest)


# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?
# 濡炪倗鏁诲鎵崉椤栨粍鏆?
# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?

@app.route("/")
def index():
    return render_template("index.html")


# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?
# API 閻犱警鍨抽弫?
# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?

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
    # 婵炴挸鎳忕粈鍌涚▔瀹ュ懎璁查悷娆庣閻⊙呯箔?
    cookie_str = "".join(c for c in cookie_str if 32 <= ord(c) < 127)
    if not cookie_str:
        return jsonify({"ok": False, "msg": "Cookie 濞戞挸绉烽崗妯荤▔閾忓厜鏁?})

    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies)
    if not uin:
        return jsonify({"ok": False, "msg": "闁哄啰濮电涵鍫曞箵閹邦剙绲?QQ 闁告瑥鍤栫槐婵堟嫚闁垮姊鹃柡灞诲劜濡叉悂宕ラ敃鈧悾顒勫极閺夋埈妲婚柛?})

    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "缂傚倸鎼惃顖炴儌鐠囪尙绉块悗闈涙閹?(p_skey/skey)"})

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
        return jsonify({"ok": False, "msg": "閻犲洤鍢查悾銊ф啑閸滃啰绐梡ip install selenium webdriver-manager"})

    def _launch_browser():
        """閻忓繑绻嗛惁?Chrome 闁?Edge 濡炪倕鎼花顓㈠触椤栨艾袟婵炴潙绻楅～宥夊闯椤帞绀夐弶鈺傛煥濞?(driver, name)"""
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
                # Edge 濡増绻傞ˇ濠氭晬濮橀硸娲ｉ柣顫姂椤╄鈻庨檱缁诲秶鎮扮仦鑺ュ€婚悗?
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
        raise RuntimeError(f"闁哄啰濮电涵鍫曞触椤栨艾袟婵炴潙绻楅～宥夊闯椤帞绀凜hrome / Edge 闁秆冩搐閵囨垹鎷归妷顖滅: {last_error}")

    def login_thread():
        driver = None
        browser_name = ""
        try:
            driver, browser_name = _launch_browser()
            print(f"  妫ｅ啯鐏?闁规鍋嗛悥婊堟儌鐠囪尙绉垮ù锝堟硶閺? {browser_name}")

            # 闁烩晛鐡ㄧ敮瀵告媼閸ф锛?i.qq.com闁挎稑鐭侀鈧鐐插暱瑜版挳鎳涢鍕畳濠㈣泛瀚幃濠囨儌鐠囪尙绉挎繛缈犺兌閳?
            driver.get("https://i.qq.com/")

            # 缂佹稑顦欢鐔兼儌鐠囪尙绉块悗鐟版湰閸ㄦ岸鏁嶅顓烆棁闁活喕鑳堕垾妯兼媼閵堝懏鍊靛ù鍏间亢閸ゆ粓宕濋妸銊у劜閺夌儐鍓欓崺?user.qzone.qq.com/{uin}
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
                app.config["QR_RESULT"] = {"ok": False, "msg": "Cookie 濞戞挸绉撮崣蹇涙晬瀹€鍐惧殲閻忓繑绻嗛惁顖炲棘閻熸壆纭€ 2"}
        except Exception as e:
            app.config["QR_RESULT"] = {"ok": False, "msg": f"闁规鍋嗛悥婊勫緞鏉堫偉袝: {str(e)[:80]}"}
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
    """闂侇偀鍋撻柛鎴ｆ濞呫儴銇愰弴顏嗙闁告帞濞€濞?Cookie 闁告粌鐬肩槐锔锯偓?""
    # 闁告帞濞€濞呭酣宕滃鍡楃倒闁?uin 闁活潿鍔嬬花顒€銆掗崨顖滃閻?
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
        return jsonify({"ok": False, "msg": "闁哄牜浜炲▍銉ㄣ亹?})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 鐎规瓕灏换鍐嫉?})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    try:
        albums = list_albums(uin, uin, g_tk, qzt)
    except Exception as e:
        return jsonify({"ok": False, "msg": f"闁兼儳鍢茶ぐ鍥儎缁嬪灝鏂€闁哄啳娉涢崵顓㈡煥濞嗘瑧绀夐悹鍥敱椤ュ懘寮婚妷褏绉圭紓浣圭矋閸ㄣ劑鏌屽鍡樼厐闁谎嗩嚙缂?, "detail": str(e)[:120]})

    if not albums:
        return jsonify({"ok": False, "msg": "閻犲洢鍎存径鍕矗閾氬倻鐟撴繛灞稿墲濠€渚€鎯勭粙鍨杸闁挎稑鑻ぐ鏌ユ嚄閼恒儲寮撶€殿喒鍋撻梺?QQ 缂佸本妞藉Λ鍧楀箣閺嶎偅绁查柛鎰鐠愮喓绮?})

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
        return jsonify({"ok": False, "msg": "閻犲洤鍢查崢娑㈠礆闁垮鐓€闁烩晝顭堥崬浠嬪礆濡ゅ嫨鈧?})

    # selected 濞ｅ洦绻冪€垫梹绋?(origin_idx, album) 闁汇劌瀚崹顏嗘偘?
    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("UIN", "")
    g_tk = app.config.get("G_TK", 0)
    qzt = app.config.get("QZT", "")

    # 缁绢収鍠曠换?Cookie 鐎规瓕灏鏇犵磾?
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            set_global_cookie(f.read().strip())

    # 闁哄被鍎叉竟妯侯啅閸欏绠掗柣鈺冾焾閸炰粙鎯勯鑲╃Э闁汇劌瀚崵閬嶅极?
    def find_album_dir(base: str, album_name: str) -> str:
        """婵☆偀鍋撻柡灞诲劜濡叉悂宕ラ敃鈧崙锟犲嫉婢跺﹥鍊遍柛姘Ф濞村宕樺畝鈧ú鎷屻亹閺囶亞绀夐柡鍫濐槸閸垱寰勫鍥ㄦ殢"""
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
            # 濞村吋锚閸樻稒寰勫鍥ㄦ殢鐎圭寮跺﹢渚€鎯勯鑲╃Э
            existing_dir = find_album_dir(os.path.join(app.config['OUTPUT_DIR'], uin), alb["name"])
            if existing_dir:
                adir = existing_dir
            else:
                adir = os.path.join(app.config['OUTPUT_DIR'], uin, f"{origin_idx:02d}_{aname}")
            DOWNLOAD_STATE["current"] = f"闁兼儳鍢茶ぐ? {alb['name']}..."
            os.makedirs(adir, exist_ok=True)

            # 濞?API 闁兼儳鍢茶ぐ鍥偂瑜忔晶鏍礆濡ゅ嫨鈧?
            photos = list_photos(uin, uin, alb["id"], g_tk, qzt)
            if not photos:
                print(f"  闁?{alb['name']}: list_photos 閺夆晜鏌ㄥú鏍矚?)
                DOWNLOAD_STATE["failed"] += 1
                continue

            # 閺夆晛娲﹂幎銈囨喆閸℃侗鏆?
            if not download_video:
                photos = [p for p in photos if not p.get("is_video")]

            if not photos:
                continue

                        # 闁告梻濮惧ù鍥ь啅闊厾鐟撻弶鐐跺Г缁斿宕￠弴顏嗙闁告挻妫冨▍搴☆啅閹绘帞鎽犻柛锔哄妿濞?
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

            print(f"  {alb['name']}: 闁?{len(photos)} 鐎殿喚濯寸槐婵嗐€掗崨顓炵鐎圭寮跺﹢?{len(manifest)} 鐎殿喚濯寸槐?
                  f"闁哄倹婢橀·鍐偂瑜忔晶?{len(new_photos)} 鐎? +
                  (f"闁挎稑鐭侀～瀣紣閹存繄娈遍梻?{len(new_videos)} 鐎? if new_videos else ""))
            existing_total = len(manifest)

            if not new_photos and not (download_video and new_videos):
                DOWNLOAD_STATE["current"] = f"闁?{alb['name']}: 闁哄啰濮甸弻濠冩櫠?
                time.sleep(0.1)
                continue

            tasks = []
            for items, sub_dir, prefix in [
                (new_photos, "闁搞儱澧芥晶?, "photo"),
                (new_videos if download_video else [], "閻熸瑥妫濋。鍓佷焊娓氣偓濞?, "video"),
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

            # 妤犵偠娉涜ぐ鍌涚▔鐎ｎ厽绁?
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
        DOWNLOAD_STATE["current"] = "閻庣懓鏈崹姘舵晬?
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


# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?
# 閻熸瑥妫濋。鍓佲偓鐢靛帶閸?API
# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?

@app.route("/api/video/albums")
def api_video_albums():
    """閺夆晜鏌ㄥú鏍触椤愶絾绠掗悷娆忔椤ｅ爼鎯冮崟顓熺ゲ闁告劕鑻崹顏嗘偘?""
    cookie_str = ""
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    if not cookie_str:
        return jsonify({"ok": False, "msg": "闁哄牜浜炲▍銉ㄣ亹?})

    set_global_cookie(cookie_str)
    cookies = parse_cookies(cookie_str)
    uin = extract_qq(cookies) or ""
    skey = cookies.get("p_skey") or cookies.get("media_p_skey") or cookies.get("skey") or ""
    if not skey:
        return jsonify({"ok": False, "msg": "Cookie 鐎规瓕灏换鍐嫉?})

    g_tk = calc_gtk(skey)
    qzt = fetch_qzonetoken(uin)

    albums = list_albums(uin, uin, g_tk, qzt)
    if not albums:
        return jsonify({"ok": False, "msg": "闁哄牜浜ｉ獮蹇涘矗閺嵮冪厒闁烩晝顭堥崬?})

    # 妤犵偞鍎奸、鎴﹀箥椤愶絽浼庨柛姘煎亯椤锛愰幋鐘崇暠闁烩晝顭堥崬浠嬫晬? 缂佹崘娉曢埢濂告晬鐏炲墽妲ㄥ☉鎿冧簽濞村宕樼仦钘夋锭闁规鍋傜粩鏉戔枎閳藉懐绀?
    from concurrent.futures import ThreadPoolExecutor, as_completed
    print(f"\n妫ｅ啫绠?闁规鍋呭璺ㄦ喆閸℃侗鏆ラ柣鈺冾焾閸?..闁挎稑鐗嗛崣?{len(albums)} 濞戞搩浜炲ù澶愬礃瀹€瀣妤犵偞鍎奸、鎴︽晬?)

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
                print(f"  [{len(results_by_idx):2d}] {a['name']} 闁?{count} 濞戞搩浜ｉ～瀣紣?)

    result = [{"id": a["id"], "name": a["name"], "count": count, "origin_idx": idx, "cover": a.get("cover", "")}
              for idx, (a, count) in sorted(results_by_idx.items())]
    print(f"  闁?闁?{len(result)} 濞戞搩浜炲ù澶愬礃鐏炶姤鍎撻柡鍫濐槼椤锛愰幈鐠?)

    if not result:
        return jsonify({"ok": False, "msg": "閻犲洢鍎存径鍕矗閾氬倻鐟撴繛灞稿墲濠€渚€宕ラ銉綊濡増鍨瑰▓鎴︽儎缁嬪灝鏂€"})

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
        return jsonify({"ok": False, "msg": "閻犲洤鍢查崢娑㈠礆闁垮鐓€閻熸瑥妫濋。鍫曞礆濡ゅ嫨鈧?})

    selected = [albums_with_idx[i] for i in indices if 0 <= i < len(albums_with_idx)] if indices else albums_with_idx
    uin = app.config.get("VIDEO_UIN", "")
    g_tk = app.config.get("VIDEO_G_TK", 0)
    qzt = app.config.get("VIDEO_QZT", "")

    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie_str = f.read().strip()
    else:
        cookie_str = ""

    # 濞寸姴娴风槐锔锯偓娑櫳戦崹?API 闁兼儳鍢茶ぐ鍥╂喆閸℃侗鏆ラ柛鎺擃殙閵?
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
        return jsonify({"ok": False, "msg": "闁圭鍋撻梺顐㈩槺濞村宕樼仦鑹板幀婵炲备鍓濆﹢浣烘喆閸℃侗鏆?})

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

        # 缂佹鍏涚粩鏉戭潰閵夘垳绐楀ù鐘叉捣缁憋妇鈧?/ API 闁兼儳鍢茶ぐ鍥╂喆閸℃侗鏆ュ☉鎾愁儓濞村洭鏌ч悙顒€澶?
        VIDEO_DOWNLOAD_STATE["current"] = "婵繐绲藉﹢顏堟嚔瀹勬澘绲块悷娆忔椤ｈ埖绋夌€ｎ厽绁伴梺鍓у亾鐢?.."
        print(f"\n妫ｅ啫绠?闁兼儳鍢茶ぐ?{len(all_videos)} 濞戞搩浜ｉ～瀣紣閹寸姵鐣卞☉鎾愁儓濞村洭鏌ч悙顒€澶?..")
        urls = []
        for i, v in enumerate(all_videos, 1):
            pic_key = v.get("lloc", "")
            if not pic_key:
                continue
            cache_key = (v["album_id"], pic_key)
            video_url = get_video_url(uin, uin, v["album_id"], pic_key, g_tk)
            if video_url:
                desc = v.get("name", "") or pic_key[:12]
                print(f"  闁?[{i}/{len(all_videos)}] {desc}")
                urls.append({
                    "album": v.get("album_name", ""),
                    "name": v.get("name", desc),
                    "url": video_url,
                    "origin_idx": v.get("origin_idx", 0),
                })
            VIDEO_DOWNLOAD_STATE["done"] = i
            time.sleep(0.05)

        if not urls:
            VIDEO_DOWNLOAD_STATE["current"] = "闁哄牜浜ｉ獮蹇涘矗閺嵮冪厒濞寸姾顔婄紞宥囨喆閸℃侗鏆ラ梺鍓у亾鐢?
            VIDEO_DOWNLOAD_STATE["finished"] = True
            VIDEO_DOWNLOAD_STATE["running"] = False
            return

        # 缂佹鍏涚花鈺侇潰閵夘垳绐楀褏鍋ら崳娲嵁鐠哄搫绲哄☉鎾愁儓濞?
        VIDEO_DOWNLOAD_STATE["done"] = 0
        VIDEO_DOWNLOAD_STATE["current"] = "婵繐绲藉﹢顏呯▔鐎ｎ厽绁?.."
        new_count = 0  # 閻庡湱鍋ゅ顖炲棘閺夋鏉诲☉鎾愁儓濞村洭寮?
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
            adir = os.path.join(output_base, f"{oidx:02d}_{aname}", "閻熸瑥妫濋。?)
            os.makedirs(adir, exist_ok=True)
            fp = os.path.join(adir, f"{idx:03d}_{vname}{ext}")

            # 濠⒀呭仱閸ｆ椽鏁嶅顓ф⒕闁哄被鍎插Σ鎼佸触閿曗偓閸戔剝绋夌€ｎ厽绁?
            manifest = load_manifest(os.path.dirname(adir))
            if item["url"] in manifest:
                continue  # 閻犲搫鐤囩换鍐晬鐏炶偐鐟濋悹浣测偓鍐插汲 total
            new_count += 1
            tasks.append((item["url"], fp, adir, f"[{idx}/{len(urls)}] {item['name']}"))

        if not tasks:
            VIDEO_DOWNLOAD_STATE["total"] = VIDEO_DOWNLOAD_STATE["done"]
            VIDEO_DOWNLOAD_STATE["current"] = "闁稿繈鍔戦崕鏉戭啅闊厾鐟撻弶鐐存灮缁辨繈寮悩缁樹粯闂佹彃绉撮ˇ?
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
                    # 闁告劖鐟ラ崣鍡樻櫠閻愬搫娅ゆ繛鎾虫噹瀹曠喖鏁嶉崼婊呯憿闁绘挆鍛暬闁稿繗浜弫銈夊触鐏炶偐顏辩紒鐙欏懏绐楃憸鐗堟礈濞?manifest闁?
                    parent_dir = os.path.dirname(adir)
                    manifest = load_manifest(parent_dir)
                    manifest[url] = os.path.join("閻熸瑥妫濋。?, os.path.basename(fp))
                    save_manifest(parent_dir, manifest)
                else:
                    VIDEO_DOWNLOAD_STATE["failed"] += 1
                VIDEO_DOWNLOAD_STATE["done"] += 1
                time.sleep(0.05)

        VIDEO_DOWNLOAD_STATE["current"] = "閻庣懓鏈崹姘舵晬?
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
    """濞寸媴绲块幃?QZone 闁搞儱澧芥晶鏍晬瀹€鈧划顐ｆ交閸ヮ剚些闁烩晜顨婇幗?""
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
    """闁稿繑濞婂Λ鎾嫉瀹ュ懎顫?""
    DOWNLOAD_STATE["running"] = False
    VIDEO_DOWNLOAD_STATE["running"] = False
    threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/version")
def api_version():
    return jsonify({"version": VERSION})


@app.route("/api/check_update")
def api_check_update():
    """婵☆偀鍋撻柡灞诲劜濞插潡寮敮顔剧獥闁稿繐鐗婇悡?VERSION 闁哄倸娲ｅ▎銏ゆ晬閸繃褰ラ柨娑橆檧缁辨繈宕樺鍡欏弨 GitHub API闁挎稑鐗婂﹢浣烘嫚閿旇棄鍓伴柨?""
    current = VERSION.lstrip("v")
    latest = ""
    url = ""
    body = ""

    def parse_ver(v):
        parts = v.split(".")
        return tuple(int(p) for p in parts if p.isdigit())

    # 缂佹鍏涚粩鏉戭潰閵夘垳绐楀ù?GitHub 闁告鍠庨～鎰板棘閸ワ附顐介柤鎯у槻瑜板洭寮甸埀顒勫棘閹殿喖顣奸柡鍫墮瑜板潡鏁嶉崼婵囩闁告劕鎳嶇弧鍐嚄閸婄噥鍟忛梻鍌ゅ櫙缁?
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/RivoMonar/QQAlbumExporter/master/VERSION",
            timeout=8
        )
        if r.status_code == 200:
            latest = r.text.strip().lstrip("v")
    except Exception:
        pass

    # 缂佹鍏涚花鈺侇潰閵夘垳绐楅悶娑栧劚閸?Release 閻犲浄闄勯崕?
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
        # VERSION 闁哄倸娲ｅ▎銏ゆ嚔瀹勬澘绲垮鎯扮簿鐟欙箓鏁嶇仦鑺ョ闂侇偀鍋撻柛?GitHub API
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
        return jsonify({"ok": False, "msg": "闁哄啰濮电涵鍫曟嚔瀹勬澘绲块柡鍥х摠閺屽﹥绌遍埄鍐х礀闁挎稑鐭侀顒€螞閳ь剟寮婚妷褏绉圭紓?, "current": VERSION, "has_update": False})

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
    """闁瑰灚鎸哥槐鎴犲寲閼姐倗鍩犻柛妯煎枔閺佹捇鎯勯鑲╃Э闂侇偄顦扮€氥劎鈧數顢婇惁钘夘浖?""
    folder = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="闂侇偄顦扮€氥劍娼忛幘鍐叉瘔闁烩晩鍠栫紞?)
        root.destroy()
    except:
        pass

    if folder:
        app.config['OUTPUT_DIR'] = folder
        os.makedirs(folder, exist_ok=True)
        save_settings({"output_dir": folder})
        return jsonify({"ok": True, "output_dir": folder})
    return jsonify({"ok": False, "msg": ""})  # 闁告瑦鐗楃粔鐑芥焻婢跺顏?= 濞戞挸绉垫慨銈夋煥?


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify({"ok": True, "output_dir": app.config['OUTPUT_DIR']})
    # POST: 闁归潧顑呮慨鈺冩媼閸撗呮瀭閻犱警鍨扮欢鐐烘晬閸粎鐦嶉柟鎭掑劚瑜?pick_directory 闁汇劌瀚ú鍧楀棘鐢喚绀?
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
    return jsonify({"ok": False, "msg": "閻犱警鍨扮欢鐐寸▔瀹ュ牆鍘村☉鎾规閳?})
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
    return jsonify({"ok": False, "msg": "闁烩晩鍠栫紞宥嗙▔瀹ュ懐鎽犻柛?})


# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?
# 闁告凹鍨版慨?
# 闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩?

if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    port = 5800

    # 婵炲鍔岄崬?Ctrl+C 濞村吋锕㈠▔銈夋焻閳ь剟宕?
    def _on_exit(sig, frame):
        print("\n闁?婵繐绲藉﹢顏堝磻濠婂嫷鍓?..")
        DOWNLOAD_STATE["running"] = False
        VIDEO_DOWNLOAD_STATE["running"] = False
        os._exit(0)
    signal.signal(signal.SIGINT, _on_exit)
    signal.signal(signal.SIGTERM, _on_exit)

    print(f"""
闁崇儤鏌￠弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅?
闁?    QQ 缂佸本妞藉Λ鍧楁儎缁嬪灝鏂€閻庣數鍘ч崵顓㈠闯?鐠?GUI 闁?          闁?
闁?                                         闁?
闁? http://localhost:{port}                  闁?
闁?                                         闁?
闁? 婵炴潙绻楅～宥夊闯閵娿儱鍤掗柤濂変簻婵晠骞嶉幘宕囩；                        闁?
闁崇儤鍩冮弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娅滈柍鐑樺姀閺呮煡鍩￠幇銊︽珳闁崇儤鍔忛弲鏌ュ煛閹般劍娈?
""")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
