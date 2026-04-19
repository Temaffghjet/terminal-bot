#!/usr/bin/env bash
cd "$(dirname "$0")"
export PYTHONPATH=.
exec .venv/bin/python -m backend.main
