# Аналитические verification-тесты

Этот набор проверяет PFLOTRAN `RICHARDS` mode на простых задачах влагопереноса с известным аналитическим ответом. Внутренняя координата `z` направлена вверх: низ колонки `z=0`, верх `z=L`, отрицательный `qz` означает нисходящий Darcy-поток.

## 1. _test_linear_darcy

Насыщенная однородная колонка с постоянным потоком сверху и заданным нижним давлением. Тест проверяет линейный закон Дарси при `K=Ks`.

Формулы:

```text
qz = -Ks * d(P/(rho*g) + z)/dz
P(z) = P_bottom - rho*g*(1 + qz/Ks)*z
```

Критерии PASS:

```text
max_abs_pressure_error_pa <= 10
saturation_min >= 0.999999
saturation_max <= 1.000001
abs(q_from_gradient_m_s - qz) <= max(1e-9, 0.002*abs(qz))
```

Если ошибка давления меньше допуска, в `TEST_STATUS.txt` выводится `max_abs_pressure_error_pa=0`, а реальное значение сохраняется в `test_diagnostics.json`.

## 2. _test_hydrostatic_vg_no_flow

Гидростатическое равновесие в однородной колонке с van Genuchten saturation. Верхняя и нижняя границы no-flow, источников и стоков нет. Начальное гидростатическое состояние должно сохраниться.

Формулы:

```text
P(z) = P_bottom - rho*g*z
h(z) = (P(z) - P_atm)/(rho*g)
Se(h) = 1, если h >= 0
Se(h) = [1 + (alpha*abs(h))^n]^(-m), если h < 0
S_l = S_r + (1 - S_r)*Se
qz = 0
```

Критерии PASS:

```text
max_abs_pressure_error_pa <= pressure_abs_tolerance_pa
max_abs_saturation_error <= saturation_abs_tolerance
abs(q_from_gradient_m_s) <= flux_abs_tolerance_m_s
```

## 3. _test_unit_gradient_unsat

Установившийся ненасыщенный unit-gradient drainage. Давление постоянно по всей колонке, поэтому градиент давления равен нулю, а поток вызван только гравитацией.

Формулы:

```text
P(z) = P_const
Se = VG((P_const - P_atm)/(rho*g))
kr = sqrt(Se) * [1 - (1 - Se^(1/m))^m]^2
K_eff = Ks * kr
qz = -K_eff
```

Критерии PASS:

```text
max_abs_pressure_error_pa <= pressure_abs_tolerance_pa
max_abs_saturation_error <= saturation_abs_tolerance
abs(q_from_gradient_m_s - q_expected_m_s) <= max(1e-12, flux_relative_tolerance*abs(q_expected_m_s))
```

## 4. _test_brooks_corey_burdine

Гидростатическое равновесие в однородной колонке с парой `Brooks-Corey + Burdine`. Тест нужен как первый контроль того, что генератор входных файлов не привязан только к `van Genuchten + Mualem`.

Формулы:

```text
P(z) = P_bottom - rho*g*z
h(z) = (P(z) - P_atm)/(rho*g)
Se(h) = 1, если alpha*abs(h) <= 1
Se(h) = (alpha*abs(h))^(-lambda), если alpha*abs(h) > 1
kr = Se^(3 + 2/lambda)
qz = 0
```

Критерии PASS такие же, как у hydrostatic no-flow теста: давление, насыщенность и восстановленный поток должны оставаться в заданных допусках.

## 5. _test_transient_uniform_storage_vg

Нестационарная manufactured-задача для горизонтальной no-flow области с равномерным `SOURCE_SINK` через `RATE LIST`. Область остаётся пространственно однородной, а средняя насыщенность должна следовать заданному закону хранения.

Формулы:

```text
S(t) = S0 + A*(1 - cos(2*pi*t/T))/2
Q(t) = phi*V*dS/dt
P(t) = P_atm + rho*g*h(S)
```

Где `h(S)` получается обратной кривой van Genuchten. Тест пишет `uniform_storage_rate.csv`, `analytical_time_series.csv`, `test_comparison.csv`, `test_comparison.svg` и `test_pressure_comparison.svg`. Сравнение выполняется по фактическим временам TECPLOT-снимков из `run_pflotran.log`, потому что PFLOTRAN использует адаптивные шаги.

Критерии PASS:

```text
raw_max_abs_pressure_error_pa <= pressure_abs_tolerance_pa
max_abs_saturation_error <= saturation_abs_tolerance
max_saturation_spread <= uniformity_tolerance
mass_balance_error_m3 <= mass_balance_tolerance_m3
```

## Интерпретация TEST_STATUS.txt

`TEST_STATUS=PASS` означает, что все критерии конкретного теста выполнены. `TEST_STATUS=PASS_WITH_WARNINGS` означает, что физические и solver-проверки пройдены, но PFLOTRAN выдал ожидаемое предупреждение о Mualem-VG без `SMOOTH` для ненасыщенного VG-теста.

