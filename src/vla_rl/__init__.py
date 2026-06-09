"""RL для дообучения Vision-Language-Action моделей.

Модули прототипа ВКР:
    evaluate_vla        — инференс девяти VLA-политик на LIBERO (серия 1);
    residual_rl_train   — residual RL-дообучение (SAC/PPO, серии 2–4);
    stage_reward        — стадийная функция вознаграждения (4 фазы);
    vlm_reward_gen      — VLM-кодогенерация награды (Qwen2.5-VL, серия 5).
"""

__version__ = "1.0.0"

__all__ = [
    "evaluate_vla",
    "residual_rl_train",
    "stage_reward",
    "vlm_reward_gen",
]
