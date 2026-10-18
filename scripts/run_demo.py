"""命令行Demo：按统一输出格式生成一篇图文软文

用法：
  python scripts/run_demo.py
  python scripts/run_demo.py --product "HUAWEI MateBook Pro" --audience 大学新生 \
      --scenario 开学季 --platform 小红书
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.models import Platform  # noqa: E402
from agent.pipeline import MarketingAgent, TaskError  # noqa: E402
from agent.models import Task  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="华为PC营销软文生成Demo")
    parser.add_argument("--product", default="HUAWEI MateBook Pro")
    parser.add_argument("--audience", default="大学新生")
    parser.add_argument("--scenario", default="开学季")
    parser.add_argument("--platform", default="小红书",
                        choices=["公众号", "小红书", "门店朋友圈", "门店海报"])
    parser.add_argument("--goal", default="种草")
    args = parser.parse_args()

    agent = MarketingAgent()
    status = agent.initialize()
    print(f"[知识库] 来源：{status['knowledge']['source']}｜{status['knowledge']['reason']}")

    task = Task(
        product=args.product,
        target_audience=args.audience,
        scenario=args.scenario,
        platform=Platform(args.platform),
        content_goal=args.goal,
    )
    try:
        result = agent.execute(task)
    except TaskError as e:
        print(f"[任务错误] {e}")
        sys.exit(1)

    print("\n===== 执行过程 =====")
    for step in (result.trace.steps if result.trace else []):
        print(f"[{step.status}] {step.step} ({step.duration_ms}ms) {step.detail}")

    print("\n===== 统一输出格式 =====\n")
    print(agent.export_markdown(result))

    out_dir = Path(__file__).resolve().parent.parent / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{task.task_id}.md"
    json_path = out_dir / f"{task.task_id}.json"
    md_path.write_text(agent.export_markdown(result), encoding="utf-8")
    json_path.write_text(agent.export_json(result), encoding="utf-8")
    print(f"\n[已保存] {md_path}")
    print(f"[已保存] {json_path}")


if __name__ == "__main__":
    main()
