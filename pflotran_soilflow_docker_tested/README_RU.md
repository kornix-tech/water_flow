# SoilFlow/PFLOTRAN Docker kit

Автономный Docker-комплект для демонстрационного расчёта влагопереноса в почве на основе уравнения Ричардса с использованием PFLOTRAN как внешнего FVM-решателя.

Комплект рассчитан на ваш сценарий: Windows → WSL Ubuntu 24.04 → Docker. После сборки образ содержит PFLOTRAN, PETSc, Python-адаптер, XLSX-шаблон исходных данных и демонстрационный сценарий. Интернет нужен только на стадии `docker build`; запуск расчёта можно выполнять с `--network none`.

## 1. Состав пакета

```text
Dockerfile                                      сборка PETSc + PFLOTRAN + Python-адаптер
Makefile                                        короткие команды make build/run/check/shell/save
docker-compose.yml                              альтернативный запуск через compose
README_RU.md                                    эта инструкция

docker/
  entrypoint.sh                                 точка входа контейнера

scripts/
  build_image.sh                                сборка Docker-образа
  run_demo_docker.sh                            запуск demo без сети
  dry_run_docker.sh                             только генерация pflotran.in без запуска PFLOTRAN
  shell_in_container.sh                         интерактивный shell внутри образа
  save_image.sh                                 экспорт готового образа в .tar
  load_image.sh                                 импорт образа из .tar
  clean_output.sh                               очистка output/runs
  soilflow_pflotran.py                          XLSX → PFLOTRAN input → запуск PFLOTRAN

input/
  soilflow_pflotran_demo.xlsx                   синтетические входные данные

output/
  .gitkeep                                      папка для результатов; монтируется в контейнер как /work

docs/
  ARCHITECTURE_RU.md                            пояснение программной архитектуры
  LICENSE_NOTES_RU.md                           лицензионные замечания
```

## 2. Что делает контейнер

Внутри образа находятся:

```text
/opt/petsc                                      PETSc, собранный при docker build
/opt/pflotran                                   PFLOTRAN, собранный при docker build
/opt/soilflow/scripts/soilflow_pflotran.py      Python-адаптер
/opt/soilflow/input/soilflow_pflotran_demo.xlsx XLSX demo input
/work                                           рабочая папка расчёта
```

По умолчанию контейнер выполняет:

```text
1. читает XLSX;
2. генерирует /work/runs/demo_richards/pflotran.in;
3. генерирует /work/runs/demo_richards/forcing_daily.csv;
4. генерирует /work/runs/demo_richards/soilflow_run_summary.txt;
5. запускает PFLOTRAN;
6. сохраняет лог и output-файлы PFLOTRAN в /work/runs/demo_richards.
```

## 3. Быстрый старт в WSL Ubuntu 24.04

Откройте терминал WSL Ubuntu 24.04, распакуйте архив и перейдите в папку проекта:

```bash
cd /path/to/pflotran_soilflow_docker
```

Разрешите выполнение shell-скриптов, если архив распакован без executable-битов:

```bash
chmod +x scripts/*.sh docker/entrypoint.sh
```

Соберите образ:

```bash
./scripts/build_image.sh
```

или через Makefile:

```bash
make build
```

Запустите демонстрационный расчёт:

```bash
./scripts/run_demo_docker.sh
```

или:

```bash
make run
```

Результаты будут здесь:

```text
output/runs/demo_richards/
```

Минимально должны появиться:

```text
pflotran.in
forcing_daily.csv
soilflow_run_summary.txt
run_pflotran.log
```

При успешном PFLOTRAN-расчёте появятся также output-файлы PFLOTRAN, например `.out` и `.tec`.

## 4. Проверка контейнера

После сборки:

```bash
docker run --rm soilflow-pflotran:local check
```

Команда проверит наличие Python, PFLOTRAN executable, `mpirun` и выполнит сухую генерацию входного файла.

## 5. Запуск без доступа к интернету

Скрипт `run_demo_docker.sh` уже запускает контейнер с:

```bash
--network none
```

Это проверяет, что образ не требует сети на стадии расчёта.

Ручной эквивалент:

```bash
docker run --rm -it \
  --network none \
  -v "$PWD/output:/work" \
  soilflow-pflotran:local
```

