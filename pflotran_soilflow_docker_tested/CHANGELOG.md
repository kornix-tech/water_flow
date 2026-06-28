## [Unreleased]

### Added
- Добавлена расчетная поддержка полной пары `tabular + tabular`: CLI строит PFLOTRAN `SATURATION_FUNCTION LOOKUP_TABLE` и `PERMEABILITY_FUNCTION PCHIP_LIQ` из сохраненных `soil_curve_tables`.
- Добавлен smoke-скрипт `scripts/smoke_tabular_permeability.sh` и Makefile-цель `smoke-tabular-permeability` для быстрой проверки табличных кривых.
- Добавлен web workflow `Табличная почва`: страница `Тесты` создает расчет в SQLite, сохраняет табличные кривые Pc(S)/kr(S), запускает PFLOTRAN и автоматически строит графики.
- Добавлен живой regression-smoke `scripts/api_tabular_workflow_smoke.sh` для полного API-контура `расчет -> soil_curve_tables -> PFLOTRAN -> визуализация`.
- Добавлены валидация и SVG-предпросмотр табличных кривых на странице `Исходные данные`.
- Добавлен модуль `soilflow_pflotran_modules.demo_deck_writer` для стандартного PFLOTRAN RICHARDS deck writer и unit-тесты его совместимости с прежним wrapper'ом.
- Добавлен модуль `soilflow_pflotran_modules.result_diagnostics` для Tecplot parser, solver/warning diagnostics, direct flux probe и unified status writer.
- Добавлены модули `soilflow_pflotran_modules.solver_runner` и `soilflow_pflotran_modules.surface_balance` как replaceable adapter boundaries для solver-а и блока верхнего водного баланса/испарения.
- Добавлены модули `soilflow_pflotran_modules.floodplain_deck_writer`, `result_contract` и `test_evaluation`, а также smoke `scripts/smoke_modular_scenarios.sh`.
- Добавлены модули `soilflow_pflotran_modules.test_registry` и `test_artifacts` для маршрутизации тестов, путей suite и общих CSV/SVG/overlay artifacts.
- Добавлен модуль `soilflow_pflotran_modules.profile_benchmarks` для генерации аналитических profile overlay и оценки TECPLOT-ready статусов профильных benchmarks.
- Добавлены модули `soilflow_pflotran_modules.richards_test_cases` и `richards_test_evaluators` для strict/partial Richards verification builders и evaluators.
- Добавлен модуль `soilflow_pflotran_modules.verification_runner` для orchestration режима `_test`: выбора сценариев, рабочих папок, запуска solver-а и записи suite status.
- Добавлены модули `soilflow_pflotran_modules.richards_test_runner` и `profile_test_runner`, чтобы запуск strict/partial и profile-smoke тестов был отделен от центрального suite-router.
- Добавлен модуль `soilflow_pflotran_modules.test_solver_execution` для общего native/WSL PFLOTRAN запуска внутри verification runners.
- Добавлен модуль `soilflow_pflotran_modules.test_suite_artifacts` для записи suite summary в TXT/JSON/CSV.
- Добавлены API `/api/results/runs/{run_name}/test-suite` и `/api/results/runs/{run_name}/test-status`, а также блоки сводки на странице `Расчеты` для чтения verification-suite и отдельных тестов без парсинга текстовых status-файлов во frontend.
- Добавлен API `/api/results/runs/{run_name}/overview` и общий frontend-компонент карточек состояния для страниц `Статус` и `Расчеты`.
- Добавлен UI route smoke `scripts/ui_route_smoke.sh` и Makefile-цель `ui-smoke` для проверки коротких frontend URL и SPA/API fallback-контракта живого сервиса.
- Добавлен `scripts/api_results_performance_smoke.sh`: живой performance/stability smoke для `/api/results/runs`, `/overview`, `/test-suite` и `/test-status` на временных run-папках с большим числом файлов.
- `scripts/api_results_performance_smoke.sh` дополнительно проверяет HTML-график, `/plots` и отказ от выдачи symlink-файлов из run-директории.
- Добавлен `scripts/api_restart_resilience_smoke.sh`: live smoke для проверки restart-поведения активных job'ов, SQLite schema version и базовых API после `docker compose restart soilflow-web`.
- Добавлен модуль `soilflow_pflotran_modules.profile_benchmark_evaluators` для диагностической оценки `REFERENCE_OVERLAY` profile-smoke benchmark'ов и явной отметки pending strict evaluator.
- Добавлен модуль `soilflow_pflotran_modules.profile_benchmark_cases` с машинно-читаемой картой profile benchmark'ов, физическими семействами и blocker'ами будущих strict evaluator'ов.
- Добавлен модуль `soilflow_pflotran_modules.profile_strict_evaluators` с первым strict-кандидатом для `richards_mms` по RMSE/max-error напора и влажности.
- Для profile benchmark'ов теперь записывается `profile_case_manifest.json` с физическим семейством, типом deck'а, готовностью carrier-а и флагом допуска strict-кандидата к suite gate.
- Добавлен `soilflow_pflotran_modules.richards_mms_case`: `richards_mms` теперь генерирует uniform storage `SOURCE_SINK`/`RATE LIST` candidate deck и artifacts `richards_mms_initial_profile.csv`, `richards_mms_source_rate.csv`.
- Для `richards_mms` добавлен cell-wise residual artifact `richards_mms_spatial_source_profile.csv` с storage derivative, flux divergence и расчетным MMS source по ячейкам.
- Для `richards_mms` добавлены adapter-ready artifacts `richards_mms_spatial_source_matrix.json` и `richards_mms_spatial_source_manifest.json` с initial pressure profile и матрицами cell-wise source по времени.
- Profile status для `richards_mms` теперь проверяет согласованность MMS adapter artifacts и добавляет `richards_mms_adapter_artifact_check`.
- Suite CSV теперь включает `richards_mms_adapter_artifact_check` для машинного контроля готовности adapter artifacts.
- Для каждого profile benchmark теперь пишется `profile_strict_plan.json` с readiness stage, blocker'ом и следующим шагом подключения strict evaluator-а.
- Suite summary теперь агрегирует strict-readiness stages: strict gate ready, deck-adapter pending, case-builder pending и strict-evaluator pending.
- Добавлены reference overlay метрики для profile-smoke benchmark'ов: RMSE/max-error по объемной влажности и напору относительно `analytical_profiles.csv`.
- Для profile-smoke benchmark'ов теперь записывается `profile_overlay_comparison.csv` с построчным сравнением `PFLOTRAN vs analytical`.
- Добавлена архитектурная схема `docs/ARCHITECTURE_RU.md` с текущими потоками данных и заменяемыми adapter-границами.
- Добавлен модуль `soilflow_pflotran_modules.tabular_curves` с нормализацией табличных кривых, записью PFLOTRAN `.dat` файлов и unit-тестами монотонности.
- Добавлен интерфейс редактирования табличных кривых почвы на странице `Исходные данные`: паспорт кривой, точки `h/P/theta/S/kr/K`, сохранение, обновление и удаление через SQLite API.
- Добавлен модуль `soilflow_pflotran_modules.profile_carrier` для генерации PFLOTRAN profile-carrier deck'ов расширенных аналитических тестов.
- Добавлен API `/api/soil-curves` для создания, чтения, списка и удаления табличных кривых почвы, привязанных к расчету.
- Добавлен модуль `soilflow_pflotran_modules.extended_analytical` для расширенных аналитических эталонов и нормированных profile overlay.
- Добавлена SQLite-миграция schema version 2 с таблицами `soil_curve_tables` и `soil_curve_points` для будущих табличных экспериментальных кривых водоудерживания/влагопроводности.
- Добавлены модули `soilflow_pflotran_modules.input_contract` и `soilflow_pflotran_modules.physical_models`, а также unit-тесты перенесенных контрактов.
- Добавлен endpoint `/api/health/ready` для проверки готовности расчетной среды: PFLOTRAN, workspace/tmp, frontend dist и SQLite schema version.
- Добавлен `scripts/api_smoke.sh` и Makefile-цель `api-smoke` для read-only проверки базового backend API-контракта живого сервиса.
- Добавлены backend unit-тесты для безопасных путей, SQLite-миграций и обработки активных заданий после рестарта.
- Добавлена документация `docs/API_CONTRACT_RU.md` с описанием lifecycle-статусов, endpoints и совместимых legacy API.
- Добавлен пакет `scripts/soilflow_pflotran_modules` как безопасный первый шаг декомпозиции большого `soilflow_pflotran.py`.
- Добавлен `scripts/check_project.sh` и Makefile-цель `project-check` для единой проверки Python compile, frontend build, restart web-сервиса и health-check.
- Добавлен `scripts/sync_to_running_container.sh` и Makefile-цель `web-sync` для документированной синхронизации исходников и frontend dist в уже запущенный контейнер без полной пересборки образа.
- Добавлен frontend-модуль `testDefinitions.ts` для предметных описаний analytical/verification-тестов отдельно от UI-страницы.
- Добавлен режим плановых двумерных расчетов `2D_XY`: генератор PFLOTRAN формирует сетку `nx × ny × 1`, поддерживает опциональные боковые давления WEST/EAST/SOUTH/NORTH и строит XY-карты влажности/давления.
- Добавлена визуализация двумерных вертикальных разрезов `2D_XZ`: расчёты `nx × 1 × nz` автоматически отображаются как XZ-карты влажности и давления.
- Добавлена специализированная постановка `floodplain_controlled_drainage`: двухслойная пойменная почва, река, водоупор и регулируемая закрытая дрена как pressure-regulated internal sink.
- Добавлено удаление сохраненных расчетов из интерфейса `Расчеты` с удалением связанной папки результатов внутри `output/runs`.
- Добавлен переход из `Расчеты` в `Исходные данные` выбранного расчета через `/ishodnye?calculation_id=...`; форма подставляет сохраненные значения без пересчета.
- Добавлена живая навигация из панели прогресса в `Статус` и из списка `Расчеты` в `Графики` выбранного расчета.
- Добавлено хранение пользовательских исходных данных в SQLite как записей `расчет №...` с датой создания, статусом, связью с job и папкой результатов.
- Добавлены API и интерфейс поиска ранее сохраненных расчетов с загрузкой исходных данных и просмотром готовых результатов без пересчета.
- Добавлен JSON-шаблон `input/soilflow_pflotran_demo.json` как источник начальной структуры формы и тестовых сценариев.
- Добавлен transient verification-test `_test_transient_uniform_storage_vg` с PFLOTRAN `SOURCE_SINK`/`RATE LIST`, аналитическими CSV, диагностикой и SVG-графиками.
- Добавлены цели `test-transient` и `dry-test-transient`.
- Добавлен модуль `scripts/soilflow_visualize.py` для HTML/SVG/PNG-визуализации профилей влажности и давления по TECPLOT output.
- Добавлены Docker/Makefile-команды `visualize`, `visualize-demo`, `visualize-test-*` и `visualize-selftest`.
- Добавлен web-интерфейс: FastAPI backend, SQLite job store, React/Vite frontend, Docker Compose сервис `soilflow-web` и Makefile-цели `web-*`.
- Добавлена документация `docs/WEB_INTERFACE_RU.md` и roadmap `docs/WEB_ROADMAP_RU.md`.
- Добавлены короткие понятные URL web-интерфейса: `/ishodnye`, `/zadachi`, `/testy`, `/rezultaty`, `/grafiki`, `/sistema`.
- Добавлена многовкладочная страница `Исходные данные` для редактирования параметров проекта без ручной загрузки файла.
- Добавлена панель прогресса задач в левом меню: общий индикатор по последним задачам и отдельный индикатор текущего запуска.

