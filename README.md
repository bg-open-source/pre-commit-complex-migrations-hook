## To create a package:
1. activate poetry shell
2. delete files pyproject.toml and poetry.lock
3. commit
4. create new tag & commit tag
5. `python setup.py build`
6. `python setup.py sdist` (создаст файл pre_commit_merge_content_hooks-0.0.0.tar.gz)
7. `python setup.py bdist_wheel` (создаст файл pre_commit_merge_content_hooks-0.0.0-py3-none-any.whl)

___


## Complex migration hook

The hook is used to check new migration files for the presence of large tables.

Migrations that include large tables must be tested on a copy of the production database and must contain the comments:
- `# migration tested on prod database`
- `# migration_duration: {n}` where _n_ is the migration execution time in minutes (integer only).

A **downtime** migration is a migration whose execution time exceeds 1 minute.
Such migrations will be marked with the "__downtime_" postfix.

___

Hook args:
- `--tables` - names of big tables separated by commas. These tables will be validated by the hook.
- `--min-revision` - min revision number of migration after which the hook will perform the validation.
- `--migrations-dir` - path to migrations directory. _**Do not include "versions" and "old_versions" in path**_

___


## Enum CDC hook

`check-enum-cdc` rejects a new migration that rebuilds a PostgreSQL enum. Creating a new type and dropping the old one removes an OID Debezium is already streaming, and the connector stops until the replication slot is recreated. `ALTER TYPE ... RENAME TO` keeps the OID and is allowed.

The hook fails when a staged file under `migrations/versions` or `migrations/old_versions` contains any of:

- `change_options_in_enum(`
- `delete_option_in_enum(`
- `DELETE FROM pg_enum`, including `pg_catalog.pg_enum`
- `DROP TYPE` of a `tmp_` enum, including a schema-qualified name such as `public.tmp_` or `public."tmp_..."`

`add_option_in_enum`, `ALTER TYPE ... ADD VALUE`, `ALTER TYPE ... RENAME TO`, `ALTER TYPE ... RENAME VALUE`, and `DROP TYPE` of a non-`tmp_` enum are allowed. Set `downgrade()` to `pass` when the migration only adds a value.

Files whose revision in the filename is below `--min-revision` are skipped. A migration that really must rebuild a type has to contain this comment:

```python
# debezium: enum type rebuild, replication slot must be recreated
```

Hook args:

- `--min-revision` - same meaning as for the complex-migration hook.
- `--migrations-dir` - path to the migrations directory, without `versions` or `old_versions`.

```yaml
- id: check-enum-cdc
  args: ['--min-revision', '0251', '--migrations-dir', 'migrations']
```