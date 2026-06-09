#!/usr/bin/env bash
# Серия 3: residual SAC + стадийная награда для всех девяти VLA на 4 наборах.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"

python -m vla_rl.residual_rl_train --config-name series3_residual_all -m \
    model=openvla_oft,univla,pi0,cogact,smolvla,pi0_fast,spatialvla,octo_small,rt1x \
    suite=libero_object,libero_spatial,libero_goal,libero_long \
    seed=7,13,42

echo "Серия 3 завершена."
