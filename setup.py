from setuptools import setup, find_packages

name = 'pre_commit_complex_migrations_hook'
version = '1.0.0'
description = 'pre-commit hook for validating complexity of alembic migrations'

# Package setup
setup(
    name=name,
    version=version,
    description=description,
    packages=find_packages(),
)