## Правило отображения ошибки давления

`raw_max_abs_pressure_error_pa` — фактическая максимальная ошибка давления.
`max_abs_pressure_error_pa` — человекочитаемое значение; оно равно `0` только если `raw_max_abs_pressure_error_pa < 10 Pa`.
`pressure_abs_tolerance_pa` — тестовый допуск PASS/FAIL и не используется для обнуления отображаемой ошибки.

Например, transient-test с `raw_max_abs_pressure_error_pa=41.53` и `pressure_abs_tolerance_pa=120` проходит `pressure_check=PASS`, но в статусе сохраняет `max_abs_pressure_error_pa=41.53`.

## PASS_WITH_WARNINGS

`PASS_WITH_WARNINGS` не означает ошибку расчёта. Это статус для случая, когда физические проверки, `solver_check` и баланс прошли, но PFLOTRAN выдал предупреждение. Ожидаемое предупреждение текущего suite — Mualem-van Genuchten relative permeability without `SMOOTH`.

## Transient uniform storage test

`_test_transient_uniform_storage_vg` не проверяет пространственный поток через грани. Это горизонтальная no-flow manufactured-задача с равномерным source/sink, поэтому `flux_check=SKIP`, а ключевые проверки:

- `uniformity_check`;
- `source_sink_balance_check`;
- `mass_balance_check`.

## Direct flux output probe

Генератор пытается включить PFLOTRAN `MASS_BALANCE_FILE`, `CONSERVATION_FILE` и velocity output. Если прямой flux-output распознан, он сохраняется в `test_diagnostics.json` и `TEST_STATUS.txt` как дополнительная диагностика. Если формат недоступен или не содержит распознаваемых колонок, тест не падает и использует штатный метод проверки: `gradient_reconstruction` для unit-gradient или `analytical_rate_integral` для transient storage.

Все тесты пишут единый набор верхнеуровневых полей:

```text
pressure_check
saturation_check
flux_check
solver_check
warning_check
raw_max_abs_pressure_error_pa
max_abs_pressure_error_pa
solver_error_count
solver_warning_count
solver_diverged
solver_cuts
snes_diverged_count
mualem_vg_without_smooth_warning
mualem_smooth_warning_policy
```

Если ошибка давления меньше допуска, в `TEST_STATUS.txt` выводится `max_abs_pressure_error_pa=0`, а реальное значение сохраняется в `raw_max_abs_pressure_error_pa` и `test_diagnostics.json`.

Suite-статус находится в:

```text
output/runs/_test_suite/TEST_SUITE_STATUS.txt
```

## Частые причины FAIL

- Неверный знак потока или координаты `z`.
- Слишком низкое нижнее давление в saturated-тесте: верхняя часть колонки становится ненасыщенной.
- Несогласованные `mu_water_pa_s`, `Ks` и intrinsic permeability.
- Слишком строгий допуск saturation при низкой точности TECPLOT output.
- Отсутствие колонки `Liquid Saturation` в PFLOTRAN output.

## Команды

```bash
make test
make test-transient
make dry-test
make dry-test-transient
```

## Будущие тесты

Расширенный suite уже содержит отдельно запускаемые аналитические эталоны:

```text
theis_radial_flow
ogata_banks_1d_transport
terzaghi_1d_consolidation
philip_infiltration
green_ampt_infiltration
heat_conduction_1d
buckley_leverett
richards_mms
boussinesq_groundwater_mound
```

Для всех расширенных benchmark'ов дополнительно генерируется `pflotran.in` и при
запуске с `--run` выполняется PFLOTRAN `RICHARDS` profile carrier, чтобы получить
расчетные TECPLOT-профили влажности и давления. Эти проверки имеют статус
`PASS_WITH_WARNINGS`: профили solver'а уже доступны для просмотра, но строгая
метрика сравнения с исходным аналитическим законом будет подключаться отдельными
физическими deck'ами для transport/heat/two-phase/groundwater задач.

Для всех расчетных профилей визуализация ищет аналитический профиль и накладывает его
на тот же график. Приоритетный файл - `analytical_profiles.csv` с колонками
`frame_index`, `depth_m`, `theta_m3_m3`, `pressure_head_m`; если его нет, используется
статический `analytical_solution.csv`. В легенде линии подписываются отдельно:
`PFLOTRAN θ`, `Аналитика θ`, `PFLOTRAN h`, `Аналитика h`.

Для неричардсовых benchmark'ов `analytical_profiles.csv` строится как нормированный
профиль-носитель: исходная аналитическая величина приводится к сопоставимому профилю
`theta_m3_m3`/`pressure_head_m`, который можно наложить на PFLOTRAN-график. Это уже
устраняет отсутствие расчетных профилей, но не заменяет будущую строгую численную
постановку соответствующей физики.
