# SoilFlow / PFLOTRAN starter kit

Стартовый комплект для демонстрационного расчёта влагопереноса в почве на основе уравнения Ричардса с внешним FVM-решателем PFLOTRAN.

Комплект содержит:

```text
run_demo_windows.bat                         Windows BAT-запуск
scripts/soilflow_pflotran.py                 Python-обвязка: XLSX → pflotran.in → запуск
scripts/install_pflotran_wsl.sh              опциональная сборка PFLOTRAN в WSL/Ubuntu
input/soilflow_pflotran_demo.xlsx            XLSX-шаблон входных данных
runs/                                        рабочие папки расчётов
```

## 1. Важное ограничение Windows

У PFLOTRAN нет штатного Windows-инсталлятора. Официальная документация PFLOTRAN указывает, что для Windows рекомендуется Windows Subsystem for Linux (WSL), потому что сборка через Cygwin/Visual Studio сложна и склонна к ошибкам.

Официальные страницы:

```text
https://release.documentation.pflotran.org/user_guide/how_to/installation/installation.html
https://www.pflotran.org/documentation/user_guide/how_to/installation/windows_wsl.html
https://www.pflotran.org/documentation/user_guide/how_to/installation/linux.html
https://www.pflotran.org/documentation/user_guide/how_to/running.html
https://www.pflotran.org/documentation/user_guide/how_to/simple_flow_problem.html
```

Поэтому BAT-скрипт делает следующее:

```text
1. Проверяет Python.
2. Создаёт локальное виртуальное окружение .venv.
3. Устанавливает Python-зависимость openpyxl.
4. Читает XLSX.
5. Генерирует PFLOTRAN input deck: runs/demo_richards/pflotran.in.
6. Пытается найти PFLOTRAN:
   - через переменную PFLOTRAN_EXE;
   - через PATH Windows;
   - через WSL.
7. Если PFLOTRAN не найден, расчёт не падает: входные файлы остаются созданными.
```

## 2. Быстрый запуск

Распакуйте архив в папку без кириллицы и пробелов, например:

```text
C:\soilflow_pflotran_starter
```

Откройте `cmd.exe` или PowerShell в этой папке и выполните:

```bat
run_demo_windows.bat
```

Результат будет в:

```text
runs\demo_richards\
```

Минимально должны появиться:

```text
pflotran.in
forcing_daily.csv
soilflow_run_summary.txt
```

Если PFLOTRAN найден и успешно запущен, появятся также файлы PFLOTRAN output и лог:

```text
run_pflotran.log
```

или для WSL:

```text
run_pflotran_wsl.log
```

## 3. Запуск с другим XLSX-файлом

```bat
run_demo_windows.bat --xlsx input\my_case.xlsx --workdir runs\my_case
```

## 4. Опциональная автоматическая сборка PFLOTRAN в WSL

Сначала установите WSL/Ubuntu, если он ещё не установлен:

```powershell
wsl --install -d Ubuntu
```

Затем из папки комплекта:

```bat
run_demo_windows.bat --install-pflotran-wsl
```

Это запустит `scripts/install_pflotran_wsl.sh`, который:

```text
1. Установит пакеты Ubuntu: gcc, gfortran, make, cmake, mpich, git и др.
2. Склонирует PETSc.
3. Соберёт PETSc.
4. Склонирует PFLOTRAN.
5. Соберёт PFLOTRAN.
6. Создаст symlink ~/.local/bin/pflotran.
```

Сборка может занять значительное время и может запросить sudo-пароль внутри WSL.

## 5. Ручное подключение уже установленного PFLOTRAN

Если у вас уже есть PFLOTRAN executable, задайте переменную окружения:

```bat
set PFLOTRAN_EXE=C:\path\to\pflotran.exe
run_demo_windows.bat
```

Или укажите путь в XLSX:

```text
Лист 09_Solver
Parameter = pflotran_exe
Value     = C:\path\to\pflotran.exe
```

Если PFLOTRAN установлен в WSL и доступен как команда `pflotran`, BAT найдёт его автоматически через WSL.

## 6. Структура XLSX

Файл:

```text
input/soilflow_pflotran_demo.xlsx
```

содержит листы:

```text
00_README                краткое описание
01_Project               параметры проекта
02_Domain                область, сетка, размерность 1D/2D/3D
03_Soil                  гидрофизические свойства почвы
04_Initial_BC            начальные и граничные условия
05_Time_Forcing          период расчёта и временные настройки
06_ET_Roots              контракт внешней ET/T-модели и корней
07_Irrigation_Drainage   полив и дренаж
08_Groundwater           динамические грунтовые воды
09_Solver                настройки PFLOTRAN/запуска
10_Weather_Daily         суточный форсинг
11_Derived_Checks        производные параметры и контроль единиц
```

