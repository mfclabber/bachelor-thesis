"""Инференс девяти VLA-политик на бенчмарке LIBERO (серия 1).

Протокол оценки (см. раздел subsec:libero и А.3):
    * 4 набора LIBERO: Object, Spatial, Goal, Long (по 10 задач);
    * 10 эпизодов/задачу (100 эпизодов/набор);
    * 3 seed среды (7, 13, 42);
    * разрешение 224x224, greedy-инференс;
    * метрика — Success Rate (%), 95% ДИ по 3 seed (t-распределение, df=2).

Модуль также содержит загрузчики VLA-весов и фабрику сред LIBERO,
используемые residual_rl_train. Реальные веса и LIBERO/ROBOSUITE должны быть
установлены отдельно (см. requirements.txt).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

log = logging.getLogger(__name__)

LIBERO_SUITES = ("libero_object", "libero_spatial", "libero_goal", "libero_long")
SEEDS = (7, 13, 42)
EPISODES_PER_TASK = 10
TASKS_PER_SUITE = 10
RESOLUTION = 224

# Девять оцениваемых VLA: имя -> (HF-чекпоинт / описание, число параметров)
VLA_REGISTRY: dict[str, dict] = {
    "openvla_oft": {"ckpt": "moojink/openvla-7b-oft-finetuned-libero-{suite}", "params": "7B"},
    "univla":      {"ckpt": "univla/univla-7b", "params": "7B"},
    "pi0":         {"ckpt": "openpi/pi0-3b", "params": "3B"},
    "cogact":      {"ckpt": "cogact/cogact-8b", "params": "8B"},
    "smolvla":     {"ckpt": "lerobot/smolvla-2.2b", "params": "2.2B"},
    "pi0_fast":    {"ckpt": "openpi/pi0-fast-3b", "params": "3B"},
    "spatialvla":  {"ckpt": "spatialvla/spatialvla-4b", "params": "4B"},
    "octo_small":  {"ckpt": "octo/octo-small-1.5", "params": "120M"},
    "rt1x":        {"ckpt": "rt1x/rt-1-x-sim-adapter", "params": "35M"},
}


# --------------------------------------------------------------------------- #
# Загрузка VLA и сред (ленивые внешние зависимости)
# --------------------------------------------------------------------------- #
class VLAPolicy:
    """Тонкая обёртка над предобученной VLA с замороженными весами.

    Реальная загрузка весов выполняется в `load_vla`; здесь определён единый
    интерфейс, который ожидают `evaluate_suite` и `ResidualVLAEnv`:
        encode_image(img)            -> np.ndarray (512,)
        encode_instruction(text)     -> np.ndarray (768,)
        predict(obs, instruction)    -> np.ndarray (action,)
    """

    def __init__(self, name: str, model, frozen: bool = True) -> None:
        self.name = name
        self.model = model
        self.frozen = frozen

    def encode_image(self, image: np.ndarray) -> np.ndarray:
        return self.model.vision_encoder(image)

    def encode_instruction(self, instruction: str) -> np.ndarray:
        return self.model.text_encoder(instruction)

    def predict(self, obs, instruction: str) -> np.ndarray:
        return self.model.act(obs, instruction)


def load_vla(name: str, freeze: bool = True) -> VLAPolicy:
    """Загрузить VLA по имени и (опционально) заморозить веса.

    Загрузка конкретного backend (transformers / openpi / octo) вынесена в
    отдельные адаптеры. Octo-Small дообучается LoRA (rank=16), RT-1-X
    использует симуляционный адаптер 7-DoF -> токены RT-1.
    """
    if name not in VLA_REGISTRY:
        raise KeyError(f"Неизвестная VLA: {name}. Доступно: {list(VLA_REGISTRY)}")
    model = _build_backend(name, VLA_REGISTRY[name]["ckpt"], freeze=freeze)
    log.info("Загружена VLA %s (%s, frozen=%s)", name, VLA_REGISTRY[name]["params"], freeze)
    return VLAPolicy(name, model, frozen=freeze)


def _build_backend(name: str, ckpt: str, freeze: bool):
    """Загрузить конкретный VLA-backend и (опц.) заморозить параметры.

    Разные семейства моделей грузятся разными библиотеками:
      * openvla_oft / univla / cogact / smolvla / spatialvla — transformers;
      * pi0 / pi0_fast — openpi;
      * octo_small — octo (+ LoRA rank=16 для переноса на LIBERO);
      * rt1x — симуляционный адаптер 7-DoF -> дискретные токены RT-1.
    Здесь — единая точка входа; конкретные ветки реализуются по мере
    подключения весов. Возвращаемый объект обязан реализовать
    vision_encoder / text_encoder / act.
    """
    raise NotImplementedError(
        f"Backend для '{name}' ({ckpt}) подключается отдельно — нужны веса VLA "
        "и установленный бенчмарк LIBERO (см. requirements.txt)."
    )


def make_libero_env(suite: str, seed: int = 42):
    """Создать среду LIBERO и вернуть (env, instruction)."""
    from libero.libero import benchmark, get_libero_path  # type: ignore
    from libero.libero.envs import OffScreenRenderEnv      # type: ignore

    task_suite = benchmark.get_benchmark_dict()[suite]()
    task = task_suite.get_task(0)
    bddl = task_suite.get_task_bddl_file_path(0)
    env = OffScreenRenderEnv(bddl_file_name=bddl, camera_heights=RESOLUTION,
                             camera_widths=RESOLUTION)
    env.seed(seed)
    return env, task.language


# --------------------------------------------------------------------------- #
# Оценка
# --------------------------------------------------------------------------- #
@dataclass
class SuiteResult:
    model: str
    suite: str
    sr_per_seed: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return float(np.mean(self.sr_per_seed))

    @property
    def ci95(self) -> float:
        """Полуширина 95% ДИ по t-распределению (df = n-1)."""
        n = len(self.sr_per_seed)
        if n < 2:
            return 0.0
        s = float(np.std(self.sr_per_seed, ddof=1))
        t = stats.t.ppf(0.975, df=n - 1)  # для n=3: t ≈ 4.303
        return t * s / np.sqrt(n)


def run_episode(vla: VLAPolicy, env, instruction: str, max_steps: int = 220) -> bool:
    obs, _ = env.reset()
    for _ in range(max_steps):
        action = vla.predict(obs, instruction)
        obs, _, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            return bool(info.get("success", False))
    return False


def evaluate_suite(vla: VLAPolicy, suite: str) -> SuiteResult:
    """Оценить одну VLA на одном наборе LIBERO по протоколу серии 1."""
    result = SuiteResult(model=vla.name, suite=suite)
    for seed in SEEDS:
        env, instruction = make_libero_env(suite, seed=seed)
        successes = 0
        total = TASKS_PER_SUITE * EPISODES_PER_TASK
        for _task in range(TASKS_PER_SUITE):
            for _ep in range(EPISODES_PER_TASK):
                successes += int(run_episode(vla, env, instruction))
        sr = 100.0 * successes / total
        result.sr_per_seed.append(sr)
        log.info("%s / %s / seed=%s: SR=%.1f%%", vla.name, suite, seed, sr)
    return result


def evaluate_all(models: list[str] | None = None, suites: list[str] | None = None,
                 out_csv: str = "results/libero/baseline_sr.csv") -> pd.DataFrame:
    """Запустить серию 1: baseline всех VLA на всех наборах LIBERO."""
    models = models or list(VLA_REGISTRY)
    suites = suites or list(LIBERO_SUITES)

    rows = []
    for name in models:
        vla = load_vla(name, freeze=True)
        per_suite = {s: evaluate_suite(vla, s) for s in suites}
        mean_sr = float(np.mean([per_suite[s].mean for s in suites]))
        row = {"model": name, "params": VLA_REGISTRY[name]["params"]}
        for s in suites:
            row[s] = round(per_suite[s].mean, 1)
            row[f"{s}_ci95"] = round(per_suite[s].ci95, 2)
        row["mean"] = round(mean_sr, 1)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("mean", ascending=False)
    df.to_csv(out_csv, index=False)
    log.info("Saved baseline SR -> %s", out_csv)
    return df


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    print(evaluate_all())
