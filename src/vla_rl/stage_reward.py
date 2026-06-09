"""Стадийная функция вознаграждения для манипуляционных задач LIBERO.

Четыре фазы манипуляции с равными весами w_k = 0.25 и бонусом beta за успех
эпизода (см. уравнение (eq:stage_reward) в работе):

    R_stage(s_t) = sum_k w_k * 1[phase_k выполнена] + beta * S(T_i)

    1. Reach     — расстояние захвата до объекта < 0.05 м;
    2. Grasp     — контакт с объектом и закрытие захвата;
    3. Transport — объект перемещён, расстояние до цели < 0.15 м;
    4. Place     — успех эпизода S(T_i) = 1, бонус beta = 1.0.

Детекция фаз — по проприоцептивным сигналам ROBOSUITE (положение захвата,
контакт, расстояние до цели).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np


@dataclass
class StageRewardConfig:
    """Пороги и веса стадийного вознаграждения."""

    reach_threshold: float = 0.05      # м, фаза Reach
    transport_threshold: float = 0.15  # м, фаза Transport
    weights: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)
    success_bonus: float = 1.0         # beta
    monotonic: bool = True             # фазы засчитываются только по порядку


PHASES = ("reach", "grasp", "transport", "place")


class StageReward:
    """Вычисляет стадийное вознаграждение и отслеживает достигнутые фазы.

    Экземпляр хранит состояние одного эпизода (множество уже достигнутых фаз),
    поэтому при `monotonic=True` награда за фазу выдаётся ровно один раз —
    в момент её первого достижения. Это превращает плотную награду в
    «лестницу» прогресса и снимает проблему разреженного сигнала.
    """

    def __init__(self, config: StageRewardConfig | None = None) -> None:
        self.cfg = config or StageRewardConfig()
        self.reset()

    def reset(self) -> None:
        """Сбросить состояние в начале нового эпизода."""
        self._achieved: set[str] = set()

    # ------------------------------------------------------------------ #
    # Детекторы фаз (по проприоцепции ROBOSUITE)
    # ------------------------------------------------------------------ #
    def _reach_done(self, info: Mapping[str, np.ndarray]) -> bool:
        d = float(np.linalg.norm(info["gripper_pos"] - info["object_pos"]))
        return d < self.cfg.reach_threshold

    def _grasp_done(self, info: Mapping[str, np.ndarray]) -> bool:
        return bool(info.get("object_in_contact", False)) and bool(
            info.get("gripper_closed", False)
        )

    def _transport_done(self, info: Mapping[str, np.ndarray]) -> bool:
        if not (info.get("object_in_contact", False)):
            return False
        d = float(np.linalg.norm(info["object_pos"] - info["target_pos"]))
        return d < self.cfg.transport_threshold

    def _place_done(self, info: Mapping[str, np.ndarray]) -> bool:
        return bool(info.get("success", False))

    def _phase_done(self, phase: str, info: Mapping[str, np.ndarray]) -> bool:
        return {
            "reach": self._reach_done,
            "grasp": self._grasp_done,
            "transport": self._transport_done,
            "place": self._place_done,
        }[phase](info)

    # ------------------------------------------------------------------ #
    # Основной вызов
    # ------------------------------------------------------------------ #
    def __call__(self, info: Mapping[str, np.ndarray]) -> float:
        """Вернуть приращение награды за текущий шаг.

        Args:
            info: словарь проприоцептивных сигналов среды с ключами
                `gripper_pos`, `object_pos`, `target_pos` (np.ndarray, 3D),
                `object_in_contact`, `gripper_closed`, `success` (bool).

        Returns:
            Скалярное вознаграждение r_t >= 0.
        """
        reward = 0.0
        for k, phase in enumerate(PHASES):
            if phase in self._achieved:
                continue
            # При monotonic=True следующая фаза недоступна, пока не достигнута
            # предыдущая — это исключает «перепрыгивание» этапов.
            if self.cfg.monotonic and k > 0 and PHASES[k - 1] not in self._achieved:
                break
            if self._phase_done(phase, info):
                self._achieved.add(phase)
                reward += self.cfg.weights[k]
                if phase == "place":
                    reward += self.cfg.success_bonus
        return reward

    @property
    def achieved_phases(self) -> tuple[str, ...]:
        return tuple(p for p in PHASES if p in self._achieved)


def build_stage_reward(cfg: Mapping | None = None) -> StageReward:
    """Фабрика для создания StageReward из Hydra/словаря конфигурации."""
    if cfg is None:
        return StageReward()
    config = StageRewardConfig(
        reach_threshold=cfg.get("reach_threshold", 0.05),
        transport_threshold=cfg.get("transport_threshold", 0.15),
        weights=tuple(cfg.get("weights", (0.25, 0.25, 0.25, 0.25))),
        success_bonus=cfg.get("success_bonus", 1.0),
        monotonic=cfg.get("monotonic", True),
    )
    return StageReward(config)
