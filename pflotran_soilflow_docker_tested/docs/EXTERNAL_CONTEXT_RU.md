# Внешний контекст проекта

**Проект:** Влагоперенос в почве  
**Папка проекта:** `/home/zenbook/SF/pflotran_soilflow_docker_tested`  
**Папка git-репозитория:** `/home/zenbook/SF`  
**Дата фиксации контекста:** 2026-06-16  
**Назначение файла:** восстановить состояние разработки в новом чате Codex без потери архитектурного контекста.

## 1. Краткое состояние

Проект представляет собой Docker-комплект и web-интерфейс для подготовки, запуска и анализа расчетов влагопереноса в почве на базе PFLOTRAN. Текущая целевая постановка расширилась от 1D демонстрационного уравнения Ричардса до 2D XY/XZ расчетов, аналитических тестов и исследовательской задачи управляемого дренажа пойменного участка.

Актуальный web-сервис запущен в Docker:

```text
Контейнер: pflotran_soilflow_docker_tested-soilflow-web-1
Образ: soilflow-pflotran:local
URL: http://localhost:18080/
Порт контейнера: 8080
Рабочая папка внутри контейнера: /workspace
Код приложения внутри контейнера: /opt/soilflow
PFLOTRAN: /opt/pflotran/src/pflotran/pflotran
Режим авторизации сейчас: SOILFLOW_AUTH_MODE=none
```

Важно: часть последних изменений была внесена в исходники и дополнительно скопирована в уже работающий контейнер без полной пересборки образа. Полная пересборка `docker compose build soilflow-web` ранее запускалась, но была остановлена из-за длительной сборки PETSc/MPICH. Поэтому при пересоздании контейнера нужно либо пересобрать образ, либо заново скопировать актуальные скрипты в контейнер.

## 2. Главные архитектурные решения

1. PFLOTRAN остается внешним расчетным ядром, а проект хранит свою предметную структуру в Python/JSON/SQLite и генерирует PFLOTRAN input deck.
2. XLSX больше не является внутренним этапом подготовки данных. XLSX допускается только как формат вывода/экспорта проекта или исторический артефакт.
3. Пользовательские исходные данные сохраняются в SQLite как записи `расчет №...` с timestamp, JSON-снимком параметров, статусом, связью с job и папкой результатов.
4. Web-интерфейс работает как SPA на React/Vite, а backend на FastAPI обслуживает API, static frontend, файлы результатов и HTML-графики.
5. Долгие операции запускаются как фоновые задания через `JobManager` и `ThreadPoolExecutor`; состояние заданий хранится в SQLite.
6. Визуализация отделена от расчета: `soilflow_pflotran.py` генерирует и запускает расчет, `soilflow_visualize.py` читает TECPLOT/CSV и строит HTML/SVG/CSV графические артефакты.
7. Для безопасности backend валидирует имена расчетов, job id, пути к файлам, размер API body и архивов; добавлены CSP/security headers, rate-limit и опциональный Bearer-token режим.
8. SQLite schema version 2 содержит задел под табличные экспериментальные кривые почвы: `soil_curve_tables` и `soil_curve_points`.

## 3. Карта каталогов

