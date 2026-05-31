# Режим `_test`: аналитическая проверка PFLOTRAN/FVM на установившейся почвенной колонке

## 1. Назначение

Режим `_test` нужен для первой численной верификации контейнера: до усложнения модели корнями, испарением, поливом и дренажем надо показать, что внешний FVM-решатель воспроизводит простое классическое аналитическое решение.

Тестовая задача представляет лабораторную колонку высотой 2 м:

```text
однородная изотропная почва
насыщенный режим
K(h) = Ks = const
нет испарения
нет транспирации
нет внутренних источников и стоков
задан постоянный поток через верхнюю границу
снизу задано опорное давление
```

Строго две Neumann-границы для стационарной задачи дают давление только с точностью до произвольной константы. Поэтому в коде физика постоянного расхода сохраняется через верхний flux boundary, а на нижней границе задаётся одно reference pressure. В установившемся режиме поток через нижнюю границу должен совпасть с заданным верхним потоком.

## 2. Уравнение

PFLOTRAN в `RICHARDS` mode использует поток Дарси вида:

```text
qz = -Ks * d(P/(rho*g) + z)/dz
```

Для насыщенной однородной колонки `k = const`, `mu = const`. В одномерной стационарной постановке без источников:

```text
dqz/dz = 0
```

следовательно:

```text
qz = const
```

и

```text
d(P/(rho*g) + z)/dz = -qz/Ks
```

Так как насыщенная гидравлическая проводимость связана с intrinsic permeability как:

```text
Ks = k*rho*g/mu
```

получаем аналитический профиль давления:

```text
P(z) = P_bottom - rho*g*(1 + qz/Ks)*z
```

где:

```text
z = 0      нижняя граница колонки
z = L      верхняя граница колонки
qz         поток в PFLOTRAN z-направлении
P_bottom  заданное нижнее давление
```

В демонстрационных данных аналитический `qz` отрицателен, что соответствует нисходящему потоку по оси `z`; в PFLOTRAN Neumann boundary на верхней границе этот же физический поток передаётся как положительный inward flux.

## 3. Где заданы параметры

Все параметры режима `_test` находятся в XLSX:

```text
input/soilflow_pflotran_demo.xlsx
лист: _test
```

Ключевые параметры:

```text
column_height_m          высота колонки
ksat_m_s                 насыщенная гидравлическая проводимость
bottom_pressure_pa       нижнее reference pressure
imposed_flux_z_m_s       заданный верхний поток
nz                       число конечных объёмов по вертикали
final_time_days          время расчёта
maximum_timestep_days    максимальный шаг solver-а
```

## 4. Запуск

После сборки Docker-образа:

```bash
./scripts/run_test_docker.sh
```

или:

```bash
make test
```

Только генерация файлов без запуска PFLOTRAN:

```bash
./scripts/dry_run_test_docker.sh
```

или:

```bash
make dry-test
```

## 5. Что создаётся

Результаты пишутся в:

```text
output/runs/_test_linear_darcy/
```

Основные файлы:

```text
pflotran.in                  входной файл PFLOTRAN для тестовой задачи
analytical_solution.csv       аналитический профиль давления по ячейкам
analytical_test_summary.txt   параметры и формулы теста
run_pflotran.log              лог PFLOTRAN
TEST_STATUS.txt               PASS/FAIL/UNKNOWN
-test_comparison.csv          сравнение PFLOTRAN vs аналитика
-test_comparison.svg          график профиля давления
```

В реальном каталоге имена файлов сравнения без дефиса:

```text
test_comparison.csv
test_comparison.svg
```

## 6. Критерий прохождения

После запуска PFLOTRAN скрипт ищет TECPLOT/DAT output, извлекает профиль `z` и `Liquid Pressure`, затем считает:

```text
abs_error = |P_numerical - P_analytical|
rel_error = abs_error / max(|P_analytical|, 1)
```

Тест считается пройденным, если:

```text
max_abs_error <= tolerance_abs_pressure_pa
max_rel_error <= tolerance_rel_pressure
```

Допуски задаются на листе `_test`.

## 7. Ограничение теста

Этот тест не проверяет нелинейный ненасыщенный перенос с van Genuchten–Mualem. Его задача другая: подтвердить, что контейнер, PFLOTRAN, сетка, граничные условия, запуск, output parser и базовая FVM-дискретизация правильно воспроизводят линейный установившийся поток. После прохождения этого smoke-test можно добавлять более сложные benchmark-задачи: hydrostatic VG, unit-gradient VG, Gardner exponential solution, инфильтрационный фронт, дренаж и капиллярный подъём.

## 8. Источники для теоретической основы

PFLOTRAN documentation — RICHARDS Mode, Governing Equations:

```text
https://documentation.pflotran.org/theory_guide/mode_richards.html
```

PFLOTRAN documentation — Method of Solution:

```text
https://documentation.pflotran.org/theory_guide/appendixB.html
```
