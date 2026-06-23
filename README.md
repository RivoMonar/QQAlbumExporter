# QQ 空间相册导出器

一键导出 QQ 空间所有相册的原图照片，支持增量下载、多线程并发、Web GUI 操作。

---

## 功能

| 功能 | 说明 |
|------|------|
| 📸 **原图下载** | 通过 `fcg_list_photo_v2` API 获取照片原图 URL，非缩略图 |
| 🔄 **增量导出** | 记录已下载照片的清单（`.manifest.json`），下次只导出新增的 |
| 🚀 **多线程并发** | 默认 5 线程同时下载，可配置 1–20 |
| 📱 **扫码登录** | 自动打开浏览器，手机 QQ 扫二维码即登录 |
| 🍪 **Cookie 保存** | 登录后自动保存，下次启动免登录 |
| 📂 **目录选择** | 系统原生目录选择框，可自由更改输出位置 |
| 🎬 **视频封面** | 可选的视频封面保存（单独文件夹） |
| 🖥️ **Web GUI** | Flask Web 界面，浏览器操作，小白友好 |

## 使用方法

### 环境要求

- Python 3.8+
- 依赖：`pip install flask requests`
- 扫码登录需要：`pip install selenium webdriver-manager`

### 启动

```bash
cd script/qqzone
python app.py
```

浏览器自动打开 `http://localhost:5800`

### 操作流程

```
① 扫码登录（或粘贴 Cookie）
② 勾选要导出的相册
③ 点击「开始导出」
④ 等待完成
```

### 二次导出

再次运行会自动检测已有文件，只下载新增照片，已存在的跳过。

---

## 技术原理

### 相册列表

通过 QZone 的 `fcg_list_album_v3` 接口获取，需添加 `inCharset/outCharset=utf-8` 参数避免编码错误。

```python
GET https://h5.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/fcg_list_album_v3
Params: uin, hostUin, pageStart, len, format=json, g_tk, inCharset=utf-8, outCharset=utf-8
```

### 照片列表

通过 `fcg_list_photo_v2` 接口获取，**关键参数名必须为全小写 `albumid`**（非 `topicId` 或 `albumId`）。

```python
GET https://h5.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/fcg_list_photo_v2
Params: uin, hostUin, albumid, pageNum, pageSize, format=json, g_tk
```

照片数据位于 `data.pic[]`（非 `data.photoList[]`），原图 URL 取自 `origin_url` 字段。

### 签名算法 (g_tk)

```python
def calc_gtk(skey):
    h = 5381
    for ch in skey:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF
```

`skey` 取自 Cookie 中的 `p_skey`（优先）→ `media_p_skey` → `skey`。

### 扫码登录

使用 Selenium 打开 Chrome 浏览器 → QQ 登录页 → 用户扫码 → 通过 CDP (`Network.getAllCookies`) 捕获全部 Cookie（含 HttpOnly）。

### 增量下载

每个相册目录下生成 `.manifest.json`，以照片 URL 为 key 记录已下载的文件。再次运行时对比 API 返回列表，只下载新增项。

### 多线程

使用 `concurrent.futures.ThreadPoolExecutor` 并发下载，每个相册内的照片同时下载。

---

## 文件结构

```
qqzone/
├── app.py                          # Flask Web GUI
├── qqzone_downloader.py            # 核心下载逻辑（命令行）
├── qqzone_video_downloader.py      # 视频下载（Selenium 版）
├── templates/
│   └── index.html                  # Web 前端
├── qqzone_downloads/               # 默认下载目录
├── qqzone_cookie.txt               # 保存的 Cookie
├── qqzone_settings.json            # 用户设置（输出目录等）
├── README.md
└── LICENSE
```

## 开源许可

本项目基于 **MIT License** 开源，**仅限个人学习使用，禁止商用**。

Copyright (c) 2026
