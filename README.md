# QQ 空间相册导出器

一键导出 QQ 空间所有相册的原图照片和视频，支持增量下载、多线程并发、智能缓存，提供 Web GUI 操作界面。

## 🚀 新手使用（无需安装 Python）

1. 下载 **`QQ空间相册导出器.exe`**
2. 双击运行，浏览器自动打开 `localhost:5800`
3. 扫码登录或粘贴 Cookie，选择相册开始导出

> 系统要求：Windows 10+
> - **照片导出**：任意浏览器
> - **扫码登录**：Chrome 80+ 或 Edge 80+（自动降级）
> - **视频导出**：无需浏览器，直接通过 QZone API 获取下载链接

## 🔧 开发者使用

```bash
pip install flask requests selenium webdriver-manager
python app.py
# → http://localhost:5800
```

## 📦 打包为 EXE

推送 tag 即自动构建 GitHub Release。也可手动打包：

```bash
pip install pyinstaller
pyinstaller --onefile --console --name "QQ空间相册导出器" --add-data "templates;templates" --add-data "static;static" --add-data "qqzone_downloader.py;." --hidden-import flask --hidden-import requests --hidden-import urllib3 --hidden-import selenium --hidden-import webdriver_manager --clean -y app.py
```

## 登录方式

| 方式 | 说明 |
|------|------|
| 📱 扫码登录 | 自动打开 Chrome/Edge，手机 QQ 扫码 |
| ⌨️ Cookie 登录 | 从浏览器 F12 → 网络 → 复制 Cookie 粘贴 |

## 主要功能

### 📷 照片导出
- **全量导出** — 支持所有相册，数十万张照片稳定导出
- **增量下载** — `.manifest.json` 记录已下载清单，重复运行只补充新增
- **多线程** — 可配置 1-20 线程并发下载
- **视频封面** — 可选保存视频封面到独立文件夹

### 🎬 视频导出
- **原视频下载** — 通过 floatview API 直接获取 `.mp4` 真实下载链接
- **增量下载** — 与照片共用 manifest，已下载视频自动跳过
- **独立目录** — 视频存入 `{序号}_{相册名}/视频/`，与照片/封面并列

### ⚡ 智能缓存
- **四层缓存** — 相册列表、视频列表、照片数据、视频链接全部缓存
- **持久化** — `qqzone_cache.json` 落盘，服务重启后切 Tab 秒开
- **按账号隔离** — 不同 QQ 号互不干扰，退出登录清对应账号缓存
- **刷新即重建** — 点击刷新按钮重新拉取全量数据

## 目录结构

```
QQ空间相册导出器.exe     ← 打包后的单文件
app.py                   ← Flask Web 服务
qqzone_downloader.py     ← 核心下载逻辑
templates/index.html     ← 前端页面（Alpine.js + Lucide）
static/                  ← 收款码图片
qqzone_cache.json        ← 缓存文件（自动生成）
qqzone_cookie.txt        ← 登录凭证（自动生成）
qqzone_settings.json     ← 用户设置（自动生成）
```

### 下载目录
```
qqzone_downloads/807876867/
├── 01_高三/
│   ├── .manifest.json
│   ├── 图片/
│   ├── 视频封面/
│   └── 视频/
├── 02_2019/
│   └── ...
```

## 💜 赞助

如果这个工具对你有帮助，欢迎请作者喝杯咖啡

<p align="center">
  <img src="static/alipay.png" width="200" alt="支付宝">
  &nbsp;&nbsp;&nbsp;
  <img src="static/wechat.png" width="200" alt="微信">
</p>
<p align="center">支付宝 · 微信</p>

## 常见问题

**Q: 扫码后浏览器没反应？**
A: 关闭浏览器窗口，刷新页面重试。确保 Chrome 或 Edge 已安装。

**Q: Cookie 登录提示过期？**
A: Cookie 里的 `p_skey` 有时效性，请重新复制完整的 Cookie 字符串。

**Q: 下载速度慢？**
A: 调高并发数（5-10），注意过高可能被限流。

**Q: 切账号后相册不对？**
A: 先退出登录（清缓存），再重新登录。缓存按 QQ 号隔离。

**Q: 视频导出数量为 0？**
A: 切换到"视频导出"Tab 查看。纯图片相册不会出现在视频列表中。
