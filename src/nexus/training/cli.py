"""
CLI tool for managing NEXUS coding training data.

Usage:
    python -m nexus.training.cli add
    python -m nexus.training.cli list
    python -m nexus.training.cli search "binary search"
    python -m nexus.training.cli import seed
    python -m nexus.training.cli stats
    python -m nexus.training.cli export
    python -m nexus.training.cli chat
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nexus.application.training.coding_store import CodingExample, CodingStore

STORE_PATH = Path("data/coding_examples.json")


def cmd_add(args):
    """Add a coding example interactively."""
    store = CodingStore(STORE_PATH)
    print("=== Add Coding Example ===")
    task = input("Task (what the user asks): ").strip()
    language = input("Language [python]: ").strip() or "python"
    category = input("Category [algorithms]: ").strip() or "algorithms"
    difficulty = input("Difficulty [medium]: ").strip() or "medium"
    tags = input("Tags (comma-separated): ").strip()
    explanation = input("Approach explanation: ").strip()
    print("Solution (end with empty line):")
    solution_lines = []
    while True:
        line = input()
        if line == "":
            break
        solution_lines.append(line)
    solution = "\n".join(solution_lines)
    print("Test cases (end with empty line, optional):")
    test_lines = []
    while True:
        line = input()
        if line == "":
            break
        test_lines.append(line)
    test_cases = "\n".join(test_lines)

    ex = CodingExample(
        task=task,
        solution=solution,
        language=language,
        category=category,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        explanation=explanation,
        test_cases=test_cases,
        difficulty=difficulty,
    )
    store.add(ex)
    print(f"Added example: {ex.id}")


def cmd_add_json(args):
    """Add a coding example from JSON file or stdin."""
    store = CodingStore(STORE_PATH)
    if args.file == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(Path(args.file).read_text())

    if isinstance(data, list):
        examples = [CodingExample.from_dict(d) for d in data]
        count = store.add_batch(examples)
        print(f"Imported {count} examples")
    else:
        ex = CodingExample.from_dict(data)
        store.add(ex)
        print(f"Added example: {ex.id}")


def cmd_list(args):
    """List all coding examples."""
    store = CodingStore(STORE_PATH)
    examples = store.list_all()
    if not examples:
        print("No examples found. Use 'add' or 'import seed' to add some.")
        return
    print(f"{'ID':<8} {'Lang':<10} {'Category':<15} {'Diff':<8} {'Task'}")
    print("-" * 80)
    for ex in examples:
        task_short = ex.task[:50] + "..." if len(ex.task) > 50 else ex.task
        print(f"{ex.id:<8} {ex.language:<10} {ex.category:<15} {ex.difficulty:<8} {task_short}")


def cmd_search(args):
    """Search coding examples."""
    store = CodingStore(STORE_PATH)
    examples = store.search(args.query, category=args.category, limit=args.limit)
    if not examples:
        print("No matching examples found.")
        return
    for i, ex in enumerate(examples, 1):
        print(f"\n{'='*60}")
        print(f"Example {i}: {ex.id} ({ex.language}, {ex.category})")
        print(f"Task: {ex.task}")
        print(f"Solution:\n{ex.solution}")
        if ex.test_cases:
            print(f"Tests:\n{ex.test_cases}")


def cmd_stats(args):
    """Show training data statistics."""
    store = CodingStore(STORE_PATH)
    stats = store.stats()
    print(f"Total examples: {stats['total']}")
    print(f"Languages: {json.dumps(stats['languages'], indent=2)}")
    print(f"Categories: {json.dumps(stats['categories'], indent=2)}")


def cmd_delete(args):
    """Delete a coding example by ID."""
    store = CodingStore(STORE_PATH)
    if store.delete(args.id):
        print(f"Deleted: {args.id}")
    else:
        print(f"Not found: {args.id}")


def cmd_export(args):
    """Export all examples as JSON."""
    store = CodingStore(STORE_PATH)
    examples = store.list_all()
    data = [e.to_dict() for e in examples]
    if args.output:
        Path(args.output).write_text(json.dumps(data, indent=2))
        print(f"Exported {len(data)} examples to {args.output}")
    else:
        print(json.dumps(data, indent=2))


def cmd_import_seed(args):
    """Import the built-in seed coding examples."""
    from nexus.application.training.seed_data import SEED_EXAMPLES

    store = CodingStore(STORE_PATH)
    # Deduplicate by task
    existing = {e.task for e in store.list_all()}
    new_examples = [e for e in SEED_EXAMPLES if e.task not in existing]
    if not new_examples:
        print("All seed examples already imported.")
        return
    count = store.add_batch(new_examples)
    print(f"Imported {count} new seed examples ({len(SEED_EXAMPLES) - count} already existed)")


def cmd_chat(args):
    """Interactive coding chat with NEXUS (uses local LM Studio)."""
    import asyncio

    from nexus.application.training.coding_prompt import CodingRAG
    from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider

    store = CodingStore(STORE_PATH)
    rag = CodingRAG(store, max_examples=args.few_shot)

    llm = OpenAIProvider(
        api_key="local-no-key",
        model=args.model,
        base_url=args.base_url,
        default_max_tokens=args.max_tokens,
    )

    print(f"NEXUS Coding Assistant (model: {args.model})")
    print(f"Training examples: {store.stats()['total']}")
    print(f"Few-shot examples: {args.few_shot}")
    print("Type 'quit' to exit, 'stats' for training data info.\n")

    conversation = [{"role": "system", "content": rag.build_coding_prompt("Initialize coding assistant")}]

    async def chat_loop():
        while True:
            try:
                user_input = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break
            if not user_input:
                continue
            if user_input.lower() == "quit":
                break
            if user_input.lower() == "stats":
                print(json.dumps(store.stats(), indent=2))
                continue
            if user_input.lower() == "examples":
                for ex in store.list_all()[-5:]:
                    print(f"  {ex.id}: {ex.task[:60]}")
                continue

            # Build prompt with few-shot examples
            conversation.append(
                {"role": "system", "content": f"Relevant examples:\n{rag.get_few_shot_context(user_input)}"}
            )
            conversation.append({"role": "user", "content": user_input})

            try:
                response = await llm.complete(conversation, max_tokens=args.max_tokens)
                conversation.append({"role": "assistant", "content": response})
                print(f"\nNEXUS> {response}\n")
            except Exception as e:
                print(f"\nError: {e}\n")

    asyncio.run(chat_loop())


def main(argv=None):
    parser = argparse.ArgumentParser(description="NEXUS Coding Trainer CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("add", help="Add a coding example interactively")
    sub.add_parser("list", help="List all examples")

    p_add_json = sub.add_parser("add-json", help="Add from JSON file")
    p_add_json.add_argument("file", help="JSON file path or - for stdin")

    p_search = sub.add_parser("search", help="Search examples")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--category", help="Filter by category")
    p_search.add_argument("--limit", type=int, default=5)

    sub.add_parser("stats", help="Show statistics")
    sub.add_parser("import-seed", help="Import built-in seed examples")

    p_export = sub.add_parser("export", help="Export all as JSON")
    p_export.add_argument("--output", "-o", help="Output file")

    p_delete = sub.add_parser("delete", help="Delete example by ID")
    p_delete.add_argument("id", help="Example ID")

    p_chat = sub.add_parser("chat", help="Interactive coding chat")
    p_chat.add_argument("--model", default="qwen/qwen3.5-9b", help="Model name")
    p_chat.add_argument("--base-url", default="http://localhost:1234/v1", help="LM Studio URL")
    p_chat.add_argument("--max-tokens", type=int, default=8192, help="Max tokens")
    p_chat.add_argument("--few-shot", type=int, default=3, help="Number of few-shot examples")

    p_lora = sub.add_parser("lora", help="Offline LoRA fine-tuning on consensus-approved work (Space 8)")
    p_lora.add_argument("--output-dir", default="lora_out", help="Directory for the dataset and gate reports")
    p_lora.add_argument(
        "--baseline", type=float, default=0.0, help="Current model's golden-set pass rate (the swap gate)"
    )
    p_lora.add_argument(
        "--min-pass-rate", type=float, default=0.0, help="Absolute floor; a candidate below it is blocked"
    )
    p_lora.add_argument(
        "--consensus-state", default="", help="Consensus state file (default: rendezvous root)"
    )
    p_lora.add_argument(
        "--run-eval",
        action="store_true",
        help="Run the golden-set eval now instead of reading an existing eval-report.json",
    )

    import sys

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if not args.command:
        parser.print_help()
        return

    cmds = {
        "add": cmd_add,
        "add-json": cmd_add_json,
        "list": cmd_list,
        "search": cmd_search,
        "stats": cmd_stats,
        "delete": cmd_delete,
        "export": cmd_export,
        "import-seed": cmd_import_seed,
        "chat": cmd_chat,
        "lora": cmd_lora,
    }
    cmds[args.command](args)


def cmd_lora(args):
    """Offline LoRA fine-tuning on consensus-approved work (Upgrade Space 8).

    Builds preference pairs from the consensus state (approved=chosen,
    rejected=rejected, judged pairs only), writes the JSONL training dataset,
    and gates the model swap on the golden-set eval: a candidate whose pass
    rate regresses below --baseline or --min-pass-rate is never swapped.

    The GPU trainer itself is a follow-up adapter - this command produces the
    dataset a real trainer would consume and enforces the swap gate.
    """
    from datetime import UTC, datetime

    from nexus.application.training.lora_pipeline import LoRAPipeline, pairs_from_proposals

    root = Path(__file__).resolve().parents[3]
    state = Path(args.consensus_state) if args.consensus_state else root / "consensus_state.json"

    pairs: list = []
    if state.exists():
        from nexus.infrastructure.adapters.swarm.consensus import ConsensusProtocol

        proto = ConsensusProtocol(state)
        pairs = pairs_from_proposals(proto.list_proposals())
    else:
        print(f"[lora] no consensus state at {state} - no pairs; run scripts/consensus.py first")

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    def train(pairs, out_dir: str) -> bool:
        dataset = output / "preference_pairs.jsonl"
        dataset.write_text(
            "\n".join(
                json.dumps({"prompt": p.prompt, "chosen": p.chosen, "rejected": p.rejected}) for p in pairs
            ),
            encoding="utf-8",
        )
        print(f"[lora] dataset: {dataset} ({len(pairs)} judged pairs)")
        return True

    def evaluate(out_dir: str) -> float:
        report = output / "eval-report.json"
        if args.run_eval:
            import subprocess as _sp
            import sys as _sys

            env_root = root / "src"
            r = _sp.run(
                [_sys.executable, "-m", "nexus", "eval", "--output", str(output)],
                capture_output=True,
                text=True,
                cwd=str(root),
                env={**__import__("os").environ, "PYTHONPATH": str(env_root)},
            )
            if r.returncode == 0 and report.exists():
                return float(json.loads(report.read_text(encoding="utf-8")).get("pass_rate", 0.0))
            print(
                f"[lora] eval run failed (needs the local LLM up):\n{((r.stdout or '') + (r.stderr or ''))[-500:]}"
            )
            return 0.0
        if report.exists():
            return float(json.loads(report.read_text(encoding="utf-8")).get("pass_rate", 0.0))
        print(f"[lora] no eval report at {report} - run `nexus eval` or pass --run-eval; candidate = 0.0")
        return 0.0

    def swap(out_dir: str) -> bool:
        marker = output / "swap_approved.txt"
        marker.write_text(f"swap gate passed at {datetime.now(UTC).isoformat()}\n", encoding="utf-8")
        print("[lora] swap gate passed - point the local tier at the fine-tuned adapter (follow-up)")
        return True

    pipeline = LoRAPipeline(
        pairs_source=lambda: pairs,
        train=train,
        evaluate=evaluate,
        baseline_pass_rate=args.baseline,
        swap_model=swap,
        min_pass_rate=args.min_pass_rate,
    )
    result = pipeline.run(str(output))
    print(
        f"[lora] stopped: pairs={result.pairs} trained={result.trained} "
        f"swapped={result.swapped} blocked={result.blocked_reason or 'nothing'}"
    )
    if result.eval_gate:
        gate = result.eval_gate
        print(f"[lora] gate: baseline={gate.baseline_pass_rate:.2f} candidate={gate.candidate_pass_rate:.2f}")


if __name__ == "__main__":
    main()
