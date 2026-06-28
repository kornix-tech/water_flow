# Декомпозиция `soilflow_pflotran.py`

`soilflow_pflotran.py` пока остается исполняемым совместимым входом для Docker,
CLI и web-backend. Этот пакет задает безопасные границы будущего разбиения и уже
содержит первые вынесенные контракты.

Уже вынесено:

- `input_contract.py`: приведение чисел/булевых значений, optional float,
  ключи и PFLOTRAN d-формат чисел.
- `physical_models.py`: нормализация токенов, размерность сетки, разрешенные
  пары моделей водоудерживания/влагопроводности и общие helper'ы van
  Genuchten saturation/relative permeability.
- `extended_analytical.py`: расширенные аналитические эталоны, Green-Ampt,
  Buckley-Leverett и нормированный профиль для overlay с PFLOTRAN.
- `profile_carrier.py`: генерация PFLOTRAN `RICHARDS` profile-carrier deck'ов
  для расширенных аналитических тестов, которым уже нужны расчетные TECPLOT-
  профили, но строгий физический deck подключается отдельным шагом.
- `tabular_curves.py`: нормализация сохраненных табличных кривых, проверка
  монотонности и запись PFLOTRAN `LOOKUP_TABLE`/`PCHIP_LIQ` таблиц для
  `retention_model=tabular` и `conductivity_model=tabular`.
- `demo_deck_writer.py`: стандартный PFLOTRAN `RICHARDS` deck writer для
  demo/пользовательских 1D/2D/3D расчетов, включая сетку, `OUTPUT`,
  `CHARACTERISTIC_CURVES` и граничные условия.
- `floodplain_deck_writer.py`: специализированный PFLOTRAN deck writer и summary
  для пойменного участка с двухслойной почвой, рекой и регулируемой дреной.
- `result_diagnostics.py`: низкоуровневый разбор PFLOTRAN Tecplot output,
  агрегация профилей по глубине, solver/warning diagnostics, direct flux probe,
  transient snapshot loader и единая запись `TEST_STATUS.txt`.
- `result_contract.py`: solver-neutral контракт профилей, diagnostics и статуса
  для будущих parser-adapter реализаций.
- `test_evaluation.py`: единая сборка `PASS/WARN/FAIL`, `UNKNOWN`,
  `PFLOTRAN_ERROR` и suite status.
- `test_suite_artifacts.py`: запись suite summary в `TEST_SUITE_STATUS.txt`,
  `TEST_SUITE_STATUS.json` и `TEST_SUITE_RESULTS.csv` для машинного анализа.
- `test_registry.py`: список verification/profile тестов, группировка, выбор
  `all`, чтение параметров сценария, совместимые рабочие пути CLI и уровни
  проверки `strict_analytical`/`partial_balance`/`profile_smoke`.
- `test_artifacts.py`: общие CSV/SVG artifacts и проверка аналитического overlay
  для profile-тестов.
- `profile_benchmarks.py`: генерация `analytical_profiles.csv` для расширенных
  profile benchmark'ов, сборка TECPLOT-ready статуса и diagnostic
  `REFERENCE_OVERLAY` ошибок после PFLOTRAN запуска.
- `profile_benchmark_cases.py`: машинно-читаемая карта profile benchmark'ов:
  физическое семейство, готовность carrier deck'а и blocker будущего strict
  evaluator. Для каждого profile-запуска пишет `profile_case_manifest.json`,
  где отдельно зафиксированы `profile_deck_kind` и
  `strict_candidate_can_gate_suite`.
- `profile_benchmark_evaluators.py`: диагностическая оценка качества
  `REFERENCE_OVERLAY` по инженерным smoke-границам и явная отметка, что strict
  evaluator для benchmark'а еще `PENDING`.
- `profile_strict_evaluators.py`: strict-кандидаты для profile benchmark'ов.
  Сейчас реализован кандидат Richards MMS по RMSE/max-error напора и влажности;
  он остается диагностическим до замены carrier deck'а на MMS source-term deck.
- `richards_mms_case.py`: первый Richards MMS source-term candidate: пишет
  `richards_mms_initial_profile.csv`, `richards_mms_source_rate.csv`,
  `richards_mms_spatial_source_profile.csv` и PFLOTRAN `SOURCE_SINK`/`RATE LIST`
  deck с uniform storage source. Cell-wise residual table уже готовит spatial
  MMS source, но strict-кандидат не gate'ит suite до PFLOTRAN adapter-а.
- `richards_test_cases.py`: dataclass-параметры, PFLOTRAN deck'и,
  аналитические CSV/summary и builders для strict/partial Richards verification.
- `richards_test_evaluators.py`: сравнение PFLOTRAN TECPLOT-профилей с
  аналитическими решениями Darcy/VG/Brooks-Corey/transient storage и запись
  `TEST_STATUS.txt`.
- `richards_test_runner.py`: запуск strict/partial Richards verification:
  генерация artifacts, запуск solver-а и выбор evaluator-а.
- `profile_test_runner.py`: запуск profile-smoke benchmark'ов: reference
  artifacts, profile-carrier deck, solver и TECPLOT-ready status.
- `test_solver_execution.py`: общий execution-helper для native/WSL PFLOTRAN
  запуска в verification runners и единая обработка `PFLOTRAN_ERROR`/
  `GENERATED_ONLY`.
- `verification_runner.py`: suite-router режима `_test`: чтение JSON, выбор
  тестов, рабочие директории и запись suite status.
- `solver_runner.py`: поиск исполняемого PFLOTRAN, native/WSL запуск и запись
  логов без знания физической постановки. Это текущий solver adapter.
- `surface_balance.py`: нормализация погодных строк, расчет `net_surface_input`,
  mean top flux и производных параметров почвы. Это текущий adapter блока
  верхнего водного баланса/испарения.
- `contracts.py`: декларация границ модулей и заменяемых adapter-слотов:
  `solver`, `surface_balance`, `result_parser`.

Планируемые границы:

- `input_contract`: JSON-снимок исходных данных, единицы измерения, валидация.
- `physical_models`: пары моделей водоудерживания и влагопроводности.
- `deck_writer`: расширение вынесенного writer'а на специализированные
  постановки и устранение оставшихся дублей `OUTPUT`/`CHARACTERISTIC_CURVES`
  в тестовых deck'ах.
- `analytical_tests`: строгие метрики сравнения профилей и физические PFLOTRAN
  deck'и для transport/heat/two-phase/groundwater задач.
- `test_builders`: расширение вынесенных Richards builders на будущие
  transport/heat/two-phase/groundwater постановки.
- `test_evaluators`: строгие физические сравнения для profile-smoke benchmark'ов.
- `verification_runner`: сохранять только orchestration и не возвращать в него
  физические формулы, которые должны жить в case/evaluator модулях.
- `test_runner`: новые семейства тестов подключать отдельными runner-модулями,
  чтобы центральный suite-router не зависел от физики конкретной постановки.

Правило дальнейшего рефакторинга: переносить по одному блоку, оставляя
`soilflow_pflotran.py` тонким совместимым CLI-фасадом и добавляя тест на каждый
перенесенный контракт.

Уровни проверки:

- `strict_analytical`: PFLOTRAN сравнивается с аналитическим или установившимся
  решением по численным метрикам.
- `partial_balance`: проверяется баланс/однородность/ODE, но не весь
  пространственный поток.
- `profile_smoke`: PFLOTRAN строит расчетный профиль, аналитика есть как
  эталонный артефакт, но строгой физической постановки и метрики пока нет.
