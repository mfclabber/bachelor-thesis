#!/usr/bin/env bash
# Серия 4: абляция компонентов residual RL на OpenVLA-OFT (LIBERO-Long).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"

# Полная система
python -m vla_rl.residual_rl_train --config-name series4_ablation \
    ablation=full mode=residual_sac

# Без стадийного вознаграждения (sparse reward)
python -m vla_rl.residual_rl_train --config-name series4_ablation \
    ablation=no_stage 'stage_reward.weights=[0,0,0,0]'

# Разморозка VLA (direct SAC)
python -m vla_rl.residual_rl_train --config-name series4_ablation \
    ablation=unfrozen mode=direct_sac

# PPO вместо SAC
python -m vla_rl.residual_rl_train --config-name series4_ablation \
    ablation=ppo mode=stare_ppo

# Урезанный бюджет
python -m vla_rl.residual_rl_train --config-name series4_ablation \
    ablation=budget_150k total_steps=150000

echo "Серия 4 завершена."
