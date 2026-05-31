# Запуск SoilFlow/PFLOTRAN Docker-пакета в WSL 2 Ubuntu 24.04

Эта инструкция начинается со следующих вводных:

```text
Windows уже установлен.
WSL 2 уже установлен.
В WSL уже есть дистрибутив Ubuntu 24.04.
В Ubuntu 24.04 уже установлен Docker.
```

Цель инструкции — собрать автономный Docker-образ с PFLOTRAN, PETSc, Python-адаптером и тестовыми исходными данными, затем выполнить первый верификационный расчёт `_test` и демонстрационный расчёт `demo`.

---

## 1. Открыть Ubuntu 24.04 в WSL

Откройте меню Windows и запустите:

```text
Ubuntu 24.04
```

Все дальнейшие команды выполняются в терминале Ubuntu, а не в PowerShell Windows.

---

## 2. Проверить, что Docker доступен из Ubuntu

В терминале Ubuntu выполните:

```bash
docker --version
docker ps
```

Если обе команды сработали без ошибки `permission denied`, переходите к следующему разделу.

Если появляется ошибка вида:

```text
permission denied while trying to connect to the Docker daemon socket
```

добавьте своего пользователя в группу `docker`:

```bash
sudo usermod -aG docker $USER
```

После этого полностью закройте Ubuntu. Затем в PowerShell Windows выполните:

```powershell
wsl --shutdown
```

Снова откройте Ubuntu 24.04 и проверьте:

```bash
docker ps
```

Если Docker установлен, но сервис не запущен, попробуйте:

```bash
sudo service docker start
```

Затем снова:

```bash
docker ps
```

---

## 3. Установить только недостающие служебные утилиты

WSL и Docker у вас уже есть, поэтому ставим только базовые инструменты для распаковки и запуска проекта:

```bash
sudo apt update
sudo apt install -y unzip make ca-certificates curl git
```

Проверьте:

```bash
unzip -v | head -n 2
make --version | head -n 1
```

---

## 4. Создать рабочую папку внутри Linux-файловой системы WSL

Рекомендуется работать в домашней папке Ubuntu, а не в `/mnt/c/...`. Так Docker-сборка и работа с большим количеством файлов обычно идут стабильнее.

```bash
mkdir -p ~/projects
cd ~/projects
```

---

## 5. Скопировать ZIP-пакет проекта в WSL

Актуальный архив проекта:

```text
pflotran_soilflow_docker_tested.zip
```

Если вы скачали его через браузер Windows, обычно он лежит в папке `Downloads` вашего Windows-пользователя.

Сначала посмотрите список пользователей Windows:

```bash
ls /mnt/c/Users
```

Затем скопируйте архив. Замените `<WINDOWS_USER>` на имя вашего пользователя Windows:

```bash
cp /mnt/c/Users/<WINDOWS_USER>/Downloads/pflotran_soilflow_docker_tested.zip ~/projects/
```

Пример:

```bash
cp /mnt/c/Users/Ivan/Downloads/pflotran_soilflow_docker_tested.zip ~/projects/
```

Если архив уже лежит внутри Ubuntu, просто перейдите в папку, где он находится.

Проверьте наличие архива:

```bash
ls -lh ~/projects/pflotran_soilflow_docker_tested.zip
```

---

## 6. Распаковать проект

```bash
cd ~/projects
unzip pflotran_soilflow_docker_tested.zip
cd pflotran_soilflow_docker_tested
```

Проверьте структуру:

```bash
ls
```

Ожидаемые элементы:

```text
Dockerfile
Makefile
README_RU.md
input/
scripts/
docker/
docs/
output/
```

---

## 7. Разрешить запуск shell-скриптов

```bash
chmod +x scripts/*.sh docker/*.sh
```

Если при запуске скриптов позже появится ошибка вида `bad interpreter` или `^M`, значит файл получил Windows-переносы строк. Исправьте так:

```bash
sudo apt install -y dos2unix
dos2unix scripts/*.sh docker/*.sh
chmod +x scripts/*.sh docker/*.sh
```

---

## 8. Собрать Docker-образ

Основная команда:

```bash
make build
```

Она создаёт Docker-образ:

```text
soilflow-pflotran:local
```

На стадии сборки Docker скачивает и компилирует PETSc и PFLOTRAN внутри образа. После успешной сборки контейнер становится переносимым: для обычного запуска расчётов интернет уже не нужен.

Если компьютер ограничен по памяти, уменьшите число параллельных процессов сборки:

```bash
BUILD_JOBS=2 make build
```

Если снова возникают ошибки памяти:

```bash
BUILD_JOBS=1 make build
```

Проверьте, что образ создан:

```bash
docker images | grep soilflow-pflotran
```

---

## 9. Проверить контейнер

После сборки выполните:

```bash
make check
```

Ожидаемое завершение — без ошибок. Эта команда проверяет, что внутри контейнера доступны Python-зависимости, PFLOTRAN и служебные пути.

---

## 10. Выполнить `_test`: аналитическая проверка численного решения

Первый обязательный запуск — режим `_test`:

```bash
make test
```

Этот тест моделирует лабораторную почвенную колонку с однородной изотропной насыщенной почвой и сравнивает численный результат PFLOTRAN с аналитическим линейным решением закона Дарси для стационарного потока.

Результаты пишутся в папку:

```text
output/runs/_test_linear_darcy/
```

Проверьте статус:

```bash
cat output/runs/_test_linear_darcy/TEST_STATUS.txt
```

Посмотрите файлы результата:

```bash
ls -lh output/runs/_test_linear_darcy/
```

Основные файлы:

