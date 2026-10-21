import tempfile
import unittest
from pathlib import Path

from pre_commit_complex_migrations_hook.check_enum_cdc import (
    ENUM_REBUILD_ACK,
    find_dangerous_enum_operations,
    is_enum_rebuild_acknowledged,
    main,
)


SAFE_ADD = """
from fxbase.db.utils import add_option_in_enum

def upgrade():
    add_option_in_enum(enum="PaymentProviderTypeEnum", option="finteq:card_acquirer")

def downgrade():
    pass
""" + """
ALTER TYPE "PaymentProviderTypeEnum" ADD VALUE 'finteq:card_acquirer'
"""

RENAME_VALUE = """
ALTER TYPE "PaymentProviderTypeEnum" RENAME VALUE 'old_name' TO 'new_name'
"""

DROP_NEW_TYPE = """
def downgrade():
    op.execute(text('DROP TYPE "PaymentProviderTypeEnum"'))
    delete_enum(enum="PaymentProviderTypeEnum")
"""

REBUILD = """
change_options_in_enum(
    enum="PaymentProviderTypeEnum",
    is_rename_enum=True,
    is_drop_old_enum=False,
)
op.execute(sa.text('DROP TYPE "tmp_PaymentProviderTypeEnum"'))
"""


class FindDangerousEnumOperationsTest(unittest.TestCase):
    def test_add_value_is_safe(self):
        self.assertEqual(find_dangerous_enum_operations(SAFE_ADD), [])

    def test_rename_value_is_safe(self):
        self.assertEqual(find_dangerous_enum_operations(RENAME_VALUE), [])

    def test_drop_of_a_new_type_is_safe(self):
        self.assertEqual(find_dangerous_enum_operations(DROP_NEW_TYPE), [])

    def test_rebuild_helpers_and_tmp_drop(self):
        self.assertEqual(
            find_dangerous_enum_operations(REBUILD),
            ["change_options_in_enum", 'DROP TYPE "tmp_..."'],
        )

    def test_delete_from_pg_enum(self):
        content = "delete_option_in_enum(enum='PaymentAggregatorEnum', option='finteq')\nDELETE FROM pg_enum WHERE enumlabel = 'finteq'"
        self.assertEqual(
            find_dangerous_enum_operations(content),
            ["delete_option_in_enum", "DELETE FROM pg_enum"],
        )

    def test_schema_qualified_catalog_delete_and_tmp_drop(self):
        content = """
        DELETE FROM pg_catalog.pg_enum WHERE enumlabel = 'finteq'
        DROP TYPE public.tmp_PaymentProviderTypeEnum
        DROP TYPE public."tmp_OtherEnum"
        DROP TYPE "public"."tmp_ThirdEnum"
        """
        self.assertEqual(
            find_dangerous_enum_operations(content),
            ["DELETE FROM pg_enum", 'DROP TYPE "tmp_..."'],
        )

    def test_rename_type_keeps_oid_and_is_safe(self):
        content = """
        rename_enum(old_name="PaymentIqGenderEnum", new_name="PaymentAggregatorGenderEnum")
        ALTER TYPE "PaymentProviderTypeEnum"
        RENAME TO "tmp_PaymentProviderTypeEnum"
        """
        self.assertEqual(find_dangerous_enum_operations(content), [])

    def test_drop_type_if_exists_tmp(self):
        content = 'op.execute(text(\'DROP TYPE IF EXISTS "tmp_PaymentProviderTypeEnum"\'))'
        self.assertEqual(find_dangerous_enum_operations(content), ['DROP TYPE "tmp_..."'])

    def test_acknowledgement_comment(self):
        self.assertFalse(is_enum_rebuild_acknowledged(REBUILD))
        self.assertTrue(is_enum_rebuild_acknowledged(f"{ENUM_REBUILD_ACK}\n{REBUILD}"))


class MainTest(unittest.TestCase):
    def _write(self, root: Path, relative: str, content: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_rejects_new_rebuild_and_ignores_old_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            new_file = self._write(root, "migrations/versions/0251_added_psp.py", REBUILD)
            old_file = self._write(root, "migrations/versions/0224_added_finteq_psp.py", REBUILD)
            outside = self._write(root, "core/utils.py", REBUILD)

            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "--min-revision",
                        "0251",
                        "--migrations-dir",
                        str(root / "migrations"),
                        str(old_file),
                        str(outside),
                        str(new_file),
                    ]
                )

            self.assertEqual(raised.exception.code, 1)

    def test_passes_when_rebuild_is_acknowledged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write(
                root,
                "migrations/versions/0251_remove_psp.py",
                f"{ENUM_REBUILD_ACK}\n{REBUILD}",
            )

            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "--min-revision",
                        "0251",
                        "--migrations-dir",
                        str(root / "migrations"),
                        str(path),
                    ]
                )

            self.assertEqual(raised.exception.code, 0)

    def test_passes_add_value_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self._write(root, "migrations/old_versions/0252_added_psp.py", SAFE_ADD)

            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "--min-revision",
                        "0251",
                        "--migrations-dir",
                        str(root / "migrations"),
                        str(path),
                    ]
                )

            self.assertEqual(raised.exception.code, 0)

    def test_missing_migrations_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "--min-revision",
                        "0251",
                        "--migrations-dir",
                        str(Path(tmp) / "migrations"),
                        str(Path(tmp) / "0251_added_psp.py"),
                    ]
                )

            self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
