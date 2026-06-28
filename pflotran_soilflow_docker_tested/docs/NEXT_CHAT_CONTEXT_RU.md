# Контекст для продолжения разработки в новом чате

**Проект:** Влагоперенос в почве  
**Дата фиксации:** 2026-06-28  
**Рабочая папка:** `/home/zenbook/SF/pflotran_soilflow_docker_tested`  
**Git root:** `/home/zenbook/SF`  
**Текущий сервис:** `http://localhost:18080/`  
**Контейнер:** `pflotran_soilflow_docker_tested-soilflow-web-1`  
**Базовый commit перед текущим smoke-этапом:** `c685e46 Add typed run status overviews`
**Статус этого handoff:** предназначен для открытия нового чата Codex без восстановления истории из текущего длинного чата.

## 1. Решение по переходу в новый чат

Переход в новый чат **рекомендуется**.

Обоснование:

- текущий чат уже прошел через автоматическое сжатие контекста;
- история разработки стала длинной и содержит несколько крупных этапов: verification-suite, API статусов, frontend карточки состояния, документация, проверки, hot-copy в контейнер;
- предыдущий крупный status-overview этап уже зафиксирован в `c685e46`;
- инструмент не вернул точный остаток token budget, поэтому надежнее считать контекст рискованным для следующих крупных блоков;
- следующий блок лучше начинать с этого файла, `git status`, `git diff --stat` и повторного smoke/check.

Рациональный порядок:

1. В новом чате сначала прочитать этот файл.
2. Проверить `git status --short`.
3. Проверить, что сервис жив: `curl -fsS http://localhost:18080/api/health/ready`.
4. Продолжать с текущего незакоммиченного smoke/doc этапа, если он есть.
5. После проверок зафиксировать новый малый этап отдельным commit.

## 2. Обязательные рабочие правила окружения

В этой Windows/WSL среде надежнее выполнять repo-команды через WSL:

```bash
wsl -d Ubuntu --cd /home/zenbook/SF/pflotran_soilflow_docker_tested -- <command>
```

Не использовать сырые PowerShell heredoc, сложные pipes, `head`, `true`, shell loops и вложенные кавычки на границе PowerShell/WSL. Уже несколько раз PowerShell перехватывал bash-синтаксис. Для сложных shell-конструкций использовать:

```bash
wsl -d Ubuntu --cd /home/zenbook/SF/pflotran_soilflow_docker_tested -- bash -lc "<команда>"
```

Для правок файлов использовать `apply_patch`. Не выполнять `git reset --hard`, `git clean`, force push, массовое удаление результатов без прямого запроса пользователя.

## 3. Текущее состояние репозитория

Крупный status-overview этап зафиксирован и отправлен в `main` commit'ом:

```text
c685e46 Add typed run status overviews
```

Текущий следующий этап: `scripts/api_smoke.sh` проверяет
`GET /api/results/runs/{run_name}/overview` read-only способом без привязки к
конкретному имени run. Связанные документы и этот handoff обновляются вместе со
smoke-правкой.

## 4. Что было сделано после последнего commit

### 4.1 Machine-readable suite summary

Добавлен backend reader для `TEST_SUITE_STATUS.json`, `TEST_SUITE_RESULTS.csv` и fallback на `TEST_SUITE_STATUS.txt`.

Ключевой файл:

```text
web/backend/app/services/test_suite_summary_service.py
```

Endpoint:

```text
GET /api/results/runs/{run_name}/test-suite
```

Назначение:

- отдавать verification-suite как JSON DTO;
- не заставлять frontend парсить TXT;
- безопасно читать только status-artifacts внутри run-директории;
- отвергать symlink и слишком крупные artifacts.

### 4.2 Typed test run status

Добавлен backend reader для отдельных `TEST_STATUS.txt` и `test_diagnostics.json`.

Ключевой файл:

```text
web/backend/app/services/test_run_status_service.py
```

Endpoint:

```text
GET /api/results/runs/{run_name}/test-status
```

Назначение:

