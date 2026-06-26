# QQ 空间相册导出器

一键批量导出 QQ 空间所有相册的原图照片和视频，支持增量下载、多线程并发，提供 Web GUI 操作界面。

## 🚀 新手使用

1. 下载最新版 **`QQAlbumExporter.exe`**（[GitHub Releases](https://github.com/RivoMonar/QQAlbumExporter/releases)）
2. 双击运行，浏览器自动打开 `localhost:5800`
3. 扫码登录或粘贴 Cookie，选择相册开始导出

> 系统要求：Windows 10+，Chrome 或 Edge 浏览器（扫码需要）

## 🔒 隐私与安全

**全程仅与 QQ 官方服务器通信**，网络请求链路如下：

```
本机 ↔ api.github.com     （仅「检查更新」功能，可跳过）
本机 ↔ xui.ptlogin2.qq.com （扫码登录）
本机 ↔ user.qzone.qq.com   （相册数据、照片下载）
本机 ↔ photo.store.qq.com  （原图 / 视频文件下载）
```

- ❌ **不上传** Cookie 到任何第三方服务器
- ❌ **不收集** 任何个人信息
- ✅ 全部代码开源，可自行审查：`app.py` / `qqzone_downloader.py`

## 登录方式

两种方式本质相同，都是使用 QQ 空间的登录 Cookie：

### 方式一：自动登录（推荐）

点击页面上的 **「📱 扫码登录」**，程序会自动打开 Chrome 或 Edge 浏览器，跳转到 QQ 登录页：

- 手机 QQ 扫描二维码
- 或在浏览器中手动输入账号密码
- 或点击「快速登录」（如果 QQ 已在线）

无论哪种操作，登录成功后程序会自动提取 Cookie，浏览器随即关闭。

### 方式二：手动粘贴 Cookie（无需浏览器）

如果不放心自动登录，可以手动从浏览器复制 Cookie：

1. 用你自己的浏览器（Chrome / Edge）打开 <https://user.qzone.qq.com/>
2. 手动登录 QQ 空间
3. 按 **F12** 打开开发者工具
4. 点击顶部 **Network（网络）** 标签
5. 在筛选框输入 `qzone.qq.com`
6. 点击下方任意一条请求（如 `fcg_list_album_v3`）
7. 在右侧找到 **Request Headers（请求头）**
8. 找到 **Cookie:** 这一行，**完整复制**冒号后面的全部内容
9. 粘贴到程序中的文本框，点击「确认登录」

> 提示：Cookie 字符串通常以 `uin=` 或 `p_uin=` 开头，长度一般在 500-2000 字符之间。需要包含 `p_skey` 或 `skey` 才能正常工作。

## 主要功能

### 📷 照片导出
- 全量导出所有相册，支持数十万张照片
- 增量下载：`.manifest.json` 记录已下载清单，重复运行只补充新增
- 多线程并发（1-20 线程可调）
- 视频封面可选保存到独立文件夹

### 🎬 视频导出
- 通过 QZone API 直接获取 `.mp4` 真实下载链接
- 与照片共用增量清单，已下载自动跳过
- 视频存入 `{序号}_{相册名}/视频/` 目录

### 🎨 界面特性
- 照片 / 视频 Tab 一键切换
- 相册封面缩略图预览
- 5 线程并行扫描视频相册
- 进度条跨 Tab 保持，下载中禁止刷新
- Ctrl+C 安全中断服务
- 检查更新（连接 GitHub 比对版本号）

## 🔧 开发者使用

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:5800
```

## 📦 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3 + Flask |
| 前端 | Alpine.js + Lucide Icons |
| 扫码登录 | Selenium + Chrome/Edge DevTools Protocol |
| 相册 API | QZone `fcg_list_album_v3` / `fcg_list_photo_v2` / `cgi_floatview_photo_list_v2` |
| 打包 | PyInstaller + GitHub Actions 自动构建 |

## 📁 目录结构

```
QQAlbumExporter.exe      ← 打包后的单文件
app.py                       ← Flask Web 服务
qqzone_downloader.py         ← 核心下载逻辑
templates/index.html         ← 前端页面
static/                      ← 收款码图片
requirements.txt             ← Python 依赖
VERSION                      ← 版本号（用于检查更新）
```

### 下载目录
```
qqzone_downloads/{QQ号}/
├── 01_相册名/
│   ├── .manifest.json
│   ├── 图片/
│   ├── 视频封面/
│   └── 视频/
├── 02_相册名/
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
A: Cookie 里的 `p_skey` 有时效性，请重新从浏览器复制完整的 Cookie 字符串。

**Q: 下载速度慢？**
A: 调高并发数（5-10），注意过高可能被限流。

**Q: 挂机下载到一半提示失败？**
A: QQ 空间登录 Cookie 有效期约 2-4 小时，长时间挂机会自然过期。建议分批导出或期间保持浏览器活跃。

**Q: 切账号后相册不对？**
A: 先退出登录，再重新登录新账号。

**Q: 视频导出数量为 0？**
A: 切换到「视频导出」Tab 查看。纯图片相册不会出现在视频列表中。

**Q: 检查更新提示网络错误？**
A: GitHub 在国内访问可能较慢，请使用代理或稍后重试。不影响正常导出功能。