```text
pflotran_soilflow_docker_tested/
  Dockerfile
  docker-compose.yml
  Makefile
  CHANGELOG.md
  README_*.md
  THIRD_PARTY_NOTICE_RU.md

  input/
    soilflow_pflotran_demo.json      актуальный JSON-шаблон исходных данных
    soilflow_pflotran_demo.xlsx      исторический/выводной формат, не внутренняя БД

  scripts/
    soilflow_pflotran.py             генератор PFLOTRAN deck, runner, тесты, сравнения
    soilflow_visualize.py            HTML/SVG/CSV визуализация 1D/XY/XZ профилей
    check_project.sh                 единая проверка: Python compile, backend unittest, frontend build, restart, API smoke
    api_smoke.sh                     read-only проверка базового API-контракта живого web-сервиса
    sync_to_running_container.sh     документированный hot-copy workflow для запущенного контейнера
    soilflow_pflotran_modules/       вынесенные контракты парсинга/моделей и границы дальнейшей декомпозиции
    *.sh                             вспомогательные Docker-команды

  web/backend/app/
    main.py                          FastAPI app, middleware, routers, static SPA
    config.py                        настройки окружения и workspace
    job_store.py                     SQLite-хранилище jobs/calculations + schema_migrations + soil_curve_* tables
    job_lifecycle.py                 единые статусы job/calculation lifecycle
    job_manager.py                   очередь и запуск фоновых subprocess
    file_manager.py                  безопасная работа с путями и zip
    routers/                         API endpoints
    services/                        CLI, JSON-снимки, архивы, логи, runner

  web/frontend/src/
    App.tsx                          SPA router
    routes.ts                        русские короткие URL
    api/client.ts                    клиент API, token/session/cookie для графиков
    pages/                           страницы интерфейса
    components/                      layout, прогресс, логи, графики, файлы
    styles.css                       основной CSS

  docs/
    EXTERNAL_CONTEXT_RU.md           этот файл
    ANALYTICAL_TESTS_RU.md           аналитические тесты
    WEB_INTERFACE_RU.md              web-интерфейс
    API_CONTRACT_RU.md               публичный backend API-контракт, статусы и legacy endpoints
    SCHEMA_ALGORITHM_COMPONENTS_RU.md
    schema_*.dot/png/svg             существующие схемы

  output/runs/                       generated результаты расчетов, исключены из git
```

Результаты расчетов считаются generated artifacts и не должны попадать в git. В работающем контейнере результаты и база находятся в Docker volume `/workspace`:

```text
/workspace/input/
/workspace/output/runs/
/workspace/jobs/
/workspace/archives/
/workspace/tmp/
/workspace/jobs.sqlite
```

## 4. Архитектурная схема верхнего уровня

```mermaid
flowchart LR
  User["Пользователь в браузере"] --> Frontend["React/Vite SPA<br/>/ishodnye /status /testy /raschety /grafiki"]
  Frontend --> Api["FastAPI backend<br/>/api/*"]
  Api --> SQLite["SQLite<br/>/workspace/jobs.sqlite<br/>jobs + calculations"]
  Api --> JobManager["JobManager<br/>очередь фоновых заданий"]
  JobManager --> Runner["CommandRunner<br/>subprocess + job.log"]
  Runner --> Generator["scripts/soilflow_pflotran.py<br/>JSON -> PFLOTRAN input"]
  Generator --> PFLOTRAN["PFLOTRAN executable"]
  PFLOTRAN --> RunDir["/workspace/output/runs/<run_name>"]
  Api --> Visualizer["scripts/soilflow_visualize.py"]
  Visualizer --> RunDir
  RunDir --> Frontend
```

## 5. Поток данных расчета

```mermaid
sequenceDiagram
  participant U as Пользователь
  participant F as Frontend
  participant B as FastAPI
  participant DB as SQLite
  participant JM as JobManager
  participant CLI as soilflow_pflotran.py
  participant P as PFLOTRAN
  participant V as soilflow_visualize.py
  participant R as run directory

  U->>F: Заполняет "Исходные данные"
  F->>B: PUT /api/inputs/workbook
  B->>DB: INSERT calculations(input_json, status=draft)
  U->>F: Запускает расчет
  F->>B: POST /api/calculations/{id}/run
  B->>JM: submit(kind=calculation)
  JM->>DB: INSERT jobs(status=queued)
  JM->>CLI: python3 soilflow_pflotran.py --mode demo --run
  CLI->>R: pflotran.in, forcing_daily.csv, summary
  CLI->>P: запуск PFLOTRAN
  P->>R: *.out, *.tec, mass/conservation files
  JM->>DB: job/calculation status = success/failed
  F->>B: POST /api/jobs/run-visualization/{run}
  JM->>V: python3 soilflow_visualize.py
  V->>R: plots/*.html, *.svg, *.csv, VISUALIZATION_STATUS.txt
  F->>B: GET /api/visualization/{run}/html
  B->>F: HTML-график в iframe
```

## 6. Backend

### 6.1 Точка входа