```text
pflotran.in
analytical_solution.csv
analytical_test_summary.txt
run_pflotran.log
TEST_STATUS.txt
test_comparison.csv
test_comparison.svg
```

Откройте папку результата в проводнике Windows:

```bash
explorer.exe output/runs/_test_linear_darcy
```

Файл `test_comparison.svg` можно открыть в браузере. Он показывает сравнение аналитического и численного профилей.

---

## 11. Если нужно проверить генерацию `_test` без запуска PFLOTRAN

Эта команда только генерирует входные файлы и аналитическое решение, но не запускает PFLOTRAN:

```bash
make dry-test
```

Результат будет в:

```text
output/runs/_test_linear_darcy_dryrun/
```

Это полезно, если вы хотите проверить чтение XLSX, генерацию `pflotran.in` и аналитического CSV отдельно от численного solver-а.

---

## 12. Выполнить демонстрационный расчёт `demo`

После успешного `_test` запустите демонстрационный сценарий:

```bash
make run
```

Результаты:

```text
output/runs/demo_richards/
```

Проверьте:

```bash
ls -lh output/runs/demo_richards/
cat output/runs/demo_richards/soilflow_run_summary.txt
```

Открыть папку результата в Windows:

```bash
explorer.exe output/runs/demo_richards
```

---

## 13. Изменить исходные данные XLSX

Файл исходных данных:

```text
input/soilflow_pflotran_demo.xlsx
```

Откройте папку с ним из Ubuntu в проводнике Windows:

```bash
explorer.exe input
```

Откройте XLSX в Excel или LibreOffice, измените параметры, сохраните файл и закройте редактор.

После изменения файла снова выполните:

```bash
make test
```

или:

```bash
make run
```

Важно: перед запуском закройте XLSX в Excel, чтобы файл не был заблокирован.

---

## 14. Запустить расчёт с явным указанием XLSX и папки результата

Для `_test`:

```bash
scripts/run_test_docker.sh input/soilflow_pflotran_demo.xlsx /work/runs/my_test_case
```

Результаты появятся в:

```text
output/runs/my_test_case/
```

Для `demo`:

```bash
scripts/run_demo_docker.sh input/soilflow_pflotran_demo.xlsx /work/runs/my_demo_case
```

Результаты появятся в:

```text
output/runs/my_demo_case/
```

---

## 15. Войти внутрь контейнера

Для диагностики:

```bash
make shell
```

Внутри контейнера можно проверить:

```bash
python3 --version
which pflotran
pflotran -help | head
```

Выйти из контейнера:

```bash
exit
```

---

## 16. Очистить результаты расчётов

Удалить содержимое `output/`:

```bash
make clean
```

Проверить место, занятое Docker:

```bash
docker system df
```

Осторожная очистка неиспользуемых Docker-объектов:

```bash
docker system prune
```

Не используйте агрессивную очистку, если у вас есть другие важные Docker-образы и контейнеры.

---

## 17. Сохранить Docker-образ для переноса на другой компьютер

После успешной сборки:

```bash
make save
```

Будет создан файл:

```text
soilflow-pflotran-image.tar
```

Его можно перенести на другой компьютер.

На другом компьютере с Docker:

```bash
docker load -i soilflow-pflotran-image.tar
```

После загрузки образа обычные расчёты можно запускать без повторной сборки.

---

## 18. Самый короткий сценарий первого запуска

Если Docker уже работает, а архив лежит в `~/projects`:

```bash
cd ~/projects
unzip pflotran_soilflow_docker_tested.zip
cd pflotran_soilflow_docker_tested
chmod +x scripts/*.sh docker/*.sh

make build
make check
make test
cat output/runs/_test_linear_darcy/TEST_STATUS.txt

make run
ls -lh output/runs/demo_richards/
```

Если эти команды прошли, проект установлен, Docker-образ собран, PFLOTRAN работает, аналитический `_test` выполнен, и можно переходить к изменению XLSX и развитию модели.

---

## 19. Типовые ошибки и быстрые решения

### Ошибка: `docker: permission denied`

Решение:

```bash
sudo usermod -aG docker $USER
```

Затем закрыть Ubuntu, в PowerShell выполнить:

```powershell
wsl --shutdown
```

и открыть Ubuntu снова.

---

### Ошибка: `make: command not found`

Решение:

```bash
sudo apt update
sudo apt install -y make
```

---

### Ошибка: `unzip: command not found`

Решение:

```bash
sudo apt update
sudo apt install -y unzip
```

---

### Ошибка при сборке из-за памяти

Попробуйте:

```bash
BUILD_JOBS=2 make build
```

или:

```bash
BUILD_JOBS=1 make build
```

---

### Ошибка: `bad interpreter: /bin/bash^M`

Решение:

```bash
sudo apt install -y dos2unix
dos2unix scripts/*.sh docker/*.sh
chmod +x scripts/*.sh docker/*.sh
```

---

### `_test` не создал `TEST_STATUS.txt`

Проверьте лог PFLOTRAN:

```bash
cat output/runs/_test_linear_darcy/run_pflotran.log
```

Проверьте, что входной файл создан:

```bash
ls -lh output/runs/_test_linear_darcy/pflotran.in
```

Проверьте контейнер:

```bash
make check
```

---

## 20. Логика запуска в одном абзаце

Проект читает параметры из XLSX, Python-адаптер генерирует входной файл `pflotran.in`, Docker-контейнер запускает PFLOTRAN в режиме `RICHARDS`, затем результаты сохраняются в `output/`. Режим `_test` дополнительно строит аналитическое решение для линеаризованной стационарной фильтрации в колонке и сравнивает его с численным результатом.
