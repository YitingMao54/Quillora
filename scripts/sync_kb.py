"""把外部 P1-P8 知识库同步为仓库内置快照（knowledge-base/）

用法：
    python scripts/sync_kb.py                    # 默认从项目上级目录同步
    python scripts/sync_kb.py --source ~/kb      # 指定知识库根目录
    python scripts/sync_kb.py --check            # 只比对差异，不写入

同步范围为 00 与 P1-P8 九个板块、待审核/历史归档，以及库级说明与统计文件；
点文件（.DS_Store 等）与赛题手册 PDF 等非知识库内容一律跳过。
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = PROJECT_ROOT / "knowledge-base"

SECTIONS = [
    "00-建库规范",
    "P1-产品参数库",
    "P2-卖点话术库",
    "P3-竞品资料库",
    "P4-价格政策库（机密）",
    "P5-培训赋能库",
    "P6-营销素材库",
    "P7-常见问题库",
    "P8-客户场景库",
    "90-待审核",
    "99-历史归档",
]

ROOT_FILES = [
    "README.md",
    "全库导航.md",
    "全库统计.json",
    "全库统计与校验报告.md",
    "公开来源总表.csv",
    "全库文件清单_SHA256.csv",
    "版本变更说明_v6.md",
    "版本变更说明_v7.md",
    "README-大型版说明.md",
    "导入ima说明.md",
]


def _iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            yield path


def _sync(source: Path, target: Path, check_only: bool) -> int:
    if not (source / "P1-产品参数库").is_dir():
        print(f"× 源目录不像是知识库根（缺少 P1-产品参数库）：{source}")
        return 2

    added = changed = same = 0
    for section in SECTIONS:
        src_dir = source / section
        if not src_dir.is_dir():
            print(f"! 跳过缺失板块：{section}")
            continue
        for src in _iter_files(src_dir):
            rel = src.relative_to(source)
            dst = target / rel
            if dst.exists() and filecmp.cmp(src, dst, shallow=False):
                same += 1
                continue
            status = "改" if dst.exists() else "增"
            added += not dst.exists()
            changed += dst.exists()
            print(f"  {status} {rel}")
            if not check_only:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    for name in ROOT_FILES:
        src = source / name
        if not src.is_file():
            continue
        dst = target / name
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            same += 1
            continue
        status = "改" if dst.exists() else "增"
        added += not dst.exists()
        changed += dst.exists()
        print(f"  {status} {name}")
        if not check_only:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    verb = "待同步" if check_only else "已同步"
    print(f"\n{verb}：新增 {added}，更新 {changed}，未变 {same}")
    if check_only and (added or changed):
        print("（--check 模式未写入，去掉该参数即执行同步）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 P1-P8 知识库到仓库内置快照")
    parser.add_argument("--source", default=str(PROJECT_ROOT.parent),
                        help="知识库根目录（默认：项目上级目录）")
    parser.add_argument("--target", default=str(DEFAULT_TARGET),
                        help="快照目录（默认：knowledge-base/）")
    parser.add_argument("--check", action="store_true", help="只比对，不写入")
    args = parser.parse_args()

    source, target = Path(args.source).expanduser().resolve(), Path(args.target).expanduser().resolve()
    if source == target:
        print("× 源目录与目标目录相同")
        return 2
    print(f"源：{source}\n目标：{target}\n")
    return _sync(source, target, args.check)


if __name__ == "__main__":
    sys.exit(main())
