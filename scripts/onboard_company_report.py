#!/usr/bin/env python3
"""CLI for guarded company audit-report onboarding."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.company_report_onboarding import (
    BLOCKED,
    EXIT_CODES,
    PipelineContext,
    preview_onboarding,
    promote_onboarding,
    stage_onboarding,
    validate_onboarding,
)


def print_result(result: dict) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def context_from_args(args: argparse.Namespace) -> PipelineContext:
    return PipelineContext(
        repo_root=args.repo_root.resolve(),
        artifact_root=args.artifact_root,
        base_ref=args.base_ref or None,
    )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts/company-report-onboarding"))
    parser.add_argument("--base-ref", default="origin/main")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate, stage, preview, and promote company audit-report JSON candidates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    add_common_args(validate_parser)

    stage_parser = subparsers.add_parser("stage")
    add_common_args(stage_parser)

    preview_parser = subparsers.add_parser("preview")
    add_common_args(preview_parser)

    promote_parser = subparsers.add_parser("promote")
    add_common_args(promote_parser)
    promote_parser.add_argument("--expected-preview-sha", required=True)
    promote_parser.add_argument("--acknowledge-source-review", action="store_true")
    promote_parser.add_argument("--acknowledge-public-change", action="store_true")
    promote_parser.add_argument("--write", action="store_true")

    args = parser.parse_args()
    try:
        context = context_from_args(args)
        manifest_path = args.manifest
        if not manifest_path.is_absolute():
            manifest_path = context.repo_root / manifest_path
        if args.command == "validate":
            result = validate_onboarding(manifest_path, context)
        elif args.command == "stage":
            result = stage_onboarding(manifest_path, context)
        elif args.command == "preview":
            result = preview_onboarding(manifest_path, context)
        elif args.command == "promote":
            result = promote_onboarding(
                manifest_path,
                context,
                expected_preview_sha=args.expected_preview_sha,
                source_ack=args.acknowledge_source_review,
                public_ack=args.acknowledge_public_change,
                write=args.write,
            )
        else:
            raise ValueError(f"unsupported command: {args.command}")
    except Exception as error:  # noqa: BLE001
        print_result({"verdict": BLOCKED, "error": str(error)})
        return EXIT_CODES["CLI_ERROR"]
    print_result(result)
    return EXIT_CODES.get(result.get("verdict"), EXIT_CODES["CLI_ERROR"])


if __name__ == "__main__":
    raise SystemExit(main())