`web/backend/app/main.py`:

- создает `FastAPI`;
- загружает `Settings`;
- создает `FileManager`, `JobStore`, `JobManager`;
- при старте помечает незавершенные `queued/running` задания как прерванные;
- подключает routers;
- отдает собранный frontend из `web/frontend/dist`;
- добавляет middleware авторизации, rate-limit, лимита body и security headers.
- `GET /api/health` остается быстрым liveness endpoint.
- `GET /api/health/ready` проверяет PFLOTRAN, workspace/tmp, frontend dist и SQLite schema version.

### 6.2 Конфигурация

`web/backend/app/config.py` читает переменные окружения:

```text
SOILFLOW_HOME=/opt/soilflow
SOILFLOW_WORKSPACE=/workspace
PFLOTRAN_EXE=/opt/pflotran/src/pflotran/pflotran
PORT=8080
JOB_WORKERS=1
SOILFLOW_AUTH_MODE=none|token
SOILFLOW_API_TOKEN=<token>
SOILFLOW_MAX_ARCHIVE_MB=2048
SOILFLOW_MAX_ARCHIVE_FILES=20000
SOILFLOW_JOB_TIMEOUT_SECONDS=21600
SOILFLOW_API_RATE_LIMIT_PER_MINUTE=120
SOILFLOW_MAX_JSON_BODY_KB=512
SOILFLOW_ENABLE_API_DOCS=false
SOILFLOW_ENABLE_HSTS=false
```

`ensure_workspace()` создает рабочие директории и копирует bundled JSON-шаблон в `/workspace/input/soilflow_pflotran_demo.json`, если пользовательского файла еще нет.

### 6.3 SQLite-хранилище

`web/backend/app/job_store.py` создает две таблицы:

```text
jobs(
  id TEXT PRIMARY KEY,
  kind TEXT,
  status TEXT,
  command_json TEXT,
  run_name TEXT,
  created_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  exit_code INTEGER,
  log_path TEXT,
  output_dir TEXT,
  error_message TEXT,
  calculation_id INTEGER
)

calculations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT UNIQUE,                 "расчет №<id>"
  created_at TEXT,
  updated_at TEXT,
  input_json TEXT,                   полный JSON-снимок исходных данных
  run_name TEXT UNIQUE,
  job_id TEXT,
  status TEXT,
  result_dir TEXT
)
```

Текущие статусы: `draft`, `queued`, `running`, `success`, `failed`, `cancelled`.

При удалении расчета запись удаляется из `calculations`, а у связанных jobs поле `calculation_id` обнуляется. В интерфейсе также предусмотрено удаление папки результатов внутри `output/runs`.

### 6.4 API routers

```text
/api/health
  GET ""                               health-check

/api/system
  GET /info                            параметры окружения и доступность PFLOTRAN/frontend

/api/projects
  GET/POST/GET {id}                    пока один default project

/api/inputs
  GET /workbook                        текущий/последний workbook из SQLite или seed JSON
  PUT /workbook                        сохраняет workbook как новый расчет
  POST /reset                          сбрасывает форму к bundled JSON

/api/calculations
  GET "" ?q=...                        поиск расчетов
  GET /{id}                            расчет + input workbook
  DELETE /{id}                         удаление расчета
  POST /{id}/run                       запуск сохраненного расчета

/api/jobs
  POST /run-demo                       demo расчет
  POST /run-test-suite                 весь набор тестов
  POST /run-test/{test_name}           отдельный тест
  POST /run-visualization/{run_name}   построение графиков
  POST /run-custom                     legacy/custom запуск
  GET ""                               список заданий
  GET /{job_id}                        карточка задания
  GET /{job_id}/log                    лог задания
  POST /{job_id}/cancel                отмена

/api/results
  GET /runs                            список run-директорий
  GET /runs/{run_name}                 информация по run
  GET /runs/{run_name}/status          статус
  GET /runs/{run_name}/plots           файлы графиков
  GET /runs/{run_name}/file/{path}     файл результата

/api/files
  GET /download-zip/{run_id}           zip архива run
  GET /{path}                          безопасная отдача публичных workspace-файлов

/api/visualization
  GET /{run_name}/html                 интерактивный HTML-график
  GET /{run_name}/status               VISUALIZATION_STATUS.txt
```