- отдавать статус отдельного `_test_*` запуска;
- нормализовать `true/false`, integer и float значения;
- сохранять строки без `=` как `messages`;
- подмешивать `test_diagnostics.json`, если он есть.

Пример проверенного live endpoint:

```text
GET http://localhost:18080/api/results/runs/_test_linear_darcy/test-status
```

Он возвращал `status=PASS`, `test_id=_test_linear_darcy`, checks `pressure/saturation/flux/solver/warning=PASS`, `comparison_points=80`, `q_error_m_s=4.32116333091e-10`.

### 4.3 Shared status artifact safety

Общий helper:

```text
web/backend/app/services/result_status_artifacts.py
```

Ответственность:

- `status_artifact_path(run_dir, filename)`;
- `existing_status_artifact(...)`;
- `existing_status_artifact_names(...)`;
- `parse_key_value_status(...)`.

Инварианты:

- status artifact не должен быть symlink;
- resolved path должен оставаться внутри разрешенной run-директории;
- artifact size limit: `2 MiB`;
- TXT читается с `encoding=utf-8`, `errors=replace`.

### 4.4 Unified run overview

Добавлен агрегирующий backend service:

```text
web/backend/app/services/run_status_overview_service.py
```

Endpoint:

```text
GET /api/results/runs/{run_name}/overview
```

Назначение:

- собрать единый обзор состояния run-директории;
- если есть suite status, добавить карточку `test-suite`;
- если есть test status, добавить карточку `test-run`;
- если есть `plots/VISUALIZATION_STATUS.txt`, добавить карточку `visualization`;
- если status-файлов нет, вернуть fallback `run-files`.

Проверенный live endpoint:

```text
GET http://localhost:18080/api/results/runs/_test_linear_darcy/overview
```

Возвращал карточки:

```text
test-run: PASS, _test_linear_darcy
visualization: PASS, profiles_animation.html
```

### 4.5 Frontend status cards

Добавлен общий компонент:

```text
web/frontend/src/components/StatusSummaryPanel.tsx
```

Он используется:

- на странице `Расчеты` для выбранного run через `/overview`;
- на странице `Статус` для выбранного job, чтобы job/status/run карточки были в одном визуальном стиле.

Связанные frontend файлы:

```text
web/frontend/src/api/client.ts
web/frontend/src/types.ts
web/frontend/src/pages/ResultsPage.tsx
web/frontend/src/pages/JobsPage.tsx
web/frontend/src/styles.css
```

Важно: в `StatusSummaryPanel.tsx` используется `replace(/_/g, "-")`, не `replaceAll`, потому что текущий TS target не поддержал `String.replaceAll`.

## 5. Backend API после изменений

Существующие endpoints сохранены:

```text
GET /api/results/runs
GET /api/results/runs/{run_name}
GET /api/results/runs/{run_name}/status
GET /api/results/runs/{run_name}/plots
GET /api/results/runs/{run_name}/file/{file_path}
```

Новые/расширенные endpoints:

```text
GET /api/results/runs/{run_name}/test-suite
GET /api/results/runs/{run_name}/test-status
GET /api/results/runs/{run_name}/overview
```

DTO добавлены в:

```text
web/backend/app/schemas.py
```

Новые Pydantic модели:

```text
TestSuiteResult
TestSuiteStatus
TestRunStatus
StatusSummaryMetric
StatusSummaryItem
RunStatusOverview
```

## 6. Frontend после изменений

Страница `Расчеты`:

- показывает сохраненные расчеты и standalone run-папки;
- для выбранного run вызывает `getRunStatusOverview(runName)`;
- показывает `StatusSummaryPanel title="Сводка состояния"`;
- ниже оставляет `ResultFileList`;
- кнопки `Открыть исходные данные`, `Запустить заново`, `Удалить` показываются только для SQLite calculation;
- standalone `_test_*` runs не получают неактивные calculation-кнопки.

Страница `Статус`:

- список jobs прежний;
- выбранный job показывается через `StatusSummaryPanel`;
- log viewer сохранен.

Стили:

```text
.status-summary-panel
.status-card-grid
.status-card
.status-card-header
.status-pill
.status-card-metrics
.status-card-footer
```

