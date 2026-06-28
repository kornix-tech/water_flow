# API-контракт web-сервиса

Документ фиксирует текущий публичный контракт FastAPI backend для проекта
«Влагоперенос в почве». Внутреннее хранилище проекта - SQLite и JSON-снимки
исходных данных расчета. XLSX допускается только как формат экспорта или
legacy-артефакт и не участвует в подготовке расчета.

## Служебные проверки

- `GET /api/health` - быстрый liveness-сигнал. Возвращает `status=ok`, если
  приложение отвечает.
- `GET /api/health/ready` - readiness-сигнал перед расчетами. Проверяет наличие
  PFLOTRAN, workspace, frontend dist, запись во временный каталог и доступность
  SQLite. Может вернуть `503`, если сервис поднят, но расчетная среда не готова.
- `GET /api/system/info` - сведения о рабочей директории, PFLOTRAN, auth-режиме,
  rate limit и доступности frontend.

`scripts/ui_route_smoke.sh` дополняет API smoke проверкой frontend-раздачи:
короткие URL `/`, `/ishodnye`, `/status`, `/testy`, `/raschety`, `/grafiki`,
`/sistema` должны отдавать SPA `index.html`, а неизвестные `/api/...` маршруты
должны оставаться JSON 404 и не попадать в SPA fallback.

## Исходные данные и расчеты

- `GET /api/inputs/workbook` - текущий JSON-шаблон исходных данных в форме
  вкладок интерфейса.
- `PUT /api/inputs/workbook` - сохранить введенные пользователем параметры как
  новый `расчет №...` в SQLite.
- `GET /api/calculations` - список расчетов с фильтрацией по строке `q`.
- `GET /api/calculations/{calculation_id}` - исходные данные и метаданные
  выбранного расчета. Поля формы заполняются значениями этого расчета.
- `DELETE /api/calculations/{calculation_id}` - удалить расчет и его папку
  результатов, если связанное задание не находится в активном состоянии.
- `POST /api/calculations/{calculation_id}/run` - запустить расчет по сохраненному
  JSON-снимку.

## Внутреннее хранилище табличных кривых

Начиная со schema version 2 база содержит задел под экспериментальные табличные
кривые почвы:

- `soil_curve_tables` - паспорт таблицы кривой, привязанный к `calculation_id`;
  хранит `curve_name`, `curve_kind`, выбранные модели, единицы измерения и
  комментарий.
- `soil_curve_points` - упорядоченные точки таблицы: `pressure_head_m`,
  `pressure_pa`, `water_content`, `saturation`, `relative_permeability`,
  `hydraulic_conductivity_m_s`.

Публичные endpoints:

- `GET /api/soil-curves/calculations/{calculation_id}` - список табличных кривых
  выбранного расчета.
- `POST /api/soil-curves/calculations/{calculation_id}` - сохранить таблицу
  кривой и набор точек.
- `GET /api/soil-curves/{table_id}` - получить одну таблицу с точками.
- `DELETE /api/soil-curves/{table_id}` - удалить таблицу кривой.

При удалении расчета связанные табличные кривые удаляются каскадно.

Страница `Исходные данные` использует эти endpoints напрямую: пользователь
сначала сохраняет расчет в SQLite, затем добавляет одну или несколько таблиц
кривых к этому `calculation_id`. При запуске расчета и при построении
визуализации backend добавляет сохраненные таблицы в временный JSON-снимок как
`soil_curve_tables`, чтобы CLI видел полный состав исходных данных без обращения
к SQLite.

Если в расчетном JSON выбрана `conductivity_model=tabular` при
`retention_model=van_genuchten` или `retention_model=brooks_corey`, CLI строит
PFLOTRAN `PERMEABILITY_FUNCTION PCHIP_LIQ`. Если выбрана пара
`retention_model=tabular` + `conductivity_model=tabular`, CLI строит полный
PFLOTRAN `CHARACTERISTIC_CURVES` через `SATURATION_FUNCTION LOOKUP_TABLE` и
`PERMEABILITY_FUNCTION PCHIP_LIQ`. Табличные данные записываются рядом с
`pflotran.in` во внешние `.dat` файлы:

- для водоудерживания: `time saturation Pc`, где `Pc` - капиллярное давление,
  Па, а `time` фиксирован как `0.d0` для статической кривой;
- для влагопроводности: `saturation kr`, где `kr` - относительная
  влагопроводность, безразмерная.

Значения насыщенности должны строго возрастать, `Pc` и `kr` должны быть
монотонными. Полный tabular smoke-run в текущей сборке PFLOTRAN проходит через
`LOOKUP_TABLE`; вариант `SATURATION_FUNCTION PCHIP` намеренно не используется,
потому что он отклоняется PFLOTRAN на проверке unsaturated extension.

Проверка полного web/API workflow закреплена в
`scripts/api_tabular_workflow_smoke.sh`. Smoke-сценарий создает временный расчет,
сохраняет две таблицы кривых через `/api/soil-curves`, запускает расчет через
`/api/calculations/{id}/run`, строит графики через
`/api/jobs/run-visualization/{run_name}` и проверяет HTML-визуализацию. По
умолчанию созданный расчет удаляется после проверки; для ручного анализа можно
запустить с `KEEP_TABULAR_API_SMOKE=1`.

