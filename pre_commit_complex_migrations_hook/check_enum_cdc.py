import re
import sys
from argparse import ArgumentParser
from pathlib import Path

from pre_commit_complex_migrations_hook.check_complex_migrations import get_revision_from_filename


ENUM_REBUILD_ACK = "# debezium: enum type rebuild, replication slot must be recreated"

# Quoted or bare SQL identifier, so public.tmp_ and "public"."tmp_" both match.
_SQL_IDENT = r"""(?:"[^"]*"|[A-Za-z_][\w]*)"""

_DANGEROUS_OPERATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("change_options_in_enum", re.compile(r"\bchange_options_in_enum\s*\(")),
    ("delete_option_in_enum", re.compile(r"\bdelete_option_in_enum\s*\(")),
    (
        "DELETE FROM pg_enum",
        re.compile(
            rf"""\bDELETE\s+FROM\s+(?:{_SQL_IDENT}\s*\.\s*)?"?pg_enum\b""",
            re.IGNORECASE,
        ),
    ),
    (
        'DROP TYPE "tmp_..."',
        re.compile(
            rf"""\bDROP\s+TYPE\s+(?:IF\s+EXISTS\s+)?(?:{_SQL_IDENT}\s*\.\s*)?["']?tmp_""",
            re.IGNORECASE,
        ),
    ),
)


def find_dangerous_enum_operations(content: str) -> list[str]:
    return [label for label, pattern in _DANGEROUS_OPERATIONS if pattern.search(content)]


def is_enum_rebuild_acknowledged(content: str) -> bool:
    return ENUM_REBUILD_ACK in content


def report_enum_cdc_violation(file_path: str, operations: list[str]) -> None:
    found = ", ".join(operations)
    print(
        f"Error in {file_path}: migration rebuilds a PostgreSQL enum ({found}).\n"
        "Dropping the type or deleting its labels removes an OID Debezium is already streaming and breaks CDC.\n"
        "Add a new enum value with add_option_in_enum (ALTER TYPE ... ADD VALUE), "
        "and leave downgrade empty.\n"
        "If the type really must be rebuilt, add this comment and plan a replication slot recreate:\n"
        f"{ENUM_REBUILD_ACK}",
        file=sys.stderr,
    )


def _migration_dirs(migrations_dir: str) -> tuple[Path, Path]:
    root = Path(migrations_dir)
    return root / "versions", root / "old_versions"


def main(argv: list[str] | None = None) -> None:
    parser = ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--min-revision", required=True)
    parser.add_argument("--migrations-dir", required=True)
    args = parser.parse_args(argv)

    migration_dirs = _migration_dirs(args.migrations_dir)
    if not any(path.exists() for path in migration_dirs):
        print(f"Not found versions and old_versions dirs in {args.migrations_dir}", file=sys.stderr)
        sys.exit(1)

    has_errors = False
    for file_path in args.files:
        path = Path(file_path)
        if path.suffix != ".py" or not any(path.is_relative_to(directory) for directory in migration_dirs):
            continue

        if (rev_number := get_revision_from_filename(path.name)) and rev_number < args.min_revision:
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            sys.exit(1)

        operations = find_dangerous_enum_operations(content)
        if operations and not is_enum_rebuild_acknowledged(content):
            report_enum_cdc_violation(file_path, operations)
            has_errors = True

    if has_errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
