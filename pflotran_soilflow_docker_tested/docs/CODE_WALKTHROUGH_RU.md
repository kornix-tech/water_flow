# Обзор кода verification-тестов

Основная логика находится в `scripts/soilflow_pflotran.py`.

## Поток выполнения

1. CLI принимает `--mode _test --test <name|all>`.
2. `TEST_BUILDERS` выбирает builder для одного из тестов.
3. Генератор пишет `pflotran.in`, `analytical_solution.csv` и `analytical_test_summary.txt`.
4. При запуске без `--dry-run` вызывается PFLOTRAN.
5. TECPLOT output парсится в записи `z_m`, `pressure_pa`, `saturation`.
6. Оценщик пишет `test_comparison.csv`, `TEST_STATUS.txt` и `test_diagnostics.json`.
7. Для `--test all` создаётся `output/runs/_test_suite/TEST_SUITE_STATUS.txt`.

## Registry

```python
TEST_BUILDERS = {
    "linear_darcy": build_linear_darcy_test,
    "hydrostatic_vg_no_flow": build_hydrostatic_vg_no_flow_test,
    "unit_gradient_unsat": build_unit_gradient_unsat_test,
}
```

## Диагностика

Для каждого расчёта проверяются:

- ошибка давления;
- ошибка насыщенности, если тест использует `Liquid Saturation`;
- линейный градиент давления через регрессию;
- восстановленный Darcy-поток;
- предупреждение PFLOTRAN о Mualem-VG без `SMOOTH`.

Реальные ошибки давления сохраняются в `raw_max_abs_pressure_error_pa` и `test_diagnostics.json`. Пользовательский `max_abs_pressure_error_pa` округляется до нуля только при `raw < 10 Pa`; тестовый допуск `pressure_abs_tolerance_pa` отдельно определяет PASS/FAIL.

## scripts/soilflow_visualize.py

`soilflow_visualize.py` — отдельный postprocessing CLI. Он не запускает PFLOTRAN и не меняет input-deck, а только читает готовые snapshot TECPLOT-файлы `pflotran-NNN.tec`.

Основные шаги:

- читает переменные `X/Y/Z`, `Liquid Pressure`, `Liquid Saturation`, `Porosity`, `Material ID`;
- восстанавливает `theta = porosity * saturation`;
- рассчитывает `pressure_head = (P - P_atm)/(rho*g)`;
- строит профиль по выбранной оси, по умолчанию автоматически выбирая ось с максимальным диапазоном;
- для 2D/3D по умолчанию усредняет значения по глубине;
- пишет `profile_frames_long.csv` и `profile_summary.csv`;
- создаёт самодостаточный `profiles_animation.html` на Plotly;
- создаёт статические SVG/PNG-кадры через matplotlib в headless-режиме.