## Задания

Статусы задания:

- `queued` - задание создано и ожидает запуска.
- `running` - внешний расчетный процесс выполняется.
- `success` - процесс завершился с кодом `0`.
- `failed` - процесс завершился ошибкой или был прерван рестартом сервиса.
- `cancelled` - задание отменено пользователем.

Статусы расчета:

- `draft` - сохранены исходные данные, расчет еще не запускался.
- `queued`, `running`, `success`, `failed`, `cancelled` - состояние последнего
  связанного задания.

Endpoints:

- `GET /api/jobs` - список последних заданий.
- `GET /api/jobs/{job_id}` - карточка задания.
- `GET /api/jobs/{job_id}/log` - хвост лога задания.
- `POST /api/jobs/{job_id}/cancel` - отменить активное задание.
- `POST /api/jobs/run-test/{test_name}` - запустить отдельный аналитический тест.
- `POST /api/jobs/run-test-suite` - запустить все тесты.
- `POST /api/jobs/run-visualization/{run_name}` - построить графики для уже
  существующих результатов.

Совместимые endpoints старого UI:

- `POST /api/jobs/run-demo` - сохранен для старых кнопок, внутри запускает
  последний расчет из SQLite или создает расчет из шаблона.
- `POST /api/jobs/run-custom` - сохранен для старого контракта, но запуск
  привязывается к `calculation_id`.

## Результаты и файлы

- `GET /api/results/runs` - список папок результатов.
- `GET /api/results/runs/{run_name}` - сведения о конкретном запуске.
- `GET /api/results/runs/{run_name}/status` - текстовый статус расчета/теста.
- `GET /api/results/runs/{run_name}/test-suite` - типизированная JSON-сводка
  verification-suite из `TEST_SUITE_STATUS.json` с fallback на
  `TEST_SUITE_STATUS.txt`/`TEST_SUITE_RESULTS.csv`.
- `GET /api/results/runs/{run_name}/test-status` - типизированная JSON-сводка
  отдельного тестового запуска из `TEST_STATUS.txt` и, если есть,
  `test_diagnostics.json`.
  Для profile-smoke benchmark'ов статус может включать диагностические поля
  `profile_evaluator=reference_overlay`, `profile_overlay_quality_check` и
  `strict_profile_evaluator`, а также `profile_physics_family`,
  `profile_carrier_status` и blocker будущего strict evaluator. Значение может
  быть `PENDING` или `EVALUATOR_READY_DECK_PENDING`; эти поля не повышают тест
  до strict analytical verification.
  Run-директория profile benchmark'а также содержит `profile_case_manifest.json`
  с `profile_deck_kind` и `strict_candidate_can_gate_suite`; этот manifest
  является guard-контрактом, чтобы strict-кандидат не стал suite-gate до
  готовности физического deck'а.
  Для `richards_mms` дополнительно может приходить
  `richards_mms_strict_candidate_check`: это готовый strict-кандидат по
  RMSE/max-error напора и влажности. Сейчас `richards_mms` использует
  `richards_mms_uniform_source_candidate`: PFLOTRAN deck уже содержит
  `SOURCE_SINK`/`RATE LIST` по среднему хранению, но до spatial MMS source-term
  он остается диагностикой, а не suite PASS/FAIL критерием. Дополнительно
  пишется `richards_mms_spatial_source_profile.csv` с cell-wise residual, но
  текущий deck еще не применяет этот artifact как PFLOTRAN source. Для будущего
  adapter-а также пишутся `richards_mms_spatial_source_matrix.json` и
  `richards_mms_spatial_source_manifest.json` с initial pressure profile и
  source matrices. В `TEST_STATUS.txt` может приходить
  `richards_mms_adapter_artifact_check=PASS|FAIL` как проверка согласованности
  manifest и matrix shapes.
- `GET /api/results/runs/{run_name}/overview` - единый обзор состояния запуска:
  verification-suite, отдельный тест, графики или fallback по файлам результата.
- `GET /api/results/runs/{run_name}/plots` - список файлов графиков.
- `GET /api/results/runs/{run_name}/file/{file_path}` - безопасное чтение файла
  внутри папки запуска.
- `GET /api/files/download-zip/{run_id}` - ZIP-архив папки запуска с лимитами на
  размер и число файлов.

Read-only smoke `scripts/api_smoke.sh` проверяет `/overview` для первого
доступного запуска со status/visualization-артефактами, а если таких нет - для
первой обычной папки результата. Если run-папок нет, эта часть smoke
пропускается с явным сообщением.

## Ограничения безопасности

- В token-режиме все API-запросы требуют `Authorization: Bearer ...`, кроме
  HTML-графиков, где допускается защищенная cookie для embedded просмотра.
- Пути файлов нормализуются и не могут выходить за разрешенные директории.
- Имена запусков ограничены безопасным шаблоном `[A-Za-z0-9_.-]`.
- API ограничивает размер JSON body и число запросов в минуту на client host.
- Ответы API помечаются `Cache-Control: no-store`, а frontend получает CSP и
  базовые security headers.