## 6. Запуск с собственным XLSX

Положите новый XLSX рядом с demo-файлом, например:

```text
input/my_case.xlsx
```

Запустите:

```bash
./scripts/run_demo_docker.sh input/my_case.xlsx /work/runs/my_case
```

Результаты будут в:

```text
output/runs/my_case/
```

## 7. Только генерация PFLOTRAN input без расчёта

```bash
./scripts/dry_run_docker.sh
```

или:

```bash
make dry-run
```

Это полезно для проверки `pflotran.in`, даже если PFLOTRAN-расчёт нужно запускать отдельно.

## 8. Интерактивная работа внутри контейнера

```bash
./scripts/shell_in_container.sh
```

Проверить PFLOTRAN:

```bash
which pflotran
ls -lh /opt/pflotran/src/pflotran/pflotran
```

Ручной запуск расчёта внутри контейнера:

```bash
cd /work/runs/demo_richards
mpirun -n 1 pflotran -pflotranin pflotran.in
```

## 9. Перенос готового образа на другой компьютер

После сборки можно сохранить готовый образ:

```bash
./scripts/save_image.sh
```

Будет создан файл:

```text
soilflow-pflotran-image.tar
```

На другом компьютере:

```bash
docker load -i soilflow-pflotran-image.tar
```

После этого demo можно запускать без повторной сборки.

## 10. Настройка версий при сборке

По умолчанию используются:

```text
Ubuntu:        24.04
PETSc:         v3.24.5
PETSC_ARCH:    linux-gnu-c-opt
PFLOTRAN ref:  master
Docker tag:    soilflow-pflotran:local
```

Переопределение:

```bash
PETSC_VERSION=v3.24.5 \
PFLOTRAN_GIT_REF=master \
BUILD_JOBS=8 \
IMAGE_NAME=soilflow-pflotran:dev \
./scripts/build_image.sh
```

PFLOTRAN в официальной Linux-инструкции указывает PETSc `v3.24.5` и конфигурацию PETSc с `--download-mpich`, `--download-hdf5`, `--download-fblaslapack`, `--download-metis`, `--download-parmetis`; Dockerfile следует этой логике.

## 11. XLSX-файл исходных данных

Файл:

```text
input/soilflow_pflotran_demo.xlsx
```

содержит русскоязычные листы с параметрами, единицами измерения и пояснениями физического смысла. В демо заполнены правдоподобные синтетические данные для условной 1D почвенной колонки.

Основные листы:

```text
00_README
01_Project
02_Domain
03_Soil
04_Initial_BC
05_Time_Forcing
06_ET_Roots
07_Irrigation_Drainage
08_Groundwater
09_Solver
10_Weather_Daily
11_Derived_Checks
```

Сейчас Python-адаптер читает машинно-значимые пары:

```text
Parameter → Value
```

а также суточный форсинг с листа `10_Weather_Daily`.

## 12. Текущее физическое содержание demo

Demo генерирует PFLOTRAN input deck для:

```text
SIMULATION_TYPE SUBSURFACE
MODE RICHARDS
structured grid
van Genuchten saturation function
Mualem relative permeability
верхняя граница LIQUID_FLUX NEUMANN
нижняя граница HYDROSTATIC / CONSTANT_PRESSURE / NO_FLOW по XLSX
TECPLOT POINT output
```

Верхний поток в первом demo упрощённо считается как среднее за период:

```text
precipitation + irrigation - potential_soil_evaporation
```

Корневое водопотребление, динамические грунтовые воды и дренаж уже присутствуют в XLSX и архитектурном контракте, но в текущем минимальном `pflotran.in` пока не активированы как полноценные time-dependent `SOURCE_SINK`/drain boundary. Это следующий слой разработки.

## 13. Связь с официальной документацией PFLOTRAN

Полезные страницы:

```text
https://www.pflotran.org/documentation/user_guide/how_to/installation/linux.html
https://www.pflotran.org/documentation/user_guide/how_to/installation/previous_petsc_releases.html
https://www.pflotran.org/documentation/user_guide/how_to/running.html
https://www.pflotran.org/documentation/user_guide/how_to/simple_flow_problem.html
https://documentation.pflotran.org/
```