### Changed
- Обновлен план работ в `docs/NEXT_CHAT_CONTEXT_RU.md` и
  `docs/EXTERNAL_CONTEXT_RU.md`: приоритеты смещены на устойчивость runtime/API,
  производительность чтения результатов, ленивую загрузку тяжелых artifacts и
  разделение fast/full/research verification gates.
- `/api/results/runs` больше не сканирует до 500 файлов внутри каждой run-папки
  при построении списка; детальный список файлов остается в endpoint конкретного
  run.
- `scripts/check_project.sh` теперь включает results performance smoke как
  отдельный gate после API/workflow проверок и перед UI route smoke.
- Results performance smoke теперь делает restart web-сервиса после создания
  временных run-папок и проверяет, что summary/detail/status endpoints
  сохраняют контракт после restart.
- Results performance smoke теперь проверяет не только время ответа, но и
  верхний лимит размера JSON payload для summary/detail/overview/status
  endpoints.
- `scripts/check_project.sh` теперь включает restart resilience smoke как
  отдельный gate после results performance smoke.
- JSON-only suite status теперь определяется в summary/overview так же, как
  TXT suite status: `has_suite_status=true`, а `/overview` показывает карточку
  `test-suite`.
- Чтение TXT/JSON/CSV status artifacts теперь использует общий кэш по
  `path + size + mtime_ns`, чтобы повторные overview/status запросы не
  перечитывали неизменные artifacts с диска.
