#!/usr/bin/env bash
# Серия 5: VLM-кодогенерация функции награды (Qwen2.5-VL) на MetaWorld.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"

python -m vla_rl.vlm_reward_gen

echo "Серия 5 завершена. Сгенерированные награды: results/metaworld/reward_code/"