Главные машинно-читаемые колонки на листах 01–09:

```text
Parameter  имя параметра
Value      значение
Units      размерность
Описание   физический смысл
```

Python-скрипт читает пары `Parameter → Value`.

## 7. Демонстрационная задача

По умолчанию задана синтетическая 1D-колонка:

```text
глубина: 2 м
число ячеек: 80
почва: условный суглинок van Genuchten–Mualem
режим: RICHARDS
верхняя граница: средний поток из P + irrigation - Epot
нижняя граница: hydrostatic pressure
период: 7 суток
```

В листе `10_Weather_Daily` заданы синтетические данные:

```text
осадки
полив
потенциальное испарение
потенциальная транспирация
глубина грунтовых вод
```

Для первого демонстрационного PFLOTRAN input активируется только верхний чистый поток:

```text
net_surface_input = precipitation + irrigation - potential_soil_evaporation
```

`Tpot`, корни, дренаж и динамические грунтовые воды включены в XLSX как архитектурный контракт расширения. В текущем минимальном input они не активируются как распределённый `SOURCE_SINK`, чтобы оставить первый пример максимально проверяемым и близким к официальному PFLOTRAN simple-flow example.

## 8. Как перейти от 1D к 2D/3D

В XLSX измените:

```text
02_Domain:
dimension = 2 или 3
nx, ny, nz
length_x_m, length_y_m, depth_z_m
```

Пример 2D x-z:

```text
dimension = 2
length_x_m = 30
length_y_m = 1
depth_z_m = 2
nx = 120
ny = 1
nz = 80
```

Пример 3D:

```text
dimension = 3
length_x_m = 30
length_y_m = 20
depth_z_m = 2
nx = 120
ny = 80
nz = 60
```

Архитектурно Python-обвязка генерирует `GRID NXYZ` и `DXYZ` одинаково для 1D, 2D и 3D. Более сложные граничные patches, дрены, каналы и неоднородные материалы нужно добавлять в последующих версиях adapter-а.

## 9. Что уже заложено для будущей модульной программы

В XLSX уже есть параметры для следующих модулей:

```text
внешняя ET/T-модель
распределение корней
водный стресс Tact/Tpot
полив
дренаж
регулируемый дренаж
динамический уровень грунтовых вод
капиллярный подъём
боковые граничные условия
```

Рекомендуемая следующая разработка:

```text
1. Добавить time-dependent верхний flux вместо среднего flux.
2. Добавить root uptake как SOURCE_SINK по корневой зоне.
3. Добавить нижний boundary condition от динамического GW-модуля.
4. Добавить drainage sink или drain boundary patches.
5. Добавить 2D пример с tile drain.
6. Добавить контроль водного баланса по output PFLOTRAN.
```

## 10. Частые проблемы

### Python не найден

Установите Python 3.10+:

```text
https://www.python.org/downloads/windows/
```

### PFLOTRAN не найден

Это не ошибка генератора. Скрипт всё равно создаёт `pflotran.in`.

Дальше можно:

```text
1. Установить PFLOTRAN в WSL.
2. Указать PFLOTRAN_EXE.
3. Перенести папку runs/demo_richards в Linux/HPC и запустить PFLOTRAN там.
```

### WSL есть, но PFLOTRAN не запускается

Откройте WSL и проверьте:

```bash
which pflotran
pflotran --help
```

Если команда не найдена, выполните сборку:

```bat
run_demo_windows.bat --install-pflotran-wsl
```

### PFLOTRAN сообщает ошибку input deck

Проверьте:

```text
runs/demo_richards/run_pflotran.log
runs/demo_richards/run_pflotran_wsl.log
runs/demo_richards/pflotran.in
```

Первый input deck намеренно близок к официальному simple-flow example PFLOTRAN. Если вы изменили BC/параметры, ошибка чаще всего связана с единицами или неподдерживаемым вариантом граничного условия.

## 11. Проверка сгенерированного input

Без запуска PFLOTRAN:

```powershell
.\.venv\Scripts\python.exe scripts\soilflow_pflotran.py --xlsx input\soilflow_pflotran_demo.xlsx --workdir runs\demo_richards --dry-run
```

С запуском:

```powershell
.\.venv\Scripts\python.exe scripts\soilflow_pflotran.py --xlsx input\soilflow_pflotran_demo.xlsx --workdir runs\demo_richards --run --prefer-wsl
```
