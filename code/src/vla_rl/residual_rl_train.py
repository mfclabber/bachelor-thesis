"""Residual RL-дообучение Vision-Language-Action политик на LIBERO.

Схема (основной трек работы): базовая VLA `pi_VLA` заморожена, обучается
лёгкий SAC-агент `Delta_pi_RL`, выдающий остаточную поправку к действию:

    a_t = pi_VLA(o_t, l) + Delta_pi_RL(s_t)

Residual-наблюдение s_t — конкатенация:
    * визуального эмбеддинга из замороженного энкодера VLA (512),
    * проприоцепции (9),
    * текстового эмбеддинга инструкции (768).

Поддерживаются три режима (серия 2):
    * `residual_sac`  — замороженная VLA + SAC-поправка (основной);
    * `direct_sac`    — полная разморозка VLA под SAC (контроль, деградирует);
    * `stare_ppo`     — разморозка последних 2 слоёв + PPO.

Запуск через Hydra:
    python -m vla_rl.residual_rl_train --config-name series3_residual_all \
        model=openvla_oft suite=libero_long seed=42
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import gymnasium as gym
import numpy as np

try:  # тяжёлые зависимости подключаются лениво
    import hydra
    from omegaconf import DictConfig, OmegaConf
except ImportError:  # pragma: no cover
    hydra = None

from .stage_reward import StageReward, build_stage_reward

log = logging.getLogger(__name__)

VISUAL_DIM = 512
PROPRIO_DIM = 9
TEXT_DIM = 768
RESIDUAL_OBS_DIM = VISUAL_DIM + PROPRIO_DIM + TEXT_DIM  # 1289
SEEDS = (7, 13, 42)


@dataclass
class TrainConfig:
    model: str = "openvla_oft"
    suite: str = "libero_object"
    mode: str = "residual_sac"        # residual_sac | direct_sac | stare_ppo
    total_steps: int = 300_000
    seed: int = 42
    buffer_size: int = 1_000_000
    batch_size: int = 256
    learning_rate: float = 3e-4
    tau: float = 0.005
    residual_scale: float = 0.1       # масштаб остаточной поправки
    horizon: int = 220                # шагов на эпизод (LIBERO)


class ResidualVLAEnv(gym.Wrapper):
    """Gym-обёртка, превращающая действие агента в остаточную поправку к VLA.

    Базовая VLA остаётся замороженной и используется только для инференса.
    Агент видит residual-наблюдение s_t (1289-dim) и предсказывает Delta a_t,
    которое прибавляется к действию VLA. Вознаграждение — стадийное.
    """

    def __init__(
        self,
        base_env: gym.Env,
        vla_policy,
        instruction: str,
        stage_reward: StageReward,
        residual_scale: float = 0.1,
    ) -> None:
        super().__init__(base_env)
        self.vla = vla_policy
        self.instruction = instruction
        self.stage_reward = stage_reward
        self.residual_scale = residual_scale

        act_dim = int(np.prod(base_env.action_space.shape))
        self.action_space = gym.spaces.Box(
            low=-1.0, high=1.0, shape=(act_dim,), dtype=np.float32
        )
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(RESIDUAL_OBS_DIM,), dtype=np.float32
        )
        self._last_raw_obs = None
        self._text_embed = self.vla.encode_instruction(instruction)

    def _residual_obs(self, raw_obs) -> np.ndarray:
        """Собрать s_t = [visual(512), proprio(9), text(768)]."""
        visual = self.vla.encode_image(raw_obs["image"])      # (512,)
        proprio = np.asarray(raw_obs["proprio"], dtype=np.float32)  # (9,)
        return np.concatenate([visual, proprio, self._text_embed]).astype(np.float32)

    def reset(self, *, seed: int | None = None, options=None):
        raw_obs, info = self.env.reset(seed=seed, options=options)
        self._last_raw_obs = raw_obs
        self.stage_reward.reset()
        return self._residual_obs(raw_obs), info

    def step(self, residual_action: np.ndarray):
        # Замороженная VLA выдаёт базовое действие, агент — поправку.
        base_action = self.vla.predict(self._last_raw_obs, self.instruction)
        action = base_action + self.residual_scale * residual_action
        action = np.clip(action, self.env.action_space.low, self.env.action_space.high)

        raw_obs, _, terminated, truncated, info = self.env.step(action)
        self._last_raw_obs = raw_obs
        reward = self.stage_reward(info)
        return self._residual_obs(raw_obs), reward, terminated, truncated, info


def make_residual_env(cfg: "DictConfig | TrainConfig"):
    """Построить обёрнутую среду LIBERO с замороженной VLA.

    Импорты бенчмарка и загрузчиков VLA ленивые, чтобы модуль импортировался
    без установленных LIBERO/весов (например, для юнит-тестов stage_reward).
    """
    from .evaluate_vla import load_vla, make_libero_env  # ленивый импорт

    vla = load_vla(cfg.model, freeze=cfg.mode != "direct_sac")
    base_env, instruction = make_libero_env(cfg.suite, seed=cfg.seed)
    stage_reward = build_stage_reward(getattr(cfg, "stage_reward", None))
    env = ResidualVLAEnv(
        base_env,
        vla_policy=vla,
        instruction=instruction,
        stage_reward=stage_reward,
        residual_scale=getattr(cfg, "residual_scale", 0.1),
    )
    return gym.wrappers.TimeLimit(env, max_episode_steps=cfg.horizon)


def build_agent(env, cfg: "DictConfig | TrainConfig"):
    """Создать SAC или PPO агент Stable-Baselines3 согласно режиму."""
    policy_kwargs = dict(net_arch=[256, 256])
    if cfg.mode == "stare_ppo":
        from stable_baselines3 import PPO

        policy_kwargs["activation_fn"] = __import__("torch").nn.Tanh
        return PPO(
            "MlpPolicy",
            env,
            learning_rate=cfg.learning_rate,
            n_steps=2048,
            batch_size=2048,
            n_epochs=10,
            policy_kwargs=policy_kwargs,
            seed=cfg.seed,
            verbose=1,
        )

    from stable_baselines3 import SAC

    return SAC(
        "MlpPolicy",
        env,
        learning_rate=cfg.learning_rate,
        buffer_size=cfg.buffer_size,
        batch_size=cfg.batch_size,
        tau=cfg.tau,
        policy_kwargs=policy_kwargs,
        seed=cfg.seed,
        verbose=1,
    )


def train(cfg: "DictConfig | TrainConfig"):
    """Полный цикл residual RL-дообучения одной модели на одном наборе."""
    np.random.seed(cfg.seed)
    log.info("Residual RL: model=%s suite=%s mode=%s seed=%s",
             cfg.model, cfg.suite, cfg.mode, cfg.seed)

    env = make_residual_env(cfg)
    agent = build_agent(env, cfg)
    agent.learn(total_timesteps=cfg.total_steps, progress_bar=True)

    out = f"results/libero/{cfg.model}_{cfg.suite}_{cfg.mode}_seed{cfg.seed}"
    agent.save(out)
    log.info("Saved agent -> %s.zip", out)
    return agent


if hydra is not None:

    @hydra.main(version_base=None, config_path="../../configs", config_name="series3_residual_all")
    def main(cfg: "DictConfig") -> None:
        log.info("\n%s", OmegaConf.to_yaml(cfg))
        train(cfg)


if __name__ == "__main__":  # pragma: no cover
    if hydra is None:
        raise SystemExit("hydra-core не установлен: pip install -r requirements.txt")
    main()
