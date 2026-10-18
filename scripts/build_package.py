"""项目打包脚本：生成生产环境可用的构建产物（dist/目录）

产物：
  dist/huawei-pc-marketing-agent-v<版本>.zip   源码交付包（可直接部署运行）
  dist/requirements-lock.txt                    依赖精确版本锁定
  dist/SHA256SUMS.txt                           产物校验和

安全约束：.env（含API密钥）、venv、缓存、日志、运行产物一律不入包。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DIST = PROJECT / "dist"
VERSION = "1.0"
PKG_NAME = f"huawei-pc-marketing-agent-v{VERSION}"

# 打包排除规则（安全与整洁）
EXCLUDE_DIRS = {"venv", "__pycache__", ".git", "data", "dist", ".pytest_cache", ".ruff_cache"}
EXCLUDE_FILES = {".env", ".DS_Store", ".env.local"}
EXCLUDE_SUFFIX = {".log", ".pyc", ".pyo"}


def should_include(path: Path) -> bool:
    rel = path.relative_to(PROJECT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if path.name in EXCLUDE_FILES:
        return False
    if path.suffix in EXCLUDE_SUFFIX:
        return False
    return True


def main() -> None:
    DIST.mkdir(exist_ok=True)
    zip_path = DIST / f"{PKG_NAME}.zip"

    # 1. 依赖锁定文件
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                            capture_output=True, text=True, check=True).stdout
    lock_path = DIST / "requirements-lock.txt"
    lock_path.write_text(freeze, encoding="utf-8")

    # 2. 源码打包
    files = sorted(p for p in PROJECT.rglob("*") if p.is_file() and should_include(p))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, f"{PKG_NAME}/{p.relative_to(PROJECT)}")
        zf.write(lock_path, f"{PKG_NAME}/requirements-lock.txt")

    # 3. 校验和
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sums_path = DIST / "SHA256SUMS.txt"
    sums_path.write_text(f"{sha}  {zip_path.name}\n", encoding="utf-8")

    # 4. 安全断言：密钥文件绝不能入包
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert not any(n.endswith("/.env") or n.endswith(".env") for n in names), "禁止打包.env"
    assert not any(".env" in n.split("/")[-1] and "example" not in n for n in names), "禁止打包密钥文件"
    assert not any("venv/" in n or "__pycache__" in n for n in names), "禁止打包虚拟环境/缓存"
    assert not any(n.startswith(f"{PKG_NAME}/data/") for n in names), "禁止打包运行数据"

    size_kb = zip_path.stat().st_size / 1024
    print(f"打包完成：{zip_path.name}")
    print(f"文件数：{len(files) + 1}（含依赖锁定）")
    print(f"大小：{size_kb:.1f} KB")
    print(f"SHA256：{sha}")
    print("安全校验通过：不含 .env / 密钥 / venv / 缓存 / 运行数据")


if __name__ == "__main__":
    main()