### 6.5 Безопасность backend

Уже реализовано:

- `safe_run_name()` ограничивает имена расчетов регулярным выражением и запрещает `..`;
- `safe_resolve_under()` запрещает absolute path и выход за базовую папку;
- zip-архивы пропускают symlink и ограничены по размеру/числу файлов;
- job id валидируется как hex UUID без дефисов;
- API body ограничен;
- API rate-limit по IP в памяти процесса;
- CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, COOP/CORP;
- FastAPI docs/OpenAPI выключены по умолчанию;
- Bearer token включается через `SOILFLOW_AUTH_MODE=token`;
- токен API удаляется из окружения дочерних расчетных процессов.

Ограничения:

- rate-limit in-memory, при нескольких worker/process он не общий;
- нет пользователей, ролей и разграничения проектов;
- SQLite не имеет миграционного слоя, схема обновляется вручную через `CREATE TABLE IF NOT EXISTS`/`ALTER TABLE`;
- token auth подходит для локального/закрытого использования, не для полноценного multi-user SaaS.

## 7. Frontend

Frontend: React + TypeScript + Vite без отдельного UI-фреймворка.

Главные файлы:

```text
web/frontend/src/App.tsx
  простой SPA-router по pathname, без react-router

web/frontend/src/routes.ts
  короткие русские URL:
    /                       Обзор
    /ishodnye               Исходные данные
    /status                 Статус
    /testy                  Тесты
    /raschety               Расчеты
    /grafiki                Графики
    /sistema                Система
  legacy alias-адреса удалены, неизвестные frontend пути ведут на "Обзор"

web/frontend/src/api/client.ts
  fetch-wrapper, Bearer token, sessionStorage, cookie для iframe-графиков

web/frontend/src/components/Layout.tsx
  боковая панель, навигация, прогресс задач, переход в "Статус"

web/frontend/src/pages/InputsPage.tsx
  многовкладочная форма исходных данных, сохранение в SQLite,
  подстановка параметров выбранного расчета, валидация пар моделей почвы

web/frontend/src/pages/JobsPage.tsx
  список заданий, auto-refresh, оценка оставшегося времени

web/frontend/src/pages/ResultsPage.tsx
  поиск расчетов, удаление, просмотр результатов без пересчета,
  переход к графикам выбранного расчета

web/frontend/src/pages/TestsPage.tsx
  тесты в раскрывающихся группах, запуск отдельного теста,
  автозапуск визуализации после расчета

web/frontend/src/testDefinitions.ts
  предметные описания аналитических и verification-тестов; UI-страница
  остается слоем workflow и представления

web/frontend/src/pages/VisualizationPage.tsx
  выбор run, запуск визуализации, iframe HTML-графиков, список файлов
```

Интерфейс должен оставаться полностью русскоязычным. Видимое название проекта: `Влагоперенос в почве`.

Особые UX-требования, уже заложенные в текущей версии:

- на странице исходных данных строки параметров имеют три колонки: имя переменной, поле ввода умеренной ширины, комментарий на русском;
- имена переменных не должны переноситься на вторую строку;
- размерности перенесены из имени переменной в комментарий;
- прогресс задач виден в левой панели, чтобы пользователь понимал, что сайт не завис;
- графики должны иметь читаемые оси, светлую сетку, без дублирования подписей и наложений;
- скорость проигрывания графиков задается логарифмическим ползунком от `0.1x` до `1000x`.

## 8. Расчетный слой: `soilflow_pflotran.py`

Скрипт выполняет несколько ролей:

1. читает JSON workbook;
2. извлекает параметры и weather rows;
3. валидирует пару моделей водоудерживания/влагопроводности;
4. строит structured grid для 1D, 2D_XY, 2D_XZ и частично 3D;
5. генерирует PFLOTRAN input deck;
6. пишет вспомогательные CSV/summary;
7. запускает PFLOTRAN;
8. оценивает аналитические тесты и пишет `TEST_STATUS.txt`.

