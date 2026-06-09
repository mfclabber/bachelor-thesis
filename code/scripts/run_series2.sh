#!/usr/bin/env bash
# Серия 2: сравнение схем RL-дообучения на OpenVLA-OFT.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"

python -m vla_rl.residual_rl_train --config-name series2_rl_methods -m \
    mode=residual_sac,direct_sac,stare_ppo \
    seed=7,13,42

echo "Серия 2 завершена."
