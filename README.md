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