- `GET /api/results/runs/{run_name}/overview` теперь кэширует собранную сводку
  по сигнатуре status artifacts (`size + mtime_ns`) и инвалидируется при
  изменении TXT/JSON/CSV/status-файлов.
- Чтение test-suite/test-status стало устойчивее к частично записанным
  artifacts: битый `TEST_SUITE_STATUS.json` откатывается к TXT/CSV, а битый
  `test_diagnostics.json` помечается как `PARTIAL` без потери основного статуса.
- `TEST_STATUS.txt` без ключа `TEST_STATUS` теперь возвращает
  `status=UNKNOWN` и `artifact_readiness=PARTIAL`, а не неявно выглядит как
  полноценный статус.
- Страница `Графики` перестала опрашивать список файлов графиков для run без
  готовой визуализации и снижает частоту фонового обновления до 5 секунд.
- В интерфейсе `Исходные данные` табличная кривая стала разрешенной моделью водоудерживания и влагопроводности для проверенных пар `van_genuchten + tabular`, `brooks_corey + tabular` и `tabular + tabular`.
- Сообщение об ошибке failed-задания теперь извлекает предметную строку `ERROR`/`Traceback` из job log, если она есть.
- JSON-снимок расчета, передаваемый в CLI при запуске расчета или визуализации, теперь включает `soil_curve_tables` сохраненного расчета.
- Генератор profile-carrier deck'ов вынесен из `soilflow_pflotran.py`, чтобы продолжить декомпозицию монолита без изменения CLI-контракта.
- Из `soilflow_pflotran.py` вынесен блок extended analytical helpers; основной скрипт стал ближе к CLI-фасаду.
- Статус расширенных profile-тестов теперь включает `analytical_overlay_check`, источник и число точек аналитического профиля.
- `scripts/api_smoke.sh` проверяет read-only контракт `/api/soil-curves/calculations/{id}`, если в базе уже есть расчеты.
- `scripts/api_smoke.sh` проверяет read-only контракт `/api/results/runs/{run_name}/overview` для первого доступного run без жесткой привязки к имени теста.
- `scripts/check_project.sh` теперь включает UI route smoke после API/workflow проверок живого сервиса.
- Profile-smoke suite CSV теперь включает качество reference overlay и статус strict evaluator readiness.
- Profile-smoke TEST_STATUS и suite CSV теперь включают физическое семейство benchmark'а и готовность carrier deck'а.
- `richards_mms` помечен как `EVALUATOR_READY_DECK_PENDING`: strict-кандидат готов, но остается диагностическим до замены carrier deck на MMS source-term постановку.
- Profile-smoke TEST_STATUS и suite CSV теперь явно различают `profile_deck_kind` и `strict_candidate_can_gate_suite`, чтобы strict-кандидат нельзя было случайно сделать обязательным до готовности физического deck'а.
- `richards_mms` переведен с generic profile-carrier на `richards_mms_uniform_source_candidate`; strict-кандидат остается диагностическим, пока не добавлен spatial MMS source-term.
- Blocker `richards_mms` уточнен: spatial residual table уже пишется, но PFLOTRAN deck еще не применяет cell-wise source и nonuniform initial profile.
- Blocker `richards_mms` уточнен до уровня deck adapter: matrix/manifest artifacts готовы, но текущий PFLOTRAN input еще остается uniform-source candidate.
- `analytical_test_summary.txt` для `richards_mms` теперь явно публикует readiness MMS adapter artifacts и pending-статус PFLOTRAN deck adapter-а.
- Profile status, suite CSV и `profile_case_manifest.json` теперь публикуют `strict_readiness_stage`.
- `TEST_SUITE_STATUS.txt`/JSON теперь показывают stage counts, чтобы следующий инженерный блок выбирать по текущим blocker'ам, а не вручную по отдельным run-папкам.
- `scripts/check_project.sh` теперь включает полный расчетный smoke для табличной почвы через публичный API.
- Стандартный PFLOTRAN deck writer вынесен из `soilflow_pflotran.py`; основной скрипт оставлен совместимым CLI-фасадом и отдельно маршрутизирует `floodplain_controlled_drainage`.
- Парсинг результатов PFLOTRAN, solver diagnostics и запись `TEST_STATUS.txt` вынесены из `soilflow_pflotran.py` в модуль с unit-тестами.
- Поиск/запуск PFLOTRAN и расчет производных параметров верхнего потока вынесены из `soilflow_pflotran.py`; фасад больше не содержит прямого `subprocess` runner-а и текущая ET-логика изолирована для будущей замены.
- Специализированная floodplain-постановка, базовая сборка статусов тестов и suite status вынесены из `soilflow_pflotran.py`; `check_project.sh` теперь компилирует весь каталог `scripts` и запускает modular scenario smoke.
- Список verification/profile тестов, выбор `all`, пути рабочих папок и общие CSV/SVG helpers вынесены из `soilflow_pflotran.py`; CLI сохраняет прежний контракт `--test`, `--workdir`, `--output-dir`.
- Генерация `analytical_profiles.csv` и оценка profile-smoke TECPLOT-статуса вынесены из `soilflow_pflotran.py`; helper'ы van Genuchten saturation/kr перенесены в `physical_models.py`.
- Strict/partial Richards test builders, PFLOTRAN deck writers, analytical artifacts и numerical evaluators вынесены из `soilflow_pflotran.py`; CLI-контракт `--mode test/_test` сохранён.
- Orchestration режима `_test` вынесена из `soilflow_pflotran.py`; основной скрипт стал тоньше и передает verification-suite в отдельный runner-модуль.
- `verification_runner` упрощен до suite-router: физика и запуск конкретных семейств тестов перенесены в family runner-модули.
- Дублирующая native/WSL solver-execution логика удалена из family runner'ов и заменена общим helper-модулем.
- Verification-suite теперь кроме `TEST_SUITE_STATUS.txt` пишет `TEST_SUITE_STATUS.json` и `TEST_SUITE_RESULTS.csv`, чтобы анализ результатов не зависел от парсинга текстового файла.
- Dry-run verification-suite теперь сохраняет `verification_level` в suite summary, поэтому счетчики `strict_analytical`/`partial_balance`/`profile_smoke` информативны без запуска PFLOTRAN.
- Profile-smoke benchmark'и теперь явно пишут `profile_overlay_comparison=REFERENCE_OVERLAY`; это диагностическое сравнение не повышает их до strict analytical verification.
- Verification-suite теперь явно разделяет уровни `strict_analytical`, `partial_balance` и `profile_smoke` в `TEST_STATUS.txt`, suite summary и web-описаниях тестов.
- Первый блок `soilflow_pflotran.py` вынесен из монолита в модули: парсинг входных значений, PFLOTRAN float-format и валидация пар моделей почвы.
- Все расширенные аналитические benchmarks теперь генерируют PFLOTRAN `RICHARDS` profile carrier, `pflotran.in` и `analytical_profiles.csv`, чтобы после запуска были расчетные TECPLOT-профили для графиков.
- Dry-run suite больше не считает статусы `GENERATED`/`GENERATED_ONLY` failed при `TEST_SUITE_STATUS=DRY_RUN`.
- `scripts/check_project.sh` теперь дополнительно запускает backend unit-тесты и read-only API smoke после рестарта web-сервиса.
- `scripts/sync_to_running_container.sh` синхронизирует весь каталог `scripts`, чтобы новые вспомогательные модули попадали в работающий контейнер.
- Актуальные web/API документы и текстовые источники схем переведены с XLSX-first формулировок на JSON/SQLite-first контракт.
- README и quickstart переведены на актуальный JSON/SQLite/web-first workflow; XLSX описан только как legacy/экспортный формат.
- Внутренний backend helper запуска расчета переименован с demo-oriented `demo_command` на `calculation_command`; публичный endpoint `/run-demo` сохранен как совместимый wrapper.
- Страница `Тесты` теперь импортирует описания тестов из отдельного модуля и содержит только UI/workflow-логику.
- Frontend-router очищен от legacy alias-адресов прошлых этапов разработки; публичными маршрутами интерфейса теперь остаются только короткие русские URL.
- Улучшены внутренние имена frontend workflow тестов и backend helpers для SQLite/job/application settings, чтобы код читался ближе к предметной модели.
- Видимое название проекта во frontend заменено на `Влагоперенос в почве`, включая заголовок браузерной вкладки и боковую панель.
- Раздел `Задания` переименован в `Статус`, раздел `Результаты` переименован в `Расчеты`; короткие URL обновлены до `/status` и `/raschety`.
- Страницы `Статус`, `Расчеты` и `Графики` автоматически обновляют состояние задач, расчетов и файлов графиков; в `Статус` добавлена оценка оставшегося времени по истории завершенных задач.
- Страница `Тесты` перестроена в вертикальный список: слева кнопка запуска, справа назначение теста и описание аналитического решения для сравнения.
- На страницу `Обзор` добавлены краткие сведения об архитектуре, применённых модулях, сторонних компонентах, лицензиях и текущем этапе разработки.
- Тесты в web-интерфейсе разделены на раскрывающиеся группы: служебный запуск, 1D/пространственно-однородные benchmarks и 2D/радиальные/профильные benchmarks.
- При запуске отдельного теста web-интерфейс автоматически отслеживает расчет, запускает построение графиков и показывает кнопку просмотра результата.
- В исходные данные добавлен выбор `retention_model` и `conductivity_model` с проверкой совместимости пар моделей почвы.
- Добавлены отдельно запускаемые расширенные аналитические benchmarks: Theis, Ogata-Banks, Terzaghi, Philip, Green-Ampt, heat conduction, Buckley-Leverett, Richards MMS и Boussinesq.
- Добавлен verification-test `_test_brooks_corey_burdine` для пары Brooks-Corey + Burdine.
- Demo-Richards переведен на 3600 расчетных шагов за 7 суток: `maximum_timestep_days` изменен на `0.0019444444444444444` сут.
- Подготовка demo- и `_test`-расчетов переведена с XLSX на JSON-снимки из базы данных проекта; XLSX больше не используется как этап подготовки входных данных.
- Интерактивные графики ограничивают ось объемной влажности физическим диапазоном от нуля; скорость проигрывателя теперь задается логарифмическим ползунком `0.1x...1000x` и применяется сразу во время прокрутки.
- `_test` по умолчанию запускает весь набор из четырёх аналитических тестов.
- Docker-образ теперь собирает frontend static bundle на отдельном stage и по умолчанию запускает web-сервер через FastAPI.
- Видимый frontend переведён на русский язык; технические статусы API, режим авторизации и типы заданий отображаются русскоязычными подписями.
- Frontend теперь полноценно поддерживает `SOILFLOW_AUTH_MODE=token`: API-запросы, скачивания файлов и загрузка HTML-графиков используют Bearer-токен без передачи токена в URL.
- Пункт меню `Вводные` переименован в `Исходные данные`; рабочий URL раздела — `/ishodnye`.
- Поля страницы `Исходные данные` перестроены в компактную трёхколоночную строку: имя параметра модели, поле ввода умеренной ширины и русскоязычное пояснение.
- Имена параметров на странице `Исходные данные` больше не содержат размерность; размерность или отметка о безразмерности выводится в русскоязычном пояснении, а поля ввода выровнены по единой левой границе.
- Дизайн интерактивных и статических графиков профилей унифицирован: один шрифт, разнесённые элементы управления, одна подпись глубины, тёмные оси и светлая сетка.
- Старые англоязычные и промежуточные URL первого web-этапа удалены из frontend-router.
- Web API стал строже проверять имена расчётов, job id, публичные workspace-файлы и лимиты архивов.
- `TEST_STATUS.txt` унифицирован для всех тестов: физические проверки, solver-check, предупреждения и raw/reported ошибки давления пишутся в едином формате.
- Правило отображения `max_abs_pressure_error_pa` отделено от PASS/FAIL допуска: значение обнуляется только при `raw < 10 Pa`.
- Transient storage test теперь пишет `flux_check=SKIP` и отдельные `uniformity/source_sink/mass_balance` проверки.