Поддержанные типы сетки:

```text
1D:
  nx=1, ny=1, nz>1
  вертикальная колонка по Z

2D_XY:
  nx>1, ny>1, nz=1
  плановая сетка, один слой по Z
  поддержаны боковые давления WEST/EAST/SOUTH/NORTH

2D_XZ:
  nx>1, ny=1, nz>1
  вертикальный разрез

3D:
  архитектурно частично заложен через structured GRID,
  но пользовательские сценарии и визуализация пока сфокусированы на 1D/2D.
```

Поддержанные пары моделей почвы:

```text
retention_model=van_genuchten + conductivity_model=mualem
retention_model=van_genuchten + conductivity_model=burdine
retention_model=brooks_corey + conductivity_model=burdine
retention_model=brooks_corey + conductivity_model=corey
```

Зарезервированные, но не полностью проверенные варианты:

```text
retention_model=gardner
conductivity_model=gardner
пара "Голованов-Аверьянов" / экспоненциальное водоудерживание + степенная влагопроводность
```

Специализированная постановка `scenario_type=floodplain_controlled_drainage`:

- 2D XZ представительская полоса между дренами;
- верхний слой торфяно-болотной почвы толщиной около 0.6 м;
- нижний слой песка толщиной около 2 м;
- нижняя граница как водоупор;
- река задается боковым Dirichlet head;
- закрытая дрена представлена как `SOURCE_SINK` с `PRESSURE_REGULATED_MASS_RATE VOLUME`;
- управляемый колодец пока схематизирован через контрольный напор и пропускную способность, а не как явная pipe-network модель.

## 9. Визуализация: `soilflow_visualize.py`

Скрипт читает TECPLOT output PFLOTRAN и аналитические CSV, затем создает:

```text
plots/profiles_animation.html
plots/profile_frames_long.csv
plots/profile_summary.csv
plots/profile_theta_h_tNNNN.svg
plots/VISUALIZATION_STATUS.txt
```

Для 2D:

```text
XY:
  plots/xy_map_frames_long.csv
  plots/xy_map_summary.csv
  plots/xy_map_theta_h_tNNNN.svg
  visualization_type=xy_map

XZ:
  plots/xz_map_frames_long.csv
  plots/xz_map_summary.csv
  plots/xz_map_theta_h_tNNNN.svg
  visualization_type=xz_map
```

Поведение:

- 1D профили показывают PFLOTRAN и аналитику на одном графике с легендой;
- по оси влажности не показывается отрицательная полуплоскость;
- надпись давления в интерфейсе: `Давление почвенной влаги`;
- для всех расширенных benchmark'ов добавлен PFLOTRAN `RICHARDS` profile carrier и `analytical_profiles.csv`, чтобы после запуска были расчетные TECPLOT-профили для графиков;
- для неричардсовых benchmark'ов профиль пока является нормированным carrier-сравнением, а не строгой численной постановкой transport/heat/two-phase/groundwater физики.

## 10. Аналитические и verification-тесты

Список тестов, известных backend:

```text
linear_darcy
hydrostatic_vg_no_flow
unit_gradient_unsat
transient_uniform_storage_vg
brooks_corey_burdine
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

В интерфейсе тесты разделены на группы:

- служебный запуск;
- 1D и пространственно-однородные benchmark-задачи;
- 2D/радиальные/профильные benchmark-задачи.

Часть расширенных аналитических тестов пока остается эталонной аналитикой без полноценного PFLOTRAN deck. Для релизного качества нужно довести все такие тесты до статуса, где численный профиль PFLOTRAN сравнивается с аналитическим профилем на графике.

## 11. Текущие демо и исследовательские расчеты

В Docker volume `/workspace/output/runs` есть важные run-директории:

```text
demo_xy_plan
  2D XY demo, GRID 40 x 24 x 1, visualization_type=xy_map
  URL: http://localhost:18080/grafiki?run=demo_xy_plan

demo_xz_section
  2D XZ demo, GRID 50 x 1 x 40, visualization_type=xz_map
  URL: http://localhost:18080/grafiki?run=demo_xz_section

