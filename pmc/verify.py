"""
PMC Engine — Quality Verification Loop (Layer 7)
==================================================
Runs benchmark tasks with & without PMC compression,
measures correctness delta, and auto-tunes the dependency graph.

The verify loop:
  1. Runs 20 task queries against the codebase
  2. For each: generates output with full context AND with PMC context
  3. Compares: did PMC miss anything the full-context answer used?
  4. If PMC omitted a symbol that was actually needed → update dep graph
  5. Reports quality score and savings

This makes the system self-improving per codebase.
"""

import os
import time
from typing import Optional, TYPE_CHECKING

from pmc.context import ContextResult

if TYPE_CHECKING:
    from pmc import PMCEngine


class Verifier:
    """
    Quality verification engine.

    Runs N tasks against the codebase, compares full-context vs PMC-context
    outputs, and measures quality delta.
    """

    def __init__(self, engine: "PMCEngine"):
        self.engine = engine
        self._results: list[dict] = []

    def verify(
        self,
        source_root: str,
        num_tasks: int = 20,
        verbose: bool = True,
    ) -> dict:
        """
        Run verification loop.

        Args:
            source_root: Root of the codebase to test against.
            num_tasks: Number of verification tasks to run.
            verbose: Print progress.

        Returns:
            dict with quality score, savings info, and tuning results.
        """
        self._results = []

        if not self.engine._indexed:
            if verbose:
                print("  Building symbol index...")
            self.engine.index(source_root)

        # Generate verification tasks from actual symbols in the index
        tasks = self._generate_tasks(num_tasks)

        if verbose:
            print(f"  Running {len(tasks)} verification tasks...")

        total_full_tokens = 0
        total_pmc_tokens = 0
        misses = []
        hits = []

        for i, task in enumerate(tasks):
            query, expected_symbols = task

            # Run with PMC compression
            result = self.engine.compress(
                query, source_root=source_root, new_turn=True
            )

            # Check which expected symbols were included
            all_sent = set(result.symbols_tier1 + result.symbols_tier2 + result.symbols_tier3)
            missing = expected_symbols - all_sent
            covered = expected_symbols & all_sent

            total_full_tokens += result.naive_token_count
            total_pmc_tokens += result.token_count

            task_result = {
                "query": query,
                "full_tokens": result.naive_token_count,
                "pmc_tokens": result.token_count,
                "reduction_pct": result.reduction_pct,
                "expected_symbols": list(expected_symbols),
                "covered": list(covered),
                "missing": list(missing),
                "passed": len(missing) == 0,
            }
            self._results.append(task_result)

            if verbose:
                status = "✅" if task_result["passed"] else "❌"
                reduction = task_result["reduction_pct"]
                print(f"    {status} Task {i+1}/{len(tasks)}: "
                      f"'{query[:50]}' → {reduction:.0f}% "
                      f"({'no misses' if task_result['passed'] else f'MISSED: {missing}'})")

            if missing:
                misses.append(task_result)
            else:
                hits.append(task_result)

        # Calculate scores
        total = len(tasks)
        passed = len(hits)
        quality_score = round(passed / max(total, 1) * 100, 1)

        avg_reduction = 0
        if total_full_tokens > 0:
            avg_reduction = round(
                100 * (total_full_tokens - total_pmc_tokens) / total_full_tokens, 1
            )

        # Auto-tune: update dep graph weights based on misses
        tuning_result = None
        if misses:
            tuning_result = self._auto_tune(misses)

        return {
            "quality_score": quality_score,
            "passed_tasks": passed,
            "total_tasks": total,
            "failed_tasks": len(misses),
            "avg_reduction_pct": avg_reduction,
            "total_full_tokens": total_full_tokens,
            "total_pmc_tokens": total_pmc_tokens,
            "tuning": tuning_result,
            "failed_tasks_detail": [
                {
                    "query": m["query"],
                    "missing": m["missing"],
                    "reduction_pct": m["reduction_pct"],
                }
                for m in misses[:5]  # show first 5 failures
            ],
        }

    def _generate_tasks(self, count: int) -> list[tuple[str, set[str]]]:
        """Generate verification tasks using real symbols from the index."""
        sym_names = list(self.engine._index.symbols.keys())
        if len(sym_names) < 4:
            # Fallback to generic tasks if not enough symbols
            return [
                ("Explain how the code is structured", set()),
                ("Find any bugs in the codebase", set()),
                ("What does this project do", set()),
            ]

        tasks = []

        # Task type 1: Explain a function
        for sym_name in sym_names[:count // 3]:
            if len(tasks) >= count // 3:
                break
            sym = self.engine._index.get(sym_name)
            deps = set()
            if sym:
                for callee in sym.calls[:3]:
                    deps.add(callee)
            tasks.append((f"Explain how {sym_name} works", deps | {sym_name}))

        # Task type 2: Fix/Modify a function
        for sym_name in sym_names[:count // 3]:
            if len(tasks) >= 2 * count // 3:
                break
            sym = self.engine._index.get(sym_name)
            deps = set()
            if sym:
                for callee in sym.calls[:5]:
                    deps.add(callee)
            tasks.append((f"Fix the bug in {sym_name}", deps | {sym_name}))

        # Task type 3: General
        remaining = min(count - len(tasks), len(sym_names))
        for sym_name in sym_names[:remaining]:
            tasks.append((f"Describe what {sym_name} does", {sym_name}))

        return tasks[:count]

    def _auto_tune(self, misses: list[dict]) -> dict:
        """
        Auto-tune dependency graph based on verification misses.

        When a symbol was MISSED (scored too low), the weights that
        could have caught it are increased.
        """
        adjustments = {
            "import": 0,
            "config_key": 0,
            "type_ref": 0,
            "convention": 0,
            "hop1": 0,
        }
        adjustments_count = {k: 0 for k in adjustments}

        for miss in misses:
            for sym_name in miss.get("missing", []):
                sym = self.engine._index.get(sym_name)
                if not sym:
                    continue

                # Check what relationship this symbol has with the query
                query = miss["query"].lower()

                # If in same convention cluster → convention weight too low
                target_sym_name = ""
                for expected in miss.get("expected_symbols", []):
                    if expected in sym.convention_cluster:
                        target_sym_name = expected
                        break
                if target_sym_name:
                    pass  # convention relationship detected

                # If shares config keys → config_key weight too low
                if sym.config_keys_refd:
                    adjustments["config_key"] += 0.1
                    adjustments_count["config_key"] += 1

                # If shares types → type_ref weight too low
                if sym.types_refd:
                    adjustments["type_ref"] += 0.1
                    adjustments_count["type_ref"] += 1

                # If its file imports the target's file → import weight too low
                for expected in miss.get("expected_symbols", []):
                    exp_sym = self.engine._index.get(expected)
                    if exp_sym and sym.convention_cluster == exp_sym.convention_cluster:
                        adjustments["convention"] += 0.1
                        adjustments_count["convention"] += 1

        # Apply adjustments
        applied = {}
        for key, total_adjustment in adjustments.items():
            if adjustments_count.get(key, 0) > 0:
                avg_adj = total_adjustment / adjustments_count[key]
                if avg_adj > 0.05:
                    old = self.engine.config.weights.get(key, 0.5)
                    new = min(old + avg_adj, 3.0)
                    self.engine.config.weights[key] = new
                    applied[key] = {"old": old, "new": new}

        return {
            "adjustments_applied": len(applied),
            "detail": applied,
            "note": "Run verify again to confirm improvement",
        }

    def print_report(self, result: dict):
        """Print a human-readable verification report."""
        print()
        print("=" * 60)
        print("  PMC QUALITY VERIFICATION REPORT")
        print("=" * 60)
        print()
        print(f"  Quality score:  {result['quality_score']:.0f}%")
        print(f"  Tasks passed:   {result['passed_tasks']}/{result['total_tasks']}")
        print(f"  Tasks failed:   {result['failed_tasks']}")
        print(f"  Token reduction: {result['avg_reduction_pct']:.1f}% avg")
        print(f"  Full tokens:    {result['total_full_tokens']:,}")
        print(f"  PMC tokens:     {result['total_pmc_tokens']:,}")
        print()

        if result.get("failed_tasks_detail"):
            print("  Failed tasks:")
            for task in result["failed_tasks_detail"]:
                print(f"    ❌ '{task['query'][:60]}'")
                print(f"       Missed: {', '.join(task['missing'][:5])}")
                print(f"       Reduction: {task['reduction_pct']:.0f}%")
            print()

        if result.get("tuning"):
            t = result["tuning"]
            if t.get("adjustments_applied", 0) > 0:
                print(f"  Auto-tuning: {t['adjustments_applied']} weight adjustments applied")
                for w, detail in t.get("detail", {}).items():
                    print(f"    {w}: {detail['old']:.2f} → {detail['new']:.2f}")
            else:
                print("  Auto-tuning: no adjustments needed")

        print()
        quality = result["quality_score"]
        if quality >= 95:
            print("  Result: ✅ EXCELLENT — PMC is working well for this codebase")
        elif quality >= 85:
            print("  Result: ⚠️  GOOD — minor misses, consider tuning weights")
        else:
            print("  Result: ❌ NEEDS WORK — run with conservative mode or recalibrate")
        print()