PFLOTRAN запускает расчёт из input deck `.in`; официальный пример команды использует `mpirun -n 1 ... -pflotranin myinputfile.in`. Demo-адаптер делает то же самое внутри контейнера.

## 14. Типичные проблемы

### Docker не установлен или демон не запущен

Проверьте:

```bash
docker version
docker run --rm hello-world
```

### Нет прав на Docker в WSL

Временно можно запускать через `sudo`, но лучше добавить пользователя в группу `docker`:

```bash
sudo usermod -aG docker $USER
```

Затем перезапустить WSL-сессию.

### Сборка PETSc/PFLOTRAN занимает много времени

Это нормально. PETSc скачивает и собирает MPI, HDF5, BLAS/LAPACK, METIS/ParMETIS. Увеличьте `BUILD_JOBS`, если хватает CPU/RAM:

```bash
BUILD_JOBS=8 ./scripts/build_image.sh
```

### Нехватка памяти при сборке

Уменьшите параллельность:

```bash
BUILD_JOBS=2 ./scripts/build_image.sh
```

### Нужно открыть результаты в Windows

Результаты лежат в обычной папке проекта:

```text
output/runs/demo_richards/
```

В Windows Explorer её можно открыть через путь WSL, например:

```text
\\wsl$\Ubuntu-24.04\home\<user>\...\pflotran_soilflow_docker\output\runs\demo_richards
```

## 15. Дальнейшее развитие

Следующие технические шаги:

```text
1. time-dependent верхняя атмосферная граница вместо среднего flux;
2. root uptake через SOURCE_SINK;
3. dynamic groundwater boundary;
4. drain boundary / linear drain sink;
5. постпроцессинг водного баланса;
6. генерация 2D/3D сеток и boundary patches из XLSX/GIS;
7. внешняя модель ET/T через отдельный adapter.
```


## Графические схемы

Схемы алгоритма, компонентов и XLSX-контракта добавлены в файл [`docs/SCHEMA_ALGORITHM_COMPONENTS_RU.md`](docs/SCHEMA_ALGORITHM_COMPONENTS_RU.md).

---

## Верификационный запуск `_test`

Для первого запуска контейнера добавлен специальный режим `_test`. Он решает простую установившуюся задачу: однородная изотропная почвенная колонка высотой 2 м, постоянный поток через верхнюю границу, отсутствие испарения и внутренних источников. После запуска PFLOTRAN численный профиль давления сравнивается с аналитическим решением линеаризованного уравнения Ричардса, то есть с законом Дарси для постоянной `K = K_s`.

Текущий verification-suite запускает три аналитических проверки:

```text
_test_linear_darcy
_test_hydrostatic_vg_no_flow
_test_unit_gradient_unsat
```

Команды:

```bash
make build
make check
make test
cat output/runs/_test_suite/TEST_SUITE_STATUS.txt

make test-linear
make test-hydrostatic
make test-unit-gradient
```

Параметры теста находятся в XLSX на листе:

```text
_test
```

Запуск:

```bash
./scripts/build_image.sh
./scripts/run_test_docker.sh
```

Результаты:

```text
output/runs/_test_linear_darcy/
  TEST_STATUS.txt
  test_comparison.csv
  test_comparison.svg
  analytical_solution.csv
  pflotran.in
```

Подробное описание постановки и аналитического решения см. в:

```text
docs/VERIFICATION_TEST_RU.md
```

## Верификационный запуск `_test`

В пакет добавлен специальный режим `_test` для первого численного контроля. Он решает стационарную линеаризованную задачу Ричардса/Дарси для однородной изотропной почвенной колонки высотой 2 м. Сверху задаётся постоянный поток, снизу — опорное давление; в steady-режиме нижний поток должен совпасть с верхним. Аналитическое решение имеет линейный профиль давления:

```text
qz = -Ks * d(P/(rho*g) + z)/dz
P(z) = P_bottom - rho*g*(1 + qz/Ks)*z
```

Параметры теста находятся в XLSX на листе `_test`.

Запуск:

```bash
make test
```

или:

```bash
docker/run_test.sh
```

или через скрипт из `scripts/`:

