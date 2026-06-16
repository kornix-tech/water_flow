# Быстрый старт

Актуальный рабочий режим проекта - web-first: исходные данные редактируются в интерфейсе, сохраняются в SQLite как `расчет №...`, затем backend генерирует JSON-снимок и PFLOTRAN input deck. XLSX не используется как внутреннее хранилище проекта.

## Запуск web-сервиса

```bash
cd /home/zenbook/SF/pflotran_soilflow_docker_tested
WEB_PORT=18080 docker compose up -d soilflow-web
```

Интерфейс:

```text
http://localhost:18080/
```

Основные разделы:

```text
/ishodnye   исходные данные
/status     задания и прогресс
/testy      аналитические и verification-тесты
/raschety   сохраненные расчеты
/grafiki    графики результатов
/sistema    состояние окружения
```

## Проверка здоровья сервиса

```bash
curl -fsS http://localhost:18080/api/health
curl -fsS http://localhost:18080/api/system/info
```

## Локальная проверка проекта

```bash
make project-check
```

Эта команда:

1. компилирует Python-код backend и расчетных скриптов;
2. собирает frontend через Linux `node:20`;
3. удаляет локальный generated `web/frontend/dist`;
4. перезапускает `soilflow-web`;
5. проверяет `/api/health` и `/api/system/info`.

## Синхронизация работающего контейнера без полной пересборки

Если образ уже собран, а изменились только backend/frontend/scripts, можно обновить запущенный контейнер:

```bash
make web-sync
```

Команда собирает frontend, копирует актуальные исходники и `dist` в `/opt/soilflow` внутри контейнера, удаляет локальный generated `dist` и перезапускает контейнер. Для релизной сборки все равно предпочтительна полная пересборка Docker image.

## Запуск тестов

Через web-интерфейс откройте:

```text
http://localhost:18080/testy
```

CLI-вариант:

```bash
make test
```

Результаты расчетов пишутся в runtime workspace контейнера и локальные `output/runs`. Эти файлы считаются generated artifacts и не должны попадать в git.

## Где продолжать разработку

Для восстановления контекста в новом чате используйте:

```text
docs/EXTERNAL_CONTEXT_RU.md
```
