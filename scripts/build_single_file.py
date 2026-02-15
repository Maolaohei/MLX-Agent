#!/usr/bin/env python3
"""
单文件打包脚本

使用 PyInstaller 将 MLX-Agent 打包为单个可执行文件
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.resolve()


def check_pyinstaller():
    """检查 PyInstaller 是否安装"""
    try:
        import PyInstaller
        return True
    except ImportError:
        print("❌ PyInstaller not installed.")
        print("   Install with: pip install pyinstaller")
        return False


def build_single_file():
    """构建单文件版本"""
    project_root = get_project_root()
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    print(f"📦 Building MLX-Agent single-file executable...")
    print(f"   Project root: {project_root}")

    # 清理旧的构建文件
    if build_dir.exists():
        print("🧹 Cleaning old build files...")
        shutil.rmtree(build_dir)

    if (dist_dir / "mlx-agent").exists():
        print("🧹 Cleaning old dist files...")
        shutil.rmtree(dist_dir / "mlx-agent")

    # 构建参数
    args = [
        str(project_root / "mlx_agent" / "__main__.py"),
        "--onefile",
        "--name", "mlx-agent",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(project_root),
        "--clean",
        # 隐藏导入
        "--hidden-import", "chromadb",
        "--hidden-import", "sentence_transformers",
        "--hidden-import", "duckduckgo_search",
        "--hidden-import", "readability",
        "--hidden-import", "playwright",
        "--hidden-import", "ollama",
        "--hidden-import", "telegram",
        "--hidden-import", "discord",
        "--hidden-import", "openai",
        "--hidden-import", "anthropic",
        # 数据文件
        "--add-data", f"{project_root}/config:config",
        # 排除不必要的模块以减小体积
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide2",
        "--exclude-module", "PySide6",
        "--exclude-module", "numpy.random._examples",
    ]

    print(f"🔧 Running PyInstaller...")
    print(f"   Args: {' '.join(args)}")

    try:
        import PyInstaller.__main__
        PyInstaller.__main__.run(args)
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return False

    # 检查输出
    output_file = dist_dir / "mlx-agent"
    if sys.platform == "win32":
        output_file = dist_dir / "mlx-agent.exe"

    if output_file.exists():
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"✅ Build successful!")
        print(f"   Output: {output_file}")
        print(f"   Size: {size_mb:.2f} MB")
        return True
    else:
        print(f"❌ Output file not found: {output_file}")
        return False


def build_minimal():
    """构建最小版本（不包含可选依赖）"""
    project_root = get_project_root()
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    print(f"📦 Building MLX-Agent minimal single-file executable...")
    print(f"   Project root: {project_root}")

    # 清理旧的构建文件
    if build_dir.exists():
        print("🧹 Cleaning old build files...")
        shutil.rmtree(build_dir)

    # 构建参数（最小版本，排除重型依赖）
    args = [
        str(project_root / "mlx_agent" / "__main__.py"),
        "--onefile",
        "--name", "mlx-agent-minimal",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(project_root),
        "--clean",
        # 只包含核心隐藏导入
        "--hidden-import", "mlx_agent.memory.sqlite",  # 使用 SQLite 后端
        "--hidden-import", "mlx_agent.tools.file",
        "--hidden-import", "mlx_agent.tools.http",
        # 排除所有重型依赖
        "--exclude-module", "chromadb",
        "--exclude-module", "sentence_transformers",
        "--exclude-module", "duckduckgo_search",
        "--exclude-module", "readability",
        "--exclude-module", "playwright",
        "--exclude-module", "ollama",
        "--exclude-module", "telegram",
        "--exclude-module", "discord",
        "--exclude-module", "openai",
        "--exclude-module", "anthropic",
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide2",
        "--exclude-module", "PySide6",
        "--exclude-module", "numpy.random._examples",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
    ]

    print(f"🔧 Running PyInstaller (minimal)...")
    print(f"   Args: {' '.join(args)}")

    try:
        import PyInstaller.__main__
        PyInstaller.__main__.run(args)
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return False

    # 检查输出
    output_file = dist_dir / "mlx-agent-minimal"
    if sys.platform == "win32":
        output_file = dist_dir / "mlx-agent-minimal.exe"

    if output_file.exists():
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"✅ Minimal build successful!")
        print(f"   Output: {output_file}")
        print(f"   Size: {size_mb:.2f} MB")
        return True
    else:
        print(f"❌ Output file not found: {output_file}")
        return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Build MLX-Agent single-file executable")
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Build minimal version without heavy dependencies"
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Build both full and minimal versions"
    )

    args = parser.parse_args()

    if not check_pyinstaller():
        sys.exit(1)

    success = True

    if args.both:
        success = build_single_file() and build_minimal()
    elif args.minimal:
        success = build_minimal()
    else:
        success = build_single_file()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
