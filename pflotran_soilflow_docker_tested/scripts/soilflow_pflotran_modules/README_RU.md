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
  `CHARACTERISTIC_CURVES` и граничные условия. Специализированная floodplain-
  постановка пока остается в CLI-фасаде как отдельный будущий блок.

Планируемые границы:

- `input_contract`: JSON-снимок исходных данных, единицы измерения, валидация.
- `physical_models`: пары моделей водоудерживания и влагопроводности.
- `deck_writer`: расширение вынесенного writer'а на специализированные
  постановки и устранение оставшихся дублей `OUTPUT`/`CHARACTERISTIC_CURVES`
  в тестовых deck'ах.
- `analytical_tests`: строгие метрики сравнения профилей и физические PFLOTRAN
  deck'и для transport/heat/two-phase/groundwater задач.
- `runner`: запуск PFLOTRAN и диагностические файлы.

Правило дальнейшего рефакторинга: переносить по одному блоку, оставляя
`soilflow_pflotran.py` тонким совместимым CLI-фасадом и добавляя тест на каждый
перенесенный контракт.
