import re
import shutil
import sys
from argparse import ArgumentParser
from pathlib import Path


COMMIT_REQUIRED_COMMENT = "# migration tested on prod database"
MIGRATION_DURATION_COMMENT = "# migration_duration:"
MIGRATION_DURATION_PLACEHOLDER = f"{MIGRATION_DURATION_COMMENT} -"

DOWNTIME_POSTFIX = "_downtime"


def is_table_mentioned(table: str, content: str) -> bool:
    table_escaped = re.escape(table)
    re_conditions = (
        rf'(?<!\w)(["\'`]){table}\1|\b{table}\b',  # single word
        rf'(?<!\w)(["\'`]?){table_escaped}_\d+\1\b',  # table + partition
        rf'f["\'{{]{table_escaped}_{{[^}}]+}}',  # f-string
        rf'{table_escaped}_["\']\s*\+\s*',  # concatenation
        rf"{table_escaped}_[^}}]*}}",  # string formatting .format(...)
    )

    for regex in re_conditions:
        if re.search(regex, content, re.IGNORECASE):
            return True

    return False


def get_revision_from_filename(filename: str) -> str | None:
    match = re.match(r"(\d{4})_", filename)
    return match.group(1) if match else None


def get_duration_value(content: str) -> int:
    match = re.search(rf"{MIGRATION_DURATION_COMMENT}\s*([0-9]+)\b", content, re.IGNORECASE)
    return int(match.group(1).strip())


def handle_duration_value(duration_value: int, file_path: str) -> None:
    if duration_value > 1:
        file_path = Path(file_path)

        if DOWNTIME_POSTFIX not in file_path.name:
            new_path = file_path.with_name(file_path.stem + DOWNTIME_POSTFIX + file_path.suffix)
            shutil.move(str(file_path), str(new_path))
            print(f"Migration took more than 1 minute, file moved to {new_path} with postfix {DOWNTIME_POSTFIX}")


def add_duration_placeholder(file_path: str, content: str) -> None:
    match = re.search(r'"""\s*$', content, re.MULTILINE)
    insert_pos = match.end() if match else len(content)
    new_content = content[:insert_pos] + "\n\n" + MIGRATION_DURATION_PLACEHOLDER + "\n" + content[insert_pos:]

    try:
        Path(file_path).write_text(new_content, encoding="utf-8")
        print(f"Added placeholder '{MIGRATION_DURATION_PLACEHOLDER}' to {Path(file_path).name}")
    except Exception as e:
        print(f"Failed to write file {file_path}: {e}", file=sys.stderr)


def validate_complex_migration(content: str, mentioned_tables: list, file_path: str) -> bool:
    validated = True

    if COMMIT_REQUIRED_COMMENT not in content:
        print(
            f"Error in {file_path}: Migration that affects complex table(s) ({', '.join(mentioned_tables)}) "
            f"must be tested on prod database and contain comment '{COMMIT_REQUIRED_COMMENT}'.",
            file=sys.stderr,
        )
        validated = False

    duration_regex = rf"{MIGRATION_DURATION_COMMENT}\s*\d+\s*"

    if not re.search(duration_regex, content, re.IGNORECASE):
        error_message = (
            f"Error in {file_path}: Complex migration must contain comment with migration duration:\n"
            f"'{MIGRATION_DURATION_PLACEHOLDER}' replace '-' with the migration duration value in minutes (integer)"
            f"received after testing.\n"
        )
        placeholder_regex = rf"{MIGRATION_DURATION_COMMENT}\s*-\s*"

        if not re.search(placeholder_regex, content, re.IGNORECASE):
            print(
                f"{error_message}\n" f"The line will be added automatically in file after hook.\n",
                file=sys.stderr,
            )
            add_duration_placeholder(file_path, content)
            return False

        print(
            error_message,
            file=sys.stderr,
        )
        validated = False

    return validated


def main():
    parser = ArgumentParser()
    parser.add_argument("--tables", nargs="+")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--min-revision", required=True)
    parser.add_argument("--migrations-dir", required=True)
    args = parser.parse_args()

    migration_dirs = (args.migrations_dir + "/versions", args.migrations_dir + "/old_versions")
    if not any((Path(migration_dir)).exists() for migration_dir in migration_dirs):
        print(f"Not found versions and old_versions dirs in {args.migrations_dir}", file=sys.stderr)
        sys.exit(1)

    has_errors = False
    for file_path in args.files:
        path = Path(file_path)
        if path.suffix != ".py" or not any(path.is_relative_to(Path(dir_path)) for dir_path in migration_dirs):
            continue

        if (rev_number := get_revision_from_filename(path.name)) and rev_number < args.min_revision:
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            sys.exit(1)

        if mentioned_tables := [table for table in args.tables if is_table_mentioned(table, content)]:
            has_errors = not validate_complex_migration(content, mentioned_tables, file_path)
            if not has_errors:
                handle_duration_value(duration_value=get_duration_value(content), file_path=file_path)

    if has_errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
