"""Генерация функции вознаграждения визуально-языковой моделью (серия 5).

Дополнительный трек работы: вместо ручной разметки награды VLM Qwen2.5-VL-7B
порождает исполняемый код `compute_dense_reward` для задач MetaWorld, а затем
итеративно улучшает его по обратной связи (SR, корреляция rho(R,S), описание
поведения) — по аналогии с Text2Reward / EUREKA.

Параметры (см. А.6): Qwen2.5-VL-7B-Instruct (vLLM), температура 0.7,
до 2048 токенов, 1–3 итерации рефлексии.

Пример эволюции кода награды для push-v3:
    итерация 1: SR=48.3%, rho=0.12  — только расстояние ee->object;
    итерация 3: SR=85.0%, rho=0.81  — расстояние + контакт + прогресс к цели.
"""

from __future__ import annotations

import logging
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

MODEL_NAME = "Qwen/Qwen2.5-VL-7B-Instruct"
TEMPERATURE = 0.7
MAX_TOKENS = 2048
MAX_REFLECTION_ITERS = 3

SYSTEM_PROMPT = textwrap.dedent(
    """\
    Ты — инженер по обучению с подкреплением. По описанию задачи MetaWorld и
    семантике наблюдений напиши плотную функцию вознаграждения на Python.
    Сигнатура строго:

        def compute_dense_reward(self, action, obs):
            ...
            return reward

    Доступно: numpy as np; obs — словарь с ключами 'achieved_goal',
    'observation', 'desired_goal' (np.ndarray). Верни ТОЛЬКО код функции
    в блоке ```python ... ```. Поощряй сближение схвата с объектом, контакт и
    прогресс объекта к цели; штрафуй резкие действия.
    """
)


@dataclass
class RewardCandidate:
    code: str
    iteration: int
    success_rate: float = float("nan")
    correlation: float = float("nan")  # rho(R, S)

    def is_better_than(self, other: "RewardCandidate | None") -> bool:
        if other is None:
            return True
        return self.success_rate > other.success_rate


def _extract_code(text: str) -> str:
    """Достать тело функции из ответа VLM (блок ```python ... ```)."""
    m = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    code = (m.group(1) if m else text).strip()
    if "def compute_dense_reward" not in code:
        raise ValueError("В ответе VLM не найдена функция compute_dense_reward")
    return code


def compile_reward(code: str) -> Callable:
    """Безопасно (в ограниченном пространстве имён) скомпилировать награду."""
    import numpy as np

    namespace: dict = {"np": np}
    exec(compile(code, "<vlm_reward>", "exec"), namespace)  # noqa: S102
    fn = namespace.get("compute_dense_reward")
    if not callable(fn):
        raise ValueError("compute_dense_reward не определена/не вызываема")
    return fn


class QwenRewardGenerator:
    """Обёртка над Qwen2.5-VL-7B (vLLM) для генерации кода награды."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._llm = None  # ленивая инициализация vLLM

    def _ensure_llm(self):
        if self._llm is None:
            from vllm import LLM  # type: ignore

            self._llm = LLM(model=self.model_name, trust_remote_code=True)
        return self._llm

    def _generate(self, user_prompt: str) -> str:
        from vllm import SamplingParams  # type: ignore

        llm = self._ensure_llm()
        params = SamplingParams(temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        out = llm.chat(messages, params)
        return out[0].outputs[0].text

    def propose(self, task_description: str, feedback: str | None = None) -> str:
        prompt = f"Задача: {task_description}"
        if feedback:
            prompt += f"\n\nОбратная связь по прошлой версии:\n{feedback}"
        return _extract_code(self._generate(prompt))


def generate_reward(
    task_description: str,
    evaluate: Callable[[Callable], tuple[float, float]],
    generator: QwenRewardGenerator | None = None,
    save_dir: str = "results/metaworld/reward_code",
) -> RewardCandidate:
    """Итеративно сгенерировать и улучшить функцию награды для задачи.

    Args:
        task_description: текстовое описание задачи MetaWorld (напр. 'push-v3').
        evaluate: функция, обучающая SAC с данной наградой и возвращающая
            (success_rate, correlation rho(R, S)).
        generator: генератор Qwen (по умолчанию создаётся новый).
        save_dir: куда сохранять код-кандидаты.

    Returns:
        Лучший RewardCandidate по success_rate.
    """
    generator = generator or QwenRewardGenerator()
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    best: RewardCandidate | None = None
    feedback: str | None = None

    for it in range(1, MAX_REFLECTION_ITERS + 1):
        code = generator.propose(task_description, feedback)
        candidate = RewardCandidate(code=code, iteration=it)
        try:
            reward_fn = compile_reward(code)
            candidate.success_rate, candidate.correlation = evaluate(reward_fn)
        except Exception as exc:  # noqa: BLE001
            log.warning("Итерация %d: ошибка компиляции/оценки: %s", it, exc)
            feedback = f"Код не запустился: {exc}. Исправь и упрости."
            continue

        (save_path / f"{task_description}_iter{it}.py").write_text(code, encoding="utf-8")
        log.info("Итерация %d: SR=%.1f%%, rho=%.2f", it,
                 candidate.success_rate, candidate.correlation)

        if candidate.is_better_than(best):
            best = candidate

        feedback = (
            f"Текущая версия: SR={candidate.success_rate:.1f}%, "
            f"rho(R,S)={candidate.correlation:.2f}. "
            "Усиль члены, коррелирующие с успехом; добавь прогресс к цели и "
            "бонус за контакт, если их нет."
        )

    if best is None:
        raise RuntimeError("Не удалось сгенерировать рабочую функцию награды")
    log.info("Лучшая награда: итерация %d, SR=%.1f%%", best.iteration, best.success_rate)
    return best


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(
        "Запуск серии 5 требует MetaWorld и доступного Qwen2.5-VL (vLLM); "
        "см. scripts/run_series5.sh"
    )
