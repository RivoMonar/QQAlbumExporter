# QQ 空间相册导出器

一键导出 QQ 空间所有相册的原图照片，支持增量下载、多线程并发，提供 Web GUI 操作界面。

## 🚀 新手使用（无需安装 Python）

1. 下载 **`QQ空间相册导出器.exe`**
2. 双击运行，浏览器自动打开 `localhost:5800`
3. 扫码登录或粘贴 Cookie，选择相册开始导出

> 系统要求：Windows 10+
> - **照片导出**：任意浏览器
> - **扫码登录**：Chrome 80+ 或 Edge 80+（自动降级）
> - **视频导出**：Chrome 90+ 或 Edge 90+（需 Chromium 内核，Selenium 捕获视频链接）

## 🔧 开发者使用

```bash
pip install flask requests selenium webdriver-manager
python app.py
# → http://localhost:5800
```

## 📦 打包为 EXE

项目已配置 GitHub Actions，推送代码即自动构建。也可手动打包：

```bash
pip install pyinstaller
pyinstaller --onefile --console --name "QQ空间相册导出器" --add-data "templates;templates" --add-data "static;static" --add-data "qqzone_downloader.py;." --hidden-import flask --hidden-import requests --hidden-import urllib3 --hidden-import selenium --hidden-import webdriver_manager --clean -y app.py
# 输出：dist/QQ空间相册导出器.exe
```

## 登录方式

| 方式 | 说明 |
|------|------|
| 📱 扫码登录 | 点击后自动打开 Chrome，用手机 QQ 扫描二维码 |
| ⌨️ Cookie 登录 | 从浏览器 F12 → 网络 → 复制 Cookie 粘贴 |

## 主要功能

- **全量导出** — 支持所有相册，数十万张照片稳定导出
- **增量下载** — 记录已下载清单，只补充新增照片
- **多线程** — 可配置 1-20 线程并发下载
- **断点续传** — 已下载文件自动跳过
- **视频封面** — 可选保存视频封面到独立文件夹
- **视频导出** 🆕 — 一键导出相册中的视频原文件（Selenium 捕获真实下载链接）
- **扫码登录** — Chrome/Edge 自动降级，CDP 提取 Cookie

## 目录结构

```
QQ空间相册导出器.exe    ← 打包后的单文件（推荐分发）
app.py                  ← Flask Web 服务
qqzone_downloader.py    ← 核心下载逻辑
templates/index.html    ← 前端页面
static/                 ← 静态资源（收款码图片）
```

## 💜 赞助

如果这个工具对你有帮助，欢迎请作者喝杯咖啡 ☕

<p align="center">
  <img src="static/alipay.png" width="200" alt="支付宝">
  &nbsp;&nbsp;&nbsp;
  <img src="static/wechat.png" width="200" alt="微信">
</p>
<p align="center">支付宝 · 微信</p>

## 常见问题

**Q: 扫码后浏览器没反应？**
A: 关闭浏览器窗口，刷新 `localhost:5800` 页面重试。确保 Chrome 浏览器已安装。

**Q: Cookie 登录提示过期？**
A: Cookie 里的 `p_skey` 有时效性，请重新从浏览器复制完整的 Cookie 字符串。

**Q: 下载速度慢？**
A: 在界面上调高并发数（建议 5-10），注意过高可能被限流。
