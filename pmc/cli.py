"""
PMC Engine — CLI Entry Point
=============================
Provides the `pmc` command with subcommands:
    pmc index       Build symbol index
    pmc compress    Compress a query
    pmc serve       Start HTTP proxy
    pmc mcp         Start MCP server
    pmc bench       Run benchmark
    pmc verify      Run quality verification
    pmc calibrate   Auto-tune scoring weights
    pmc install-cc-hooks   Install Claude Code hooks
    pmc stats       Show compression stats
    pmc version     Show version
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="pmc",
        description="PMC Engine — Predictive Minimal Context",
        epilog="Cut AI coding token costs by 40-80%% via AST-based surgical context compression.",
    )
    parser.add_argument("--version", action="store_true", help="Show version")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # index
    p_index = subparsers.add_parser("index", help="Build symbol index for a codebase")
    p_index.add_argument("directory", nargs="?", default=".", help="Codebase root directory")
    p_index.add_argument("--mode", choices=["conservative", "balanced", "aggressive"], default="balanced",
                         help="Compression mode")

    # compress
    p_compress = subparsers.add_parser("compress", help="Compress a query into surgical context")
    p_compress.add_argument("query", nargs="+", help="Natural language query")
    p_compress.add_argument("--source", default=".", help="Codebase root")
    p_compress.add_argument("--mode", choices=["conservative", "balanced", "aggressive"], default="balanced",
                            help="Compression mode")
    p_compress.add_argument("--json", action="store_true", help="Output as JSON")

    # serve
    p_serve = subparsers.add_parser("serve", help="Start HTTP proxy server")
    p_serve.add_argument("--port", type=int, default=None, help="Proxy port (default: 8080)")
    p_serve.add_argument("--host", default=None, help="Proxy host (default: 0.0.0.0)")
    p_serve.add_argument("--mode", choices=["conservative", "balanced", "aggressive"], default="balanced",
                         help="Compression mode")

    # mcp
    p_mcp = subparsers.add_parser("mcp", help="Start MCP server")
    p_mcp.add_argument("--mode", choices=["conservative", "balanced", "aggressive"], default="balanced",
                       help="Compression mode")

    # bench
    p_bench = subparsers.add_parser("bench", help="Run benchmark")
    p_bench.add_argument("directory", nargs="?", default=".", help="Codebase to benchmark against")
    p_bench.add_argument("--mode", choices=["conservative", "balanced", "aggressive"], default="balanced",
                         help="Compression mode")

    # verify
    p_verify = subparsers.add_parser("verify", help="Run quality verification")
    p_verify.add_argument("directory", nargs="?", default=".", help="Codebase to verify against")
    p_verify.add_argument("--tasks", type=int, default=20, help="Number of verification tasks")
    p_verify.add_argument("--mode", choices=["conservative", "balanced", "aggressive"], default="balanced",
                          help="Compression mode")

    # calibrate
    p_cal = subparsers.add_parser("calibrate", help="Auto-tune scoring weights")
    p_cal.add_argument("directory", nargs="?", default=".", help="Codebase to calibrate for")
    p_cal.add_argument("--mode", choices=["conservative", "balanced", "aggressive"], default="balanced",
                       help="Compression mode")

    # install-cc-hooks
    p_install = subparsers.add_parser("install-cc-hooks", help="Install Claude Code hooks")
    p_install.add_argument("--target", default=".", help="Project directory to install hooks into")
    p_install.add_argument("--force", action="store_true", help="Overwrite existing hooks")

    # stats
    p_stats = subparsers.add_parser("stats", help="Show compression statistics")
    p_stats.add_argument("directory", nargs="?", default=".", help="Codebase directory")

    args = parser.parse_args()

    if args.version:
        print("pmc-engine v0.1.0")
        return

    if not args.command:
        parser.print_help()
        return

    # Execute command
    command_map = {
        "index": cmd_index,
        "compress": cmd_compress,
        "serve": cmd_serve,
        "mcp": cmd_mcp,
        "bench": cmd_bench,
        "verify": cmd_verify,
        "calibrate": cmd_calibrate,
        "install-cc-hooks": cmd_install_hooks,
        "stats": cmd_stats,
    }

    cmd_fn = command_map.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


# ─── Command Implementations ────────────────────────────────────────────────


def _load_engine(args) -> "PMCEngine":
    """Load PMC engine with config from args."""
    from pmc import PMCEngine, PMCConfig, CompressionMode

    config = PMCConfig.load(getattr(args, "directory", ".") or ".")
    if hasattr(args, "mode") and args.mode:
        config.mode = args.mode
        config._apply_mode()

    engine = PMCEngine(config=config)
    return engine


def cmd_index(args):
    """Build symbol index."""
    engine = _load_engine(args)
    print(f"\n  PMC — Building index for {args.directory}")
    print(f"  Mode: {args.mode}")
    print()

    t0 = time.time()
    stats = engine.index(args.directory)
    elapsed = time.time() - t0

    print(f"  ✅ Indexed {stats['symbols']} symbols across {stats['files']} files")
    print(f"  ⚡ Build time: {stats['duration_ms']}ms (wall: {elapsed*1000:.0f}ms)")
    print(f"  🔗 Edges: {stats['edges']}")
    if stats.get("errors"):
        print(f"  ⚠ Errors: {len(stats['errors'])}")
        for err in stats["errors"][:5]:
            print(f"    {err}")

    sym_names = list(engine._index.symbols.keys())
    if sym_names:
        print(f"  📊 Sample symbols: {', '.join(sym_names[:8])}")
    print()


def cmd_compress(args):
    """Compress a query."""
    engine = _load_engine(args)
    query = " ".join(args.query)

    if not engine._indexed:
        print(f"  Indexing {args.source}...")
        engine.index(args.source)

    print(f"\n  Query: {query}")
    print(f"  Mode:  {args.mode}")
    print()

    result = engine.compress(query, source_root=args.source)

    if args.json:
        print(json.dumps({
            "context_string": result.context_string,
            "token_count": result.token_count,
            "naive_token_count": result.naive_token_count,
            "reduction_pct": result.reduction_pct,
            "tier1": result.symbols_tier1,
            "tier2": result.symbols_tier2,
            "tier3": result.symbols_tier3,
            "blast_radius": result.blast_radius_syms,
        }, indent=2))
    else:
        print(result.context_string)
        print()
        print(result.summary())
        print()


def cmd_serve(args):
    """Start HTTP proxy."""
    from pmc.proxy.server import start_proxy

    host = args.host or "0.0.0.0"
    port = args.port or 8080
    mode = args.mode

    print(f"\n  🔌 PMC Proxy — {host}:{port}")
    print(f"  Mode: {mode}")
    print()
    print("  Set your AI tool to use this proxy:")
    print(f"    export ANTHROPIC_BASE_URL=http://{host}:{port}")
    print(f"    export OPENAI_BASE_URL=http://{host}:{port}/v1")
    print()
    print("  Press Ctrl+C to stop")
    print()

    start_proxy(host=host, port=port, mode=mode)


def cmd_mcp(args):
    """Start MCP server."""
    from pmc.mcp.server import start_mcp_server

    start_mcp_server(mode=args.mode)


def cmd_bench(args):
    """Run benchmark."""
    engine = _load_engine(args)
    source_dir = args.directory

    stats = engine.index(source_dir)

    sym_names = list(engine._index.symbols.keys())
    print()
    print("  ═" + "═" * 70)
    print("  ║  PMC ENGINE — LIVE BENCHMARK")
    print("  ═" + "═" * 70)
    print()
    print(f"  Indexed {stats['symbols']} symbols across {stats['files']} files")
    print(f"  Build time: {stats['duration_ms']}ms")
    if sym_names:
        print(f"  Sample: {', '.join(sym_names[:8])}")
    print()

    def sym(i):
        return sym_names[i] if i < len(sym_names) else "index"

    queries = [
        (f"Fix the bug in {sym(0)}", "MODIFY"),
        (f"Add error handling to {sym(1) if len(sym_names) > 1 else 'index'}", "CREATE"),
        (f"Explain how {sym(2) if len(sym_names) > 2 else 'index'} works", "READ"),
        (f"Refactor {sym(3) if len(sym_names) > 3 else 'index'} for better performance", "REFACTOR"),
        (f"Why does {sym(4) if len(sym_names) > 4 else 'index'} fail on large input", "DEBUG"),
        (f"Write unit tests for {sym(5) if len(sym_names) > 5 else 'index'}", "TEST"),
        (f"Modify {sym(0)} to call {sym(6) if len(sym_names) > 6 else 'index'}", "MODIFY"),
        (f"What does {sym(7) if len(sym_names) > 7 else 'index'} return", "READ"),
    ]

    header = f"{'Query':<46} {'Naive':>8} {'PMC':>8} {'Saved':>9}"
    print("  " + header)
    print("  " + "─" * len(header))

    total_naive = 0
    total_pmc = 0

    for query, op_hint in queries:
        engine.new_conversation()
        result = engine.compress(query, source_root=source_dir)

        naive = result.naive_token_count
        pmc = result.token_count
        pct = result.reduction_pct

        total_naive += naive
        total_pmc += pmc

        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        label = query[:44] + ".." if len(query) > 44 else query
        print(f"  {label:<46} {naive:>8,} {pmc:>8,} {pct:>8.1f}%  {bar}")

    avg_savings = round(100 * (total_naive - total_pmc) / max(total_naive, 1), 1)
    print("  " + "─" * len(header))
    print(f"  {'AVERAGE REDUCTION':<46} {'':>8} {'':>8} {avg_savings:>8.1f}%")
    print()
    print("  ═" + "═" * 70)

    # Cost projections
    COST_PER_1K = 0.003
    QUERIES_PER_ENG_PER_DAY = 80
    WORKING_DAYS = 250

    avg_naive = total_naive / max(len(queries), 1)
    avg_pmc = total_pmc / max(len(queries), 1)

    print()
    print("  Enterprise savings projections:")
    print()
    for company, engineers in [("Uber", 5000), ("Mid startup", 500), ("Large bank", 10000)]:
        naive_cost = avg_naive * QUERIES_PER_ENG_PER_DAY * WORKING_DAYS * engineers * COST_PER_1K / 1000
        pmc_cost = avg_pmc * QUERIES_PER_ENG_PER_DAY * WORKING_DAYS * engineers * COST_PER_1K / 1000
        saved = naive_cost - pmc_cost
        print(f"  {company:<20} {engineers:>6} eng  "
              f"${naive_cost:>9,.0f}/yr → ${pmc_cost:>8,.0f}/yr  save ${saved:>9,.0f}/yr")

    print()
    print("  ═" + "═" * 70)
    print()


def cmd_verify(args):
    """Run quality verification."""
    engine = _load_engine(args)
    source_dir = args.directory

    print(f"\n  Running {args.tasks} verification tasks on {source_dir}")
    print(f"  Mode: {args.mode}")
    print()

    result = engine.verify(source_dir, num_tasks=args.tasks)

    if hasattr(engine, 'verifier') and engine.verifier:
        engine.verifier.print_report(result)
    else:
        print(json.dumps(result, indent=2, default=str))


def cmd_calibrate(args):
    """Auto-tune scoring weights."""
    engine = _load_engine(args)
    source_dir = args.directory

    print(f"\n  Calibrating scoring weights for {source_dir}")
    print(f"  Mode: {args.mode}")
    print()

    # Need index first
    if not engine._indexed:
        engine.index(source_dir)

    result = engine.calibrate(source_dir)

    print(f"  Best weights:")
    for k, v in result.get("best_weights", {}).items():
        print(f"    {k}: {v:.1f}")
    print(f"  Estimated reduction: {result.get('estimated_reduction', 'N/A')}")
    print()


def cmd_install_hooks(args):
    """Install Claude Code hooks."""
    target = args.target
    force = args.force
    hooks_dir = os.path.join(target, "hooks")

    os.makedirs(hooks_dir, exist_ok=True)
    os.makedirs(os.path.join(target, ".claude"), exist_ok=True)

    # Check for existing settings
    settings_path = os.path.join(target, ".claude", "settings.json")
    if os.path.exists(settings_path) and not force:
        print(f"  ⚠ {settings_path} already exists. Use --force to overwrite.")
        return

    # Write hooks
    script_dir = os.path.dirname(os.path.abspath(__file__))
    hook_src = os.path.join(os.path.dirname(script_dir), "hooks")

    if os.path.exists(hook_src):
        import shutil
        for fname in os.listdir(hook_src):
            if fname.endswith(".sh") or fname.endswith(".json"):
                src = os.path.join(hook_src, fname)
                dst = os.path.join(hooks_dir, fname)
                shutil.copy2(src, dst)
                if fname.endswith(".sh"):
                    os.chmod(dst, 0o755)

    print(f"  ✅ Installed hooks to {hooks_dir}")
    print()
    print("  To activate, add to your .claude/settings.json:")
    print('  {')
    print('    "hooks": {')
    print('      "UserPromptSubmit": "hooks/user-prompt-submit.sh",')
    print('      "PreToolUse": "hooks/pre-tool-use.sh"')
    print('    }')
    print('  }')
    print()


def cmd_stats(args):
    """Show compression statistics."""
    engine = _load_engine(args)

    if not engine._indexed:
        engine.index(args.directory)

    stats = engine.stats()
    index = stats.get("index", {})
    session = stats.get("session", {})

    print()
    print(f"  PMC Engine Stats")
    print(f"  {'─' * 40}")
    print(f"  Mode:               {stats.get('config_mode', 'N/A')}")
    print(f"  Enabled:            {stats.get('config_enabled', True)}")
    print(f"  Total symbols:      {index.get('total_symbols', 0):,}")
    print(f"  Total files:        {index.get('total_files', 0)}")
    print(f"  Call graph edges:   {index.get('total_edges', 0):,}")
    print(f"  Imports tracked:    {index.get('total_imports', 0):,}")
    print(f"  Coupling hints:     {index.get('total_coupling_hints', 0):,}")
    print(f"  Index size (json):  {index.get('index_size_bytes', 0):,} bytes")
    print(f"  Build time:         {index.get('build_time_ms', 0)}ms")
    print(f"  Cached symbols:     {session.get('cached_symbols', 0)}")
    print(f"  Current turn:       {session.get('current_turn', 0)}")
    print()


if __name__ == "__main__":
    main()