demo_floodplain_controlled_drainage
  двухслойный пойменный дренаж с регулируемым колодцем
  URL: http://localhost:18080/grafiki?run=demo_floodplain_controlled_drainage

study_floodplain_closed
study_floodplain_open
study_floodplain_partial_low
study_floodplain_partial_mid
study_floodplain_partial_high
  серия сценариев перекрытия колодца

study_floodplain_controlled_drainage
  сводка controlled_drainage_study_summary.md/csv

study_floodplain_impedance
  предварительная многофакторная сводка impedance_partial_summary.md/csv

study_impedance_dry_closed
study_impedance_dry_partial
study_impedance_dry_open
study_impedance_moderate_closed
study_impedance_moderate_partial
study_impedance_moderate_open
study_impedance_heavy_closed
  частично выполненная серия по дождю/импедансу
```

Смысл исследовательской постановки по дренажу:

- входной сигнал: инфильтрация сверху, уровень реки, степень открытия колодца;
- выходы: расход через дрену, обмен с рекой, изменение запаса воды, положение уровня грунтовых вод;
- параметры анализа: емкость системы, проводимость/пропускная способность дренажа, импеданс к дождевому воздействию, задержка и амплитуда отклика.

Ключевое ограничение: это пока не полная pipe/collector/well network. Дрена и колодец представлены эквивалентным внутренним стоком с pressure-regulated расходом.

## 12. Docker и сборка

`docker-compose.yml`:

```text
service: soilflow-web
image: soilflow-pflotran:local
build args:
  UBUNTU_VERSION=24.04
  PETSC_VERSION=v3.24.5
  PETSC_ARCH=linux-gnu-c-opt
  PFLOTRAN_GIT_REF=master
  PFLOTRAN_REPO=https://bitbucket.org/pflotran/pflotran
  BUILD_JOBS=${BUILD_JOBS:-4}
ports:
  ${WEB_PORT:-8080}:8080
volume:
  soilflow_workspace:/workspace
restart:
  unless-stopped
