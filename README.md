# Исследование применения обучения с подкреплением для повышения эффективности управления роботами с использованием визуально-языковых моделей

[![paper](https://img.shields.io/badge/paper-PDF-b31b1b)](paper/main.pdf)
[![slides](https://img.shields.io/badge/slides-PDF-1f6feb)](slides/presentation.pdf)
[![code](https://img.shields.io/badge/code-Python%203.12-3776ab)](code)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Автор:** Новичков Дмитрий Евгеньевич, группа 3435

**Научный руководитель:** Ведяков Алексей Александрович, доцент ФСУиР, канд. техн. наук, ординарный доцент

Выпускная квалификационная работа бакалавра, Университет ИТМО, Факультет систем
управления и робототехники, направление 15.03.06 «Мехатроника и робототехника», 2026.

## Аннотация

Работа посвящена повышению эффективности управления роботами-манипуляторами при
выполнении задач, заданных на естественном языке, за счёт интеграции методов
обучения с подкреплением (RL) с визуально-языковыми моделями действий (VLA).
Систематизированы три направления интеграции: RL-дообучение VLA (Residual RL,
PLD, STARE-VLA), VLM как генератор вознаграждений (EUREKA, Text2Reward,
RL-VLM-F, RoboReward) и VLM как высокоуровневый планировщик (SayCan,
Embodied-R1). Реализован программный прототип с двумя ветками: основной —
residual SAC со стадийным вознаграждением для дообучения готовых VLA на LIBERO,
и дополнительной — VLM-кодогенерация функции награды (Qwen2.5-VL) на MetaWorld.

**Основной результат** (девять VLA-моделей, 3 seed, 95% ДИ): residual SAC + stage
устойчиво повышает SR от +1,5 п.п. (OpenVLA-OFT: 97,1 → 98,6%) до +4,1 п.п.
(RT-1-X: 82,9 → 87,0%). Установлена сильная обратная корреляция (ρ = −0,97)
между baseline SR и приростом (с поправкой на эффект потолка бенчмарка).
End-to-end разморозка VLA деградирует (−0,6 п.п.) из-за катастрофического
забывания, поэтому заморозка базовой политики предпочтительна. Результат 98,6%
сопоставим с PLD (99,0% на LIBERO) при бюджете в 3 раза меньше.

**Дополнительный результат** (MetaWorld): VLM-награда с 3 итерациями рефлексии
поднимает SR на push-v3 с 48% до 85% (ρ(R,S): 0,12 → 0,81); средний SR по трём
задачам — 77,2% против 36,7% у разреженной награды.

## Структура репозитория

```
bachelor-thesis/
  code/        # программный прототип (Python 3.12)
    src/vla_rl/    # модули: evaluate_vla, residual_rl_train, stage_reward, vlm_reward_gen
    configs/       # Hydra-конфиги серий 1–5
    scripts/       # run_series1.sh … run_series5.sh
    results/       # CSV метрик, чекпоинты, сгенерированные награды
    requirements.txt
  paper/       # исходники текста ВКР (LaTeX) + main.pdf
  slides/      # презентация защиты (LaTeX + PDF + pptx-генератор)
  review/      # отзыв руководителя и рецензия
  LICENSE
  README.md
```

## Основные результаты (LIBERO, средний SR по 4 наборам)

| Модель          | До RL  | После RL | Δ        |
|-----------------|:------:|:--------:|:--------:|
| OpenVLA-OFT-7B  | 97,1   | **98,6** | +1,5     |
| UniVLA-7B       | 95,0   | 96,8     | +1,8     |
| π₀-3B           | 94,0   | 96,1     | +2,1     |
| CogACT-8B       | 93,0   | 95,4     | +2,4     |
| SmolVLA-2.2B    | 92,5   | 95,3     | +2,8     |
| π₀-fast-3B      | 90,6   | 93,8     | +3,2     |
| SpatialVLA-4B   | 88,0   | 91,5     | +3,5     |
| Octo-Small      | 86,0   | 89,9     | +3,9     |
| RT-1-X          | 82,9   | 87,0     | +4,1     |

## Запуск кода

```bash
cd code
python -m venv .venv && source .venv/bin/activate   # Python 3.12
pip install -r requirements.txt
export PYTHONPATH=src

bash scripts/run_series1.sh   # baseline девяти VLA на LIBERO
bash scripts/run_series3.sh   # residual SAC + stage для всех 9 VLA
bash scripts/run_series5.sh   # VLM-кодогенерация награды на MetaWorld
```

Подробности — в [`code/`](code). Для основного трека дополнительно требуются
установленные LIBERO/ROBOSUITE и веса VLA-моделей; для дополнительного —
MetaWorld и доступ к Qwen2.5-VL (vLLM).

## Сборка текста и презентации

```bash
cd paper  && latexmk -lualatex main.tex            # -> main.pdf
cd slides && latexmk -lualatex presentation.tex    # -> presentation.pdf
```

## Цитирование

```bibtex
@thesis{novichkov_bachelor_thesis_2026,
  author      = {Новичков, Дмитрий Евгеньевич},
  title       = {Исследование применения обучения с подкреплением для повышения
                 эффективности управления роботами с использованием
                 визуально-языковых моделей},
  type        = {Выпускная квалификационная работа бакалавра},
  institution = {Университет ИТМО},
  location    = {Санкт-Петербург},
  year        = {2026},
  langid      = {russian},
  url         = {https://github.com/mfclabber/bachelor-thesis}
}
```

## Лицензия

MIT — см. [LICENSE](LICENSE).
