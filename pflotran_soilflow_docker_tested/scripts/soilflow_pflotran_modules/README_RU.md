# Декомпозиция `soilflow_pflotran.py`

`soilflow_pflotran.py` пока остается исполняемым совместимым входом для Docker,
CLI и web-backend. Этот пакет задает безопасные границы будущего разбиения и уже
содержит первые вынесенные контракты.

Уже вынесено:

- `input_contract.py`: приведение чисел/булевых значений, optional float,
  ключи и PFLOTRAN d-формат чисел.
- `physical_models.py`: нормализация токенов, размерность сетки, разрешенные
  пары моделей водоудерживания/влагопроводности.
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
- `test_registry.py`: список verification/profile тестов, группировка, выбор
  `all`, чтение параметров сценария, совместимые рабочие пути CLI и уровни
  проверки `strict_analytical`/`partial_balance`/`profile_smoke`.
- `test_artifacts.py`: общие CSV/SVG artifacts и проверка аналитического overlay
  для profile-тестов.
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
- `test_builders`: dataclass-параметры тестов и генераторы PFLOTRAN deck'ов.
- `test_evaluators`: физические сравнения numerical/analytical профилей.

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