### Fixed
- Убрано дублирование статуса тестового workflow на странице `Тесты`: состояние остается только под кнопкой запуска.
- Обновлена подпись графиков давления почвенной влаги.
- Восстановлено отображение интерактивных HTML-графиков на странице `Графики`: iframe теперь открывает backend HTML напрямую, чтобы CSP графиков разрешал встроенный Plotly.

### Removed
- Удалён старый fallback расширенных тестов, который создавал только аналитический CSV/SVG со статусом `SKIP` без PFLOTRAN-профиля.
- `output/runs` и вложенные расчетные артефакты удалены из git-индекса; локальные результаты остаются generated files и игнорируются.
- Удалены старые frontend alias-маршруты `/inputs`, `/vvod`, `/jobs`, `/zadachi`, `/tests`, `/results`, `/rezultaty`, `/visualization`, `/system`.

### Technical
- Табличное водоудерживание передается в PFLOTRAN через `LOOKUP_TABLE`-файл с колонками `time saturation Pc`; прежний кандидат `SATURATION_FUNCTION PCHIP` оставлен неиспользуемым, потому что текущая сборка PFLOTRAN отклоняет его на unsaturated extension check.
- SQLite-хранилище переведено на явный журнал `schema_migrations`; текущая миграция сохраняет обратную совместимость с базами без `jobs.calculation_id`.
- Строковые статусы заданий и расчетов вынесены в общий backend-модуль `job_lifecycle.py`.
- `.gitignore` расширен для SQLite WAL/SHM, frontend dist, Vite temp, локальных архивов, uploads/tmp и generated visualization artifacts.
- Нумерация новых расчетов теперь опирается на SQLite AUTOINCREMENT и не переиспользует номер удаленного последнего расчета.
- При старте backend незавершенные до перезапуска `queued/running` задачи помечаются как прерванные, чтобы прогресс и статус не зависали после рестарта контейнера.
- Удалён backend-сервис сохранения исходных данных в XLSX и endpoint скачивания рабочего XLSX, чтобы исключить XLSX как хранилище данных проекта.
- Docker Compose теперь передает build-arg `BUILD_JOBS`, поэтому сборку можно запускать с `BUILD_JOBS=12`.
- Ошибки API в frontend теперь показываются через единый компонент уведомления вместо тихого сбоя отдельных страниц.
- В production-сборке frontend отключён Vite modulepreload polyfill, чтобы убрать лишний `MutationObserver` и console-error в embedded browser.
- Dockerfile runtime-слой переупорядочен: установка Python-зависимостей теперь кэшируется отдельно от изменений frontend/backend-кода.
- Добавлены security headers, constant-time проверка Bearer-токена, sandbox для HTML-графиков и очистка `SOILFLOW_API_TOKEN` из окружения дочерних расчётов.
- По умолчанию отключены FastAPI docs/OpenAPI; добавлены CSP, cache policy, request body limit и простой in-memory rate-limit для API.
- Backend читает и сохраняет редактируемые исходные данные через JSON/SQLite API, сохраняя структуру многовкладочной формы.
- Удалён frontend-компонент загрузки XLSX и API endpoint `/api/files/upload-xlsx`, так как исходные данные теперь редактируются через web-формы.
- ZIP-архивы и списки результатов теперь пропускают symlink-файлы и ограничивают объём/количество файлов, чтобы не читать данные вне run-директории.
- Прямые file responses для status/results/visualization теперь проходят через общий safe-file helper: symlink, директории, path escape и слишком крупные inline-файлы не отдаются клиенту.
- SPA fallback больше не отдаёт `index.html` для неизвестных `/api/...` и `HEAD /api/...` запросов.
- Docker Compose теперь принимает web security/time-limit параметры через переменные окружения.
- Suite-статус теперь различает `PASS`, `PASS_WITH_WARNINGS` и `FAIL`; ожидаемое предупреждение Mualem-VG без `SMOOTH` для ненасыщенных VG-тестов учитывается как warning, а не как падение.
- Добавлена диагностика solver/warning и пробный direct flux-output probe через PFLOTRAN mass/conservation/velocity output.
- Визуализация теперь умеет создавать HTML-просмотр аналитических SVG-эталонов для тестов без TECPLOT-профилей PFLOTRAN.
- Визуализация расчетных профилей теперь накладывает аналитические профили из `analytical_profiles.csv` или `analytical_solution.csv` и подписывает линии в легенде как `PFLOTRAN` и `Аналитика`.
- Генератор PFLOTRAN `CHARACTERISTIC_CURVES` переведен с жестко заданной пары van Genuchten + Mualem на валидируемую пару моделей водоудерживания и влагопроводности.
- При чтении старых расчетов backend подтягивает новые поля исходных данных из bundled JSON-шаблона, сохраняя введенные пользователем значения.
- Для Richards-связанных расширенных benchmark'ов добавлен профильный PFLOTRAN-runner, который проверяет наличие TECPLOT snapshot'ов и пишет статус `PASS_WITH_WARNINGS` вместо аналитического `SKIP`.
- Для `philip_infiltration`, `green_ampt_infiltration` и `richards_mms` генерируется покадровый `analytical_profiles.csv`, чтобы расчетные PFLOTRAN-профили сравнивались с аналитическими профилями на одном графике.
