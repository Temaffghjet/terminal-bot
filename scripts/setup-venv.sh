#!/usr/bin/env bash
# Виртуальное окружение в корне репозитория (обход PEP 668 на Ubuntu/macOS).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
"$ROOT/.venv/bin/pip" install --upgrade pip
"$ROOT/.venv/bin/pip" install -r backend/pip-requirements.txt
echo "Готово. Запуск бота:"
echo "  source .venv/bin/activate   # или: .venv/bin/python -m backend.main"
echo "  python -m backend.main"
