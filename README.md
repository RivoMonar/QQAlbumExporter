# QQ 空间相册导出器

一键导出 QQ 空间所有相册的原图照片，支持增量下载、多线程并发，提供 Web GUI 操作界面。

## 新手使用（最简单）

1. 双击 **`启动.bat`**
2. 首次运行会自动安装依赖（需要 1-2 分钟）
3. 浏览器自动打开 `localhost:5800`
4. 扫码登录或粘贴 Cookie，选择相册开始导出

> 系统要求：Windows 10+，Chrome 浏览器，Python 3.8+

## 手动启动

```bash
pip install flask requests selenium webdriver-manager
python app.py
# 浏览器打开 http://localhost:5800
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
- **扫码登录** — 自动提取 Cookie，安全可靠

## 目录结构

```
启动.bat                ← 一键启动（推荐）
app.py                  ← Flask Web 服务
qqzone_downloader.py    ← 核心下载逻辑
templates/index.html    ← 前端页面
static/                 ← 静态资源（收款码图片）
qqzone_cookie.txt       ← 登录凭证（自动生成）
qqzone_settings.json    ← 用户设置（自动生成）
```

## 常见问题

**Q: 扫码后浏览器没反应？**
A: 关闭浏览器窗口，刷新 `localhost:5800` 页面重试。确保 Chrome 浏览器已安装。

**Q: Cookie 登录提示过期？**
A: Cookie 里的 `p_skey` 有时效性，请重新从浏览器复制完整的 Cookie 字符串。

**Q: 下载速度慢？**
A: 在界面上调高并发数（建议 5-10），注意过高可能被限流。