## 7. Проверки, выполненные после изменений

Последний полный gate прошел успешно:

```bash
./scripts/check_project.sh
```

Состав gate:

```text
[1/7] Python compile
[2/7] Backend unit tests
[3/7] Modular scenario smoke
[4/7] Frontend production build
[5/7] Cleanup generated frontend build
[6/7] Restart web service
[7/7] API contract and workflow checks
```

Итог последнего запуска:

```text
Backend unit tests: 16 tests OK
Core tests: 46 tests OK
Frontend production build: OK
API smoke: OK
tabular API workflow smoke: OK
project checks passed on http://localhost:18080
```

Также отдельно проверялось:

```bash
python3 -m compileall -q web/backend/app web/backend/tests scripts tests
python3 -m unittest discover -s web/backend/tests -v
python3 -m unittest discover -s tests -v
docker run --rm -v /home/zenbook/SF/pflotran_soilflow_docker_tested:/app -w /app/web/frontend node:20 npm run build
./scripts/sync_to_running_container.sh
curl -fsS http://localhost:18080/api/health/ready
curl -fsS http://localhost:18080/api/results/runs/_test_linear_darcy/overview
```

После `check_project.sh` generated local artifacts были очищены:

```bash
git restore -- runs/_test_suite/TEST_SUITE_STATUS.txt
rm -f runs/_test_suite/TEST_SUITE_RESULTS.csv runs/_test_suite/TEST_SUITE_STATUS.json
```

Последний `git diff --check` был чистым.

## 8. Работающий сервис

Текущее состояние контейнера после последней проверки:

```text
pflotran_soilflow_docker_tested-soilflow-web-1 Up
0.0.0.0:18080->8080/tcp
```

Readiness endpoint:

```text
GET http://localhost:18080/api/health/ready
```

Возвращал:

```json
{
  "status": "ready",
  "service": "soilflow-pflotran-web",
  "checks": {
    "pflotran_exe": true,
    "workspace": true,
    "frontend_dist": true,
    "tmp_writable": true,
    "database": true
  },
  "details": {},
  "schema_version": 2
}
```

После hot-copy этапа была выполнена релизная сверка через полный Docker rebuild:

```bash
WEB_PORT=18080 BUILD_JOBS=12 docker compose build soilflow-web
WEB_PORT=18080 docker compose up -d --force-recreate soilflow-web
./scripts/check_project.sh
```

Последний подтвержденный image/container id после UI smoke-этапа:

```text
sha256:c85a40633f540dac09eaeae383bb391b86ac257fd82f1980d5ba9af93a6f3666
```

## 9. Документация, обновленная в этом этапе

```text
CHANGELOG.md
docs/API_CONTRACT_RU.md
docs/EXTERNAL_CONTEXT_RU.md
docs/WEB_INTERFACE_RU.md
```

Смысл изменений:

- добавлены `/test-suite`, `/test-status`, `/overview`;
- добавлен `scripts/ui_route_smoke.sh` и обязательный `[8/8] Frontend route smoke` в `scripts/check_project.sh`;
- зафиксировано, что frontend больше не парсит status TXT напрямую;
- описан общий reader status-сводок;
- web smoke examples дополнены curl-командами для новых endpoints.

## 10. Архитектурная карта текущего results/status слоя

```mermaid
flowchart LR
  RunDir["/workspace/output/runs/<run_name>"] --> SuiteTxt["TEST_SUITE_STATUS.txt/json/csv"]
  RunDir --> TestTxt["TEST_STATUS.txt + test_diagnostics.json"]
  RunDir --> PlotStatus["plots/VISUALIZATION_STATUS.txt"]

  SuiteTxt --> SuiteReader["test_suite_summary_service.py"]
  TestTxt --> TestReader["test_run_status_service.py"]
  PlotStatus --> OverviewReader["run_status_overview_service.py"]
  SuiteReader --> OverviewReader
  TestReader --> OverviewReader

  OverviewReader --> ResultsRouter["results.py /api/results/runs/{run}/overview"]
  ResultsRouter --> ApiClient["frontend api/client.ts"]
  ApiClient --> StatusPanel["StatusSummaryPanel.tsx"]
  StatusPanel --> ResultsPage["/raschety"]
  StatusPanel --> JobsPage["/status"]
```

