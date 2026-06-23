#!/usr/bin/env python3
"""
PyInstaller 打包脚本
运行：python build_exe.py
输出：dist/QQ空间相册导出器.exe
"""

import subprocess, sys, os

def main():
    print("🔨 正在打包 QQ 空间相册导出器...")
    print()

    # 检查 PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "-q"])

    # 构建命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "QQ空间相册导出器",
        "--add-data", f"templates{os.pathsep}templates",
        "--add-data", f"static{os.pathsep}static",
        "--add-data", f"qqzone_downloader.py{os.pathsep}.",
        "--add-data", f"qqzone_video_downloader.py{os.pathsep}.",
        "--hidden-import", "flask",
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--hidden-import", "json",
        "--hidden-import", "re",
        "--hidden-import", "threading",
        "--hidden-import", "webbrowser",
        "--hidden-import", "logging",
        "--hidden-import", "selenium",
        "--hidden-import", "webdriver_manager",
        "--clean",
        "-y",
        "app.py",
    ]

    subprocess.check_call(cmd)

    exe = os.path.join("dist", "QQ空间相册导出器.exe")
    if os.path.exists(exe):
        size_mb = os.path.getsize(exe) / (1024 * 1024)
        print()
        print(f"✅ 打包完成：dist\\QQ空间相册导出器.exe ({size_mb:.1f} MB)")
        print("   将此文件复制到任意目录，双击即可运行。")
    else:
        print()
        print("❌ 打包失败，请检查上方错误信息")

if __name__ == "__main__":
    main()
