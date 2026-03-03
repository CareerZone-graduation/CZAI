#!/usr/bin/env python
"""
Standalone script đánh giá model recommendation.

KHÔNG thay đổi code hay model đang chạy — chỉ đọc và đánh giá.

Modes:
  current  — Đánh giá model đã train (đang serve) trên toàn bộ interactions.
             Cho train metrics, nhanh (~vài giây).
  split    — Train/test split: train model tạm, đánh giá trên test set.
             Cho test metrics chính xác hơn (~vài phút).

Usage:
  python scripts/evaluate_model.py                        # mode=current, k=10
  python scripts/evaluate_model.py --mode split           # train/test split
  python scripts/evaluate_model.py --mode split --k 20    # top-20
  python scripts/evaluate_model.py --mode split --ratio 0.3  # 30% test
  python scripts/evaluate_model.py --mode current --k 5   # top-5 train metrics
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Thêm project root vào PATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import close_db, connect_db
from app.services.recommendation.evaluator import (
    evaluate_current_model,
    evaluate_train_test_split,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(
        description="Đánh giá chất lượng model recommendation (standalone).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Quick eval (train metrics)
  %(prog)s --mode split             # Offline eval (train/test split)
  %(prog)s --mode split --k 20      # Top-20 metrics
  %(prog)s --mode split --ratio 0.3 # 30%% test set

Metrics giải thích:
  precision@K   Tỷ lệ items gợi ý đúng trong top-K
  recall@K      Tỷ lệ items đúng được gợi ý trong top-K
  auc           Khả năng rank positive > negative (0.5 = random)
  mrr           1/rank của item đúng đầu tiên
  hit_rate@K    %% users có ≥1 hit trong top-K
  coverage@K    %% catalog items xuất hiện trong top-K recommendations
        """,
    )
    parser.add_argument(
        "--mode", choices=["current", "split"], default="current",
        help="Chế độ đánh giá: 'current' (train metrics) hoặc 'split' (train/test). Default: current",
    )
    parser.add_argument(
        "--k", type=int, default=10,
        help="Top-K cho precision/recall/hit_rate. Default: 10",
    )
    parser.add_argument(
        "--ratio", type=float, default=0.2,
        help="Tỷ lệ test set (chỉ dùng với --mode split). Default: 0.2",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON (cho CI/pipeline).",
    )
    args = parser.parse_args()

    results = asyncio.run(_run(args))

    # ── Output ────────────────────────────────────────────────────────────────
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        _pretty_print(results, args.mode, args.k)

    # Exit code: 0 = success, 1 = error/skipped
    status = results.get("status", "error")
    sys.exit(0 if status == "success" else 1)


async def _run(args) -> dict:
    await connect_db()
    try:
        if args.mode == "current":
            return evaluate_current_model(k=args.k)
        else:
            return evaluate_train_test_split(test_ratio=args.ratio, k=args.k)
    finally:
        await close_db()


def _pretty_print(results: dict, mode: str, k: int):
    """In kết quả dạng bảng dễ đọc."""
    status = results.get("status", "unknown")

    if status != "success":
        print(f"\n⚠  Evaluation {status}: {results.get('reason', 'unknown')}")
        return

    print("\n" + "═" * 60)
    if mode == "current":
        print("  MODEL EVALUATION — Current Model (Train Metrics)")
    else:
        print("  MODEL EVALUATION — Train/Test Split (Offline)")
    print("═" * 60)

    # Data info
    if mode == "split":
        print(f"\n  Data split:")
        print(f"    Train interactions : {results.get('n_train_interactions', '?')}")
        print(f"    Test interactions  : {results.get('n_test_interactions', '?')}")
        print(f"    Test ratio         : {results.get('test_ratio', '?')}")
    print(f"    Users              : {results.get('n_users', results.get('n_users_evaluated', '?'))}")
    print(f"    Items              : {results.get('n_items', '?')}")

    # Metrics
    print(f"\n  {'Metric':<25} {'Value':>10}")
    print(f"  {'─' * 25} {'─' * 10}")

    if mode == "current":
        _print_metric(f"Precision@{k}", results.get(f"precision@{k}"))
        _print_metric(f"Recall@{k}", results.get(f"recall@{k}"))
        _print_metric("AUC", results.get("auc"))
        _print_metric("MRR", results.get("mrr"))
    else:
        # Test metrics
        print(f"  {'[Test Set]':<25}")
        _print_metric(f"Precision@{k}", results.get(f"test_precision@{k}"))
        _print_metric(f"Recall@{k}", results.get(f"test_recall@{k}"))
        _print_metric("AUC", results.get("test_auc"))
        _print_metric("MRR", results.get("test_mrr"))
        _print_metric(f"Hit Rate@{k}", results.get(f"test_hit_rate@{k}"))
        _print_metric(f"Coverage@{k}", results.get(f"test_coverage@{k}"))

        # Train metrics
        print(f"\n  {'[Train Set — overfitting check]':<25}")
        _print_metric(f"Precision@{k}", results.get(f"train_precision@{k}"))
        _print_metric("AUC", results.get("train_auc"))

    print(f"\n  Elapsed: {results.get('elapsed_seconds', '?')}s")
    print(f"  Evaluated at: {results.get('evaluated_at', '?')}")
    print("═" * 60 + "\n")


def _print_metric(name: str, value):
    if value is not None:
        v = float(value)
        if "AUC" in name:
            indicator = "✓" if v > 0.7 else ("~" if v > 0.55 else "✗")
        elif "Coverage" in name:
            indicator = "✓" if v > 0.3 else ("~" if v > 0.1 else "✗")
        else:
            indicator = "✓" if v > 0.1 else ("~" if v > 0.02 else "✗")
        print(f"  {indicator} {name:<23} {v:>10.4f}")
    else:
        print(f"    {name:<23} {'N/A':>10}")


if __name__ == "__main__":
    main()