## 11. Текущие риски и ограничения

1. Текущий smoke/doc diff нужно закоммитить после `check_project.sh`.
2. Docker image может отставать от исходников, потому что использовался hot-copy workflow.
3. В `output/runs` и Docker volume есть много generated расчетных результатов; не добавлять их в git.
4. `runs/_test_suite/TEST_SUITE_STATUS.txt` является tracked/generated baseline и может меняться после test dry-runs. После проверок его нужно восстанавливать, если он попал в `git status`.
5. Endpoint `/overview` покрыт unit-тестами и добавлен в `scripts/api_smoke.sh`.
6. Старые endpoints `/test-suite` и `/test-status` оставлены для совместимости и прямого анализа; не удалять их без отдельного решения.

## 12. Рекомендуемый следующий план

### Блок A. API smoke для overview

Выполнено в текущем smoke-этапе:

- `scripts/api_smoke.sh` выбирает первый run с `has_test_status`,
  `has_suite_status` или `has_visualization`;
- если status/visualization run отсутствует, проверяет `/overview` для первой
  обычной run-папки;
- если run-папок нет, пропускает overview-проверку с явным сообщением;
- проверяет базовую форму DTO: `run_name`, непустой `items`, обязательные поля
  `kind/title/status` у каждой карточки.

### Блок B. UI route smoke

Выполнено в текущем UI smoke-этапе:

- добавлен `scripts/ui_route_smoke.sh`;
- добавлена Makefile-цель `ui-smoke`;
- `scripts/check_project.sh` расширен до `[1/8]...[8/8]` и запускает UI route
  smoke после API/workflow проверок;
- smoke проверяет `/`, `/ishodnye`, `/status`, `/testy`, `/raschety`,
  `/grafiki`, `/sistema`, основные JS/CSS assets и JSON 404 для неизвестного
  `/api/...` маршрута.

Более глубокий browser smoke для `/raschety` можно добавить отдельно:

- открыть `http://localhost:18080/raschety`;
- проверить заголовок `Расчеты`;
- если есть `_test_suite` или `_test_linear_darcy`, выбрать run и проверить `Сводка состояния`;
- не делать это обязательным в shell CI, если нет Playwright зависимости.

### Блок C. Следующий архитектурный шаг

После фиксации status overview можно продолжать:

- добавить строгие evaluator-модули для profile-smoke benchmarks;
- при необходимости добавить полноценный browser smoke с Playwright или отдельным инструментом;
- полный Docker rebuild gate уже был выполнен после `d955c6b`;
- затем переходить к следующей физической/исследовательской модели.

## 13. Что нельзя потерять

- XLSX не должен вернуться как внутреннее хранилище исходных данных.
- PFLOTRAN остается заменяемым solver adapter, не смешивать solver logic с frontend/API.
- Новые status endpoints не должны читать произвольные файлы вне run-директории.
- Новые UI элементы должны быть на русском языке.
- Короткие URL должны сохраняться:

```text
/ishodnye
/status
/testy
/raschety
/grafiki
/sistema
```

- Для новых тестов сохранять уровни:

```text
strict_analytical
partial_balance
profile_smoke
workflow_smoke
```

## 14. Минимальная инструкция для нового чата

Новый чат можно начать так:

```text
Работай в проекте /home/zenbook/SF/pflotran_soilflow_docker_tested.
Сначала прочитай docs/NEXT_CHAT_CONTEXT_RU.md и docs/EXTERNAL_CONTEXT_RU.md.
Проверь git status и текущее состояние сервиса.
Дальше продолжай с блока: если UI smoke-этап не закоммичен, проверить
`git status`, запустить `./scripts/check_project.sh`, очистить generated
artifacts `runs/_test_suite`, затем commit/push.
Работай через WSL bash, не через PowerShell heredoc/pipes.
```