```

Для быстрой локальной работы ранее использовалось:

```bash
WEB_PORT=18080 docker compose up -d soilflow-web
BUILD_JOBS=12 docker compose build soilflow-web
```

Проверка сервиса:

```bash
curl -fsS http://localhost:18080/api/health
curl -fsS http://localhost:18080/api/system/info
```

## 13. Состояние git/worktree

На момент создания файла рабочее дерево уже было грязным до этой задачи. Среди измененных файлов были:

```text
CHANGELOG.md
docs/ANALYTICAL_TESTS_RU.md
input/soilflow_pflotran_demo.json
scripts/soilflow_pflotran.py
scripts/soilflow_visualize.py
web/backend/app/config.py
web/backend/app/routers/calculations.py
web/backend/app/routers/inputs.py
web/backend/app/routers/jobs.py
web/backend/app/services/input_json_service.py
web/backend/app/services/soilflow_cli.py
web/frontend/index.html
web/frontend/src/components/Layout.tsx
web/frontend/src/pages/DashboardPage.tsx
web/frontend/src/pages/InputsPage.tsx
web/frontend/src/pages/TestsPage.tsx
web/frontend/src/styles.css
```

Также присутствуют сгенерированные или локальные артефакты:

```text
output/runs/_test_*/
web/frontend/node_modules/
scripts/__pycache__/
```

Нельзя выполнять `git reset --hard`, `git clean`, массовое удаление результатов или откат файлов без явного подтверждения пользователя.

## 14. Известные расхождения и технический долг

1. Часть старых схем и исторической документации еще использует термин "XLSX-контракт"; актуальные README переведены на JSON/SQLite-first, XLSX только вывод/legacy.
2. Docker image может отставать от исходников, потому что часть последних правок была hot-copied в контейнер.
3. SQLite-схема растет вручную, без Alembic/миграционного слоя.
4. Нет полноценной модели пользователей/ролей/проектов; `projects` пока фактически stub для default project.
5. Дренажная задача использует эквивалентный sink вместо явной гидравлической сети труб, коллектора и колодца.
6. Для многофакторного исследования дождя/импеданса нужны более легкие расчетные сетки или план эксперимента, иначе серия 3 x 3 работает долго.
7. Табличные экспериментальные кривые водоудерживания предполагалось хранить в SQLite как часть расчета; формат передачи в PFLOTRAN еще требует отдельного проектного решения.
8. Пара `Голованов-Аверьянов` обозначена как предметная цель, но не доведена до проверенной PFLOTRAN-реализации.

## 15. Что важно сохранить в следующих итерациях

- Не возвращать XLSX как промежуточное хранилище исходных данных.
- Не ломать русские короткие URL: `/ishodnye`, `/status`, `/testy`, `/raschety`, `/grafiki`, `/sistema`.
- Любой новый расчет через интерфейс должен сохранять JSON-снимок в SQLite как новый `расчет №...`.
- При выборе старого расчета поля формы должны заполняться значениями этого расчета.
- Любые новые графики должны иметь расчетные и аналитические профили на одном графике, если для теста есть аналитика.
- Любые новые модели водоудерживания/влагопроводности должны проходить явную валидацию совместимости.
- Для пользовательских путей и имен run обязательно использовать существующие safe helpers.
- Новые комментарии и документация должны быть на русском языке.

## 16. Рекомендуемый следующий план разработки

1. Для релизного состояния выполнить полную пересборку Docker image и сверить ее с hot-copy workflow.
2. Продолжить перенос блоков `soilflow_pflotran.py` в `soilflow_pflotran_modules`: следующий безопасный кандидат - extended analytical rows и profile carrier.
3. Довести расширенные profile carrier тесты до строгих физических deck'ов PFLOTRAN для transport/heat/two-phase/groundwater задач.
4. Добавить API/UI для `soil_curve_tables` и генерацию PFLOTRAN tabular characteristic curves из `soil_curve_points`.
5. Для дренажной задачи вынести исследовательские сценарии в отдельный воспроизводимый runner с параметрическим DOE и сводными картами `Qdrain`, `УГВ`, `C`, `G`, `Z`.
6. Отдельно решить, остается ли регулируемый колодец эквивалентным sink или нужен явный модуль hydraulic network.

## 17. Быстрые команды для нового чата

```bash
cd /home/zenbook/SF/pflotran_soilflow_docker_tested
git status --short
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
curl -fsS http://localhost:18080/api/health
curl -fsS http://localhost:18080/api/health/ready
curl -fsS http://localhost:18080/api/system/info
```

Проверка backend API:

```bash
curl -fsS http://localhost:18080/api/results/runs
curl -fsS http://localhost:18080/api/jobs
curl -fsS "http://localhost:18080/api/calculations"
WEB_PORT=18080 ./scripts/api_smoke.sh
```

Работа внутри контейнера:

```bash
docker exec -it pflotran_soilflow_docker_tested-soilflow-web-1 bash
cd /workspace/output/runs
```

Горячее копирование скриптов в работающий контейнер, если полная пересборка отложена:

```bash
./scripts/sync_to_running_container.sh
```

## 18. Минимальная графическая схема для отрисовки

Для архитектурной схемы нужны следующие узлы и связи:

```text
Browser UI
  -> FastAPI API
  -> SQLite jobs/calculations
  -> JobManager queue
  -> CommandRunner subprocess
  -> soilflow_pflotran.py
  -> PFLOTRAN
  -> run directory
  -> soilflow_visualize.py
  -> plots/html/svg/csv
  -> Browser UI

JSON seed/input workbook
  -> SQLite calculation snapshot
  -> temporary input JSON for run
  -> PFLOTRAN deck

Run directory
  contains:
    pflotran.in
    forcing_daily.csv
    soilflow_run_summary.txt
    run_pflotran.log
    PFLOTRAN *.out/*.tec
    plots/
      profiles_animation.html
      VISUALIZATION_STATUS.txt
      profile/xy/xz csv and svg
```

Этот файл можно использовать как исходное описание для Mermaid, Graphviz или любой другой графической схемы архитектуры.
