#!/usr/bin/env bash
# Серия 1: baseline девяти VLA на LIBERO (без RL).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"

python -m vla_rl.evaluate_vla

echo "Серия 1 завершена. Результаты: results/libero/baseline_sr.csv"
