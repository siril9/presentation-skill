#!/usr/bin/env python3
"""Small, model-friendly entrypoint for presentation-skill workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from composition_grammar_catalog import quick_deck_agent_brief, route_composition_grammars  # noqa: E402
from model_adaptive_workflow import PROFILE_ALIASES, PROFILE_HELP, write_agent_brief  # noqa: E402
from deck_intake import build_deck_intake  # noqa: E402


def _run(script: str, arguments: list[str]) -> int:
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / "python_runtime.py"), str(SCRIPTS / script), *arguments],
        cwd=ROOT,
        check=False,
    )
    return int(completed.returncode)


def _write_or_print(payload: dict[str, Any], output: Path | None) -> None:
    # This handoff is consumed by a model, so avoid spending context on JSON whitespace.
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    if output is None:
        print(encoded, end="")
        return
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(encoded, encoding="utf-8")
    print(destination)


def _brief(args: argparse.Namespace) -> int:
    style = "" if args.style_preset == "auto" else args.style_preset
    route = route_composition_grammars(
        topic=args.topic,
        user_prompt=args.prompt,
        style_preset=style,
        limit=3,
        intake_answers=args.answers,
    )
    brief = quick_deck_agent_brief(
        route,
        slide_count=max(3, min(30, args.slides)),
        agent_profile=args.profile,
        intake_answers=args.answers,
        remaining_percent=args.remaining_percent,
        current_model=args.current_model,
        available_models=args.available_models,
    )
    _write_or_print(brief, args.output)
    return 0


def _init(args: argparse.Namespace) -> int:
    command = [
        "--workspace", str(args.workspace.expanduser().resolve()),
        "--title", args.title,
        "--style-preset", args.style_preset,
        "--agent-profile", args.profile,
    ]
    if args.prompt:
        command.extend(["--user-prompt", args.prompt])
    if args.audit_packet:
        command.append("--emit-start-packet")
    else:
        command.append("--skip-start-packet")
    if args.overwrite:
        command.append("--overwrite")
    result = _run("init_deck_workspace.py", command)
    if result == 0 and not args.audit_packet:
        from emit_deck_start_packet import build_packet

        workspace = args.workspace.expanduser().resolve()
        prompt = args.prompt.strip() or args.title
        # Keep the audit packet transient; lean init still needs its model handoff.
        _, markdown_path, _ = write_agent_brief(
            packet=build_packet(workspace=workspace, user_prompt=prompt, mode="agent"),
            workspace=workspace,
            user_prompt=prompt,
            requested_profile=args.profile,
        )
        print(f"Agent brief: {markdown_path}")
    return result


def _build(args: argparse.Namespace) -> int:
    command = [
        "--workspace", str(args.workspace.expanduser().resolve()),
        "--qa",
        "--overwrite",
    ]
    if args.draft:
        command.extend(
            [
                "--skip-render",
                "--fail-on-planning-warnings",
                "--fail-on-whitespace-warnings",
            ]
        )
    else:
        command.extend(
            [
                "--visual-review",
                "--fail-on-visual-review-warnings",
                "--fail-on-planning-warnings",
                "--fail-on-whitespace-warnings",
            ]
        )
    return _run("build_workspace.py", command)


def _finalize(args: argparse.Namespace) -> int:
    command = [
        "--outline", str(args.outline.expanduser().resolve()),
        "--output", str(args.output.expanduser().resolve()),
        "--style-preset", args.style_preset,
    ]
    if args.qa_dir:
        command.extend(["--qa-dir", str(args.qa_dir.expanduser().resolve())])
    if args.asset_root:
        command.extend(["--asset-root", str(args.asset_root.expanduser().resolve())])
    if args.render_cache_dir:
        command.extend(["--render-cache-dir", str(args.render_cache_dir.expanduser().resolve())])
    return _run("finalize_quick_deck.py", command)


def _doctor(_args: argparse.Namespace) -> int:
    return _run("runtime_doctor.py", [])


def _audition(args: argparse.Namespace) -> int:
    command = [
        "--outline", str(args.outline.expanduser().resolve()),
        "--outdir", str(args.outdir.expanduser().resolve()),
    ]
    if args.presets:
        command.extend(["--presets", *args.presets])
    return _run("audition_styles.py", command)


def _intake(args: argparse.Namespace) -> int:
    _write_or_print(build_deck_intake(
        args.prompt, answers=args.answers, remaining_percent=args.remaining_percent,
        current_model=args.current_model, available_models=args.available_models,
    ), args.output)
    return 0


def _answers_json(value: str) -> dict[str, str]:
    try:
        answers = json.loads(value)
        build_deck_intake("", answers=answers)
        if not isinstance(answers, dict):
            raise ValueError("answers must be a JSON object")
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return answers


def _add_intake_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--answers", type=_answers_json, help="JSON object: audience, purpose, evidence, style (text answers).")
    parser.add_argument("--remaining-percent", type=float, help="Caller-reported account usage remaining; omit when unknown. No lookup is performed.")
    parser.add_argument("--current-model", help="Caller-reported model; never changed by this command.")
    parser.add_argument("--available-models", nargs="+", help="Caller-confirmed available model names; no availability is inferred.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Route, initialize, build, and finalize reproducible editable PowerPoint decks."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Check the pinned local runtime.")
    doctor.set_defaults(handler=_doctor)

    brief = commands.add_parser("brief", help="Emit a compact model-ready quick-deck brief.")
    brief.add_argument("--topic", required=True)
    brief.add_argument("--prompt", default="")
    brief.add_argument("--slides", type=int, default=7)
    brief.add_argument("--style-preset", default="auto")
    brief.add_argument(
        "--profile",
        choices=sorted(PROFILE_ALIASES),
        default="auto",
        help=PROFILE_HELP,
    )
    brief.add_argument("--output", type=Path)
    _add_intake_options(brief)
    brief.set_defaults(handler=_brief)

    init = commands.add_parser("init", help="Create a rebuildable deck workspace.")
    init.add_argument("--workspace", type=Path, required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--prompt", default="")
    init.add_argument("--style-preset", default="auto")
    init.add_argument(
        "--profile",
        choices=sorted(PROFILE_ALIASES),
        default="auto",
        help=PROFILE_HELP,
    )
    init.add_argument("--overwrite", action="store_true")
    init.add_argument(
        "--audit-packet",
        action="store_true",
        help="Also persist the full deck-start audit/recovery packet.",
    )
    init.set_defaults(handler=_init)

    build = commands.add_parser("build", help="Build a saved workspace.")
    build.add_argument("--workspace", type=Path, required=True)
    build.add_argument("--draft", action="store_true", help="Run source/static QA without rendering.")
    build.set_defaults(handler=_build)

    final = commands.add_parser("finalize", help="Build, render, and QA a quick deck.")
    final.add_argument("--outline", type=Path, required=True)
    final.add_argument("--output", type=Path, required=True)
    final.add_argument("--style-preset", default="auto")
    final.add_argument("--qa-dir", type=Path)
    final.add_argument("--asset-root", type=Path)
    final.add_argument("--render-cache-dir", type=Path)
    final.set_defaults(handler=_finalize)

    audition = commands.add_parser("audition", help="Optionally compare styles on a content-matched slide subset.")
    audition.add_argument("--outline", type=Path, required=True)
    audition.add_argument("--outdir", type=Path, required=True)
    audition.add_argument("--presets", nargs="+", required=True)
    audition.set_defaults(handler=_audition)

    intake = commands.add_parser("intake", help="Offer optional consequential questions and caller-signaled usage choices.")
    intake.add_argument("--prompt", required=True)
    intake.add_argument("--output", type=Path)
    _add_intake_options(intake)
    intake.set_defaults(handler=_intake)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
