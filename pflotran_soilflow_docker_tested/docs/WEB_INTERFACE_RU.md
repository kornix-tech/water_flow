# Web-интерфейс SoilFlow/PFLOTRAN

## Назначение

Web-режим поднимает единый Docker-контейнер с PFLOTRAN/PETSc, Python-скриптами, FastAPI backend, SQLite-хранилищем расчетов/jobs и собранным React/Vite frontend. Пользователь работает через браузер: заполняет исходные данные, сохраняет их как `расчет №...`, запускает demo и verification-тесты, смотрит статусы, логи, результаты, графики и скачивает ZIP расчёта.

## Запуск в WSL

```bash
make web-build
make web-up
make web-open
```

Открыть:

```text
http://localhost:8080
```

Если `make` не установлен, используйте прямые команды:

```bash
docker compose build soilflow-web
docker compose up -d soilflow-web
```

## Запуск на VDS

```bash
docker compose up -d
```

Открыть:

```text
http://<server-ip>:8080
```

Для VDS не публикуйте web-интерфейс в открытый интернет без token-режима, HTTPS или reverse proxy.

## Основные страницы и URL

- `/` — `Обзор`: статус сервера, PFLOTRAN и быстрые кнопки запуска.
- `/ishodnye` — `Исходные данные`: многовкладочное редактирование параметров проекта, сетки, почвы, граничных условий, solver-а и погодного форсинга.
- `/zadachi` — `Задания`: очередь задач, статусы, просмотр логов и отмена выполняемого задания.
- `/testy` — `Тесты`: запуск всех verification-тестов и отдельных тестов.
- `/rezultaty` — `Результаты`: список `/workspace/output/runs`, файлы и ZIP результата.
- `/grafiki` — `Графики`: генерация и просмотр `profiles_animation.html`.
- `/sistema` — `Система`: пути контейнера, workspace, PFLOTRAN и режим авторизации.

Старые URL первого web-этапа (`/vvod`, `/jobs`, `/results`, `/visualization` и т.п.) остаются совместимыми на уровне frontend и автоматически заменяются на короткие русскоязычные slug-адреса.

## Исходные данные

Страница `Исходные данные` редактирует JSON-снимок исходных данных через API:

- вкладки `Проект`, `Область и сетка`, `Почва`, `Начальные и граничные условия`, `Время и форсинг`, `ET и корни`, `Полив и дренаж`, `Грунтовые воды`, `Solver` соответствуют листам `01_Project`–`09_Solver`;
- вкладка `Погода` редактирует строки листа `10_Weather_Daily`;
- кнопка `Сохранить` создает новую запись `расчет №...` в SQLite;
- выбор старого расчета подставляет его параметры обратно в поля ввода;
- запуск расчета использует JSON-снимок выбранной записи, а не XLSX-файл.

## Где хранятся данные

Все пользовательские данные web-режима лежат в volume:

```text
/workspace
  input/
  output/runs/
  uploads/
  jobs/
  archives/
  tmp/
  jobs.sqlite
```

## API-проверка

```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/system/info
curl -X POST http://localhost:8080/api/jobs/run-test-suite
curl http://localhost:8080/api/jobs
curl http://localhost:8080/api/results/runs
curl http://localhost:8080/api/results/runs/_test_suite/test-suite
curl http://localhost:8080/api/results/runs/_test_linear_darcy/test-status
curl http://localhost:8080/api/results/runs/_test_linear_darcy/overview
```

## Backup

```bash
docker run --rm \
  -v soilflow_workspace:/data \
  -v "$PWD":/backup \
  alpine tar czf /backup/soilflow_workspace_backup.tar.gz -C /data .
```

## Безопасность

По умолчанию для локального WSL используется:

```text
SOILFLOW_AUTH_MODE=none
```

Для VDS включите token-режим:

```yaml
environment:
  SOILFLOW_AUTH_MODE: token
  SOILFLOW_API_TOKEN: "<секретный токен>"
```

Токен не должен попадать в git, README, changelog или примеры с реальными значениями.

Дополнительные защитные настройки:

```yaml
environment:
  SOILFLOW_MAX_ARCHIVE_MB: 2048
  SOILFLOW_MAX_ARCHIVE_FILES: 20000
  SOILFLOW_JOB_TIMEOUT_SECONDS: 21600
  SOILFLOW_API_RATE_LIMIT_PER_MINUTE: 120
  SOILFLOW_MAX_JSON_BODY_KB: 512
  SOILFLOW_ENABLE_API_DOCS: false
  SOILFLOW_ENABLE_HSTS: false
```

Web API отдаёт файлы только из пользовательских областей `input`, `uploads` и `output/runs`. HTML-графики открываются в sandboxed iframe; прямой HTML-ответ для графиков также получает CSP sandbox-заголовок.

В token-режиме frontend хранит токен только в `sessionStorage`, отправляет его в заголовке `Authorization: Bearer ...` и не добавляет токен в URL. Поэтому скачивание ZIP/файлов расчёта и открытие HTML-графиков выполняются через authenticated fetch, а не через прямые публичные ссылки.

`SOILFLOW_ENABLE_HSTS=true` включайте только за HTTPS reverse proxy. Для локального HTTP/WSL оставляйте `false`.

## Текущие ограничения

- Один пользователь, один контейнер, локальная очередь jobs.
- `JOB_WORKERS=1` по умолчанию, чтобы не запускать несколько тяжёлых PFLOTRAN-расчётов одновременно.
- XLSX не используется как внутреннее хранилище проекта; допустим только будущий экспорт/legacy-обмен.
- WebSocket не используется; frontend делает обычный polling `/api/jobs/{job_id}`.
- Production frontend отдаётся FastAPI как static bundle, Vite dev-server в контейнере не запускается.