```bash
scripts/run_test_docker.sh input/soilflow_pflotran_demo.xlsx /work/runs/_test_linearized_column
```

Результаты:

```text
output/runs/_test_linearized_column/
  pflotran.in
  analytical_solution.csv
  analytical_test_summary.txt
  TEST_STATUS.txt
  test_comparison.csv
  test_comparison.svg
```

Подробное описание: `docs/TEST_LINEARIZED_COLUMN_RU.md`.

## 15. Аналитический режим `_test`

В пакет добавлен специальный режим `_test` для первой проверки численного ядра PFLOTRAN/FVM на классической установившейся задаче почвенной колонки. Тест использует насыщенную однородную изотропную колонку высотой 2 м, отсутствие испарения и внутренних источников, постоянный верхний поток и нижнее опорное давление. Аналитическое решение получается из линеаризованного уравнения Ричардса, то есть из закона Дарси при `K = Ks = const`:

```text
qz = -Ks * d(P/(rho*g) + z)/dz
P(z) = P_bottom - rho*g*(1 + qz/Ks)*z
```

Параметры теста находятся в XLSX на листе:

```text
_test
```

Запуск после сборки образа:

```bash
./scripts/run_test_docker.sh
```

или:

```bash
make test
```

Только генерация тестовых файлов без запуска PFLOTRAN:

```bash
./scripts/dry_run_test_docker.sh
```

Результаты будут в:

```text
output/runs/_test_linear_darcy/
```

Ключевые файлы результата:

```text
analytical_solution.csv
pflotran.in
run_pflotran.log
TEST_STATUS.txt
test_comparison.csv
test_comparison.svg
```

Подробное описание выведено в:

```text
docs/ANALYTICAL_TEST_RU.md
```

## 16. Набор `_test`: 4 аналитические проверки

`make test` запускает весь verification-suite:

```text
linear_darcy
hydrostatic_vg_no_flow
unit_gradient_unsat
transient_uniform_storage_vg
```

Для нового нестационарного теста:

```bash
make test-transient
make dry-test-transient
```

Быстрая проверка статусов:

```bash
make test
cat output/runs/_test_suite/TEST_SUITE_STATUS.txt
cat output/runs/_test_transient_uniform_storage_vg/TEST_STATUS.txt
cat output/runs/_test_unit_gradient_unsat/TEST_STATUS.txt
```

Итог suite пишется в:

```text
output/runs/_test_suite/TEST_SUITE_STATUS.txt
```

Для ненасыщенных VG-тестов допустим статус `PASS_WITH_WARNINGS`: он означает, что расчёт и физические проверки пройдены, а предупреждение PFLOTRAN относится к ожидаемому Mualem-VG без `SMOOTH`.

Для строгого CI-режима доступна цель:

```bash
make test-strict
```

В ней `PASS_WITH_WARNINGS` считается неуспешным результатом, тогда как обычный `make test` завершает работу с кодом `0` для `PASS` и `PASS_WITH_WARNINGS`.

## 17. Быстрая визуализация

После расчёта demo:

```bash
make visualize-demo
explorer.exe output/runs/demo_richards/plots
```

После тестов:

```bash
make visualize-test-transient
explorer.exe output/runs/_test_transient_uniform_storage_vg/plots
```

Главный файл:

```text
profiles_animation.html
```

Он содержит интерактивный slider временных шагов, кнопки `Play/Pause` и скорости `0.25x`, `0.5x`, `1x`, `2x`, `5x`. Подробности: `docs/VISUALIZATION_RU.md`.

## 18. Web-режим

Сайт управления расчётами запускается в том же Docker-образе:

```bash
make web-build
make web-up
make web-open
```

Открыть:

```text
http://localhost:8080
```

Проверка API:

```bash
curl http://localhost:8080/api/health
```

Остановить:

```bash
make web-down
```

Данные web-режима хранятся в Docker volume `/workspace`. Для VDS включите `SOILFLOW_AUTH_MODE=token` и задайте `SOILFLOW_API_TOKEN`; без токена или reverse proxy с HTTPS сайт управления расчётами нельзя публиковать в открытый интернет. Подробности: `docs/WEB_INTERFACE_RU.md`.
