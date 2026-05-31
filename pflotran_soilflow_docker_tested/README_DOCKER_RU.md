# SoilFlow PFLOTRAN Docker Kit

Переносимый Docker-пакет для демонстрационного расчёта влагопереноса в почве на основе уравнения Ричардса с внешним FVM-решателем PFLOTRAN.

Пакет рассчитан на ваш сценарий: Windows → WSL Ubuntu 24.04 → Docker. Собирать и запускать его нужно из терминала WSL/Ubuntu.

## 1. Что входит в пакет

```text
Dockerfile                         сборка автономного образа с PETSc + PFLOTRAN + Python
requirements.txt                   Python-зависимости внутри контейнера
VERSIONS.lock                      версии по умолчанию
README_DOCKER_RU.md                эта инструкция
docker-compose.yml                 альтернативный запуск через compose

docker/
  build_image.sh                   сборка Docker image
  run_demo.sh                      запуск демонстрационного расчёта
  check_image.sh                   проверка контейнера
  shell.sh                         интерактивный shell внутри контейнера
  save_image.sh                    экспорт образа в переносимый tar.gz
  load_image.sh                    импорт образа из tar.gz
  entrypoint.sh                    entrypoint контейнера
  check_container.sh               внутренняя проверка контейнера

scripts/
  soilflow_pflotran.py             XLSX → PFLOTRAN input → запуск PFLOTRAN

input/
  soilflow_pflotran_demo.xlsx      тестовые исходные данные

docs/
  README_STARTER_RU.md             исходная инструкция Windows/WSL-версии
```

## 2. Принцип автономности

Первичная сборка образа требует интернет-доступа, потому что Dockerfile скачивает PETSc, PFLOTRAN и Python-пакеты.

После успешного `docker build` образ уже содержит:

```text
PFLOTRAN executable
PETSc
MPI
HDF5/BLAS/LAPACK/METIS/ParMETIS, собранные через PETSc
Python 3
openpyxl/numpy/pandas/h5py/matplotlib/PyYAML
Python-код обвязки
XLSX с тестовой задачей
```

После этого образ можно сохранить командой `docker/save_image.sh`, перенести как `.tar.gz` на другую машину той же архитектуры и запускать без повторного скачивания исходников.

## 3. Быстрый запуск в WSL Ubuntu 24.04

Из WSL перейдите в папку пакета:

```bash
cd /path/to/pflotran_soilflow_docker
chmod +x docker/*.sh
```

Соберите образ:

```bash
docker/build_image.sh
```

Проверьте контейнер:

```bash
docker/check_image.sh
```

Запустите демонстрационный расчёт:

```bash
docker/run_demo.sh
```

Результаты появятся в папке:

```text
output/demo_richards/
```

Минимально там будут:

```text
pflotran.in
forcing_daily.csv
soilflow_run_summary.txt
run_pflotran.log
```

При успешном PFLOTRAN-запуске появятся также output-файлы PFLOTRAN.

## 4. Запуск через docker compose

```bash
docker compose build
mkdir -p output
docker compose run --rm soilflow-pflotran
```

## 5. Экспорт переносимого образа

После сборки:

```bash
docker/save_image.sh
```

Будет создано:

```text
portable_image/soilflow-pflotran_local.tar.gz
portable_image/soilflow-pflotran_local.tar.gz.sha256
```

Перенос на другую машину:

```bash
scp portable_image/soilflow-pflotran_local.tar.gz user@host:/path/
```

Загрузка на другой машине:

```bash
docker/load_image.sh portable_image/soilflow-pflotran_local.tar.gz
```

Запуск после загрузки:

```bash
docker run --rm -v "$PWD/output:/workspace/output" soilflow-pflotran:local demo
```

## 6. Интерактивный режим

```bash
docker/shell.sh
```

Внутри контейнера:

```bash
which pflotran
soilflow-check
python3 /workspace/soilflow/scripts/soilflow_pflotran.py \
  --xlsx /workspace/soilflow/input/soilflow_pflotran_demo.xlsx \
  --workdir /workspace/output/manual_case \
  --run \
  --pflotran-exe /usr/local/bin/pflotran
```

## 7. Изменение исходных данных

Тестовый XLSX лежит внутри образа:

```text
/workspace/soilflow/input/soilflow_pflotran_demo.xlsx
```

Для пользовательских входных данных удобнее смонтировать папку снаружи:

```bash
mkdir -p cases output
cp input/soilflow_pflotran_demo.xlsx cases/my_case.xlsx

docker run --rm \
  -v "$PWD/cases:/workspace/cases" \
  -v "$PWD/output:/workspace/output" \
  soilflow-pflotran:local generate \
  --xlsx /workspace/cases/my_case.xlsx \
  --workdir /workspace/output/my_case \
  --run \
  --pflotran-exe /usr/local/bin/pflotran
```

## 8. Версии и переопределение сборки

По умолчанию используются:

```text
Ubuntu:        24.04
PETSc:         v3.24.5
PETSC_ARCH:    linux-opt
PFLOTRAN ref:  master
```

Переопределение:

```bash
PETSC_VERSION=v3.24.5 PFLOTRAN_REF=master docker/build_image.sh
```

Если на конкретной машине сборка на Ubuntu 24.04 даст ошибку компилятора или внешнего пакета, можно попробовать базовый образ Ubuntu 22.04:

```bash
UBUNTU_VERSION=22.04 docker/build_image.sh
```

## 9. Ограничения текущей демонстрационной задачи

Текущий Python-адаптер генерирует минимальный PFLOTRAN input deck для `RICHARDS` mode:

```text
structured grid 1D/2D/3D через NXYZ/DXYZ
один материал soil
van Genuchten saturation function
Mualem relative permeability
верхняя Neumann flux boundary
нижняя hydrostatic/no-flow/constant-pressure логика
initial hydrostatic pressure
```

В XLSX уже есть параметры для внешней ET/T-модели, корневого водопотребления, полива, дренажа и динамических грунтовых вод. В минимальном demo они пока не превращаются в полноценные time-dependent `SOURCE_SINK`/drain boundary. Это следующий этап развития адаптера.

## 10. Рекомендуемый следующий этап разработки

```text
1. Добавить time-dependent верхний flux из Weather_Daily вместо среднего flux.
2. Добавить SOURCE_SINK для root uptake по корневой зоне.
3. Добавить дренаж как sink или boundary patch.
4. Добавить динамический water-table boundary condition.
5. Добавить 2D пример с tile drain.
6. Добавить парсер PFLOTRAN output для водного баланса.
```

## 11. Полезные официальные источники

```text
PFLOTRAN Linux installation:
https://www.pflotran.org/documentation/user_guide/how_to/installation/linux.html

PFLOTRAN simple flow problem:
https://www.pflotran.org/documentation/user_guide/how_to/simple_flow_problem.html

PETSc install:
https://petsc.org/main/install/

PFLOTRAN repository:
https://bitbucket.org/pflotran/pflotran
```

## Верификационный режим `_test`

Для первого запуска добавлен тест стационарной линеаризованной колонки Ричардса/Дарси. Параметры находятся в XLSX на листе `_test`.

```bash
docker/run_test.sh
```

или:

```bash
make test
```

Тест создаёт аналитический профиль `analytical_solution.csv`, запускает PFLOTRAN и затем формирует `TEST_STATUS.txt`, `test_comparison.csv` и `test_comparison.svg`.
Подробности см. `docs/TEST_LINEARIZED_COLUMN_RU.md`.
