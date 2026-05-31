# Графическая схема алгоритма и компонентов SoilFlow/PFLOTRAN Docker-пакета

Этот документ описывает текущий демонстрационный код Docker-пакета: сборку контейнера, Python-адаптер, XLSX-контракт, генерацию `pflotran.in` и запуск PFLOTRAN в режиме `RICHARDS`.

## 0. Обзорная схема, удобная для чтения

![Обзорная схема компонентов](schema_overview_clean.svg)

PNG-версия: [`schema_overview_clean.png`](schema_overview_clean.png)

![Чистая схема алгоритма](schema_algorithm_clean.svg)

PNG-версия: [`schema_algorithm_clean.png`](schema_algorithm_clean.png)


## 1. Компонентная схема

![Компонентная схема](schema_components.svg)

PNG-версия: [`schema_components.png`](schema_components.png)

## 2. Алгоритм сборки и запуска demo-задачи

![Алгоритм запуска](schema_algorithm.svg)

PNG-версия: [`schema_algorithm.png`](schema_algorithm.png)

## 3. Контракт данных XLSX → PFLOTRAN

![Контракт данных](schema_data_contract.svg)

PNG-версия: [`schema_data_contract.png`](schema_data_contract.png)

## 4. Что реально активно в текущем demo-коде

Активный расчётный путь:

```text
XLSX → Python/openpyxl → производные параметры → pflotran.in → PFLOTRAN RICHARDS → output/log
```

Активные физические элементы текущего demo:

```text
1. structured grid 1D/2D/3D через NXYZ;
2. RICHARDS mode;
3. van Genuchten saturation function;
4. Mualem VG relative permeability;
5. верхний Neumann flux boundary;
6. нижний режим: hydrostatic / no-flow / constant pressure;
7. начальное hydrostatic pressure condition;
8. TECPLOT POINT output.
```

Заложено как контракт расширения, но в минимальном `pflotran.in` пока не активировано как полноценные time-dependent source/sink или boundary conditions:

```text
1. внешняя модель испарения и транспирации;
2. распределённое корневое водопотребление;
3. динамические грунтовые воды;
4. дренаж;
5. событийный полив с внутрисуточной динамикой.
```

## 5. Упрощённая Mermaid-схема

```mermaid
flowchart LR
    A[WSL Ubuntu + Docker] --> B[Dockerfile]
    B --> C[Builder stage: PETSc + PFLOTRAN]
    C --> D[Runtime image]
    D --> E[entrypoint.sh]
    E --> F[soilflow_pflotran.py]
    G[XLSX input] --> F
    F --> H[pflotran.in]
    F --> I[forcing_daily.csv]
    F --> J[soilflow_run_summary.txt]
    H --> K[PFLOTRAN RICHARDS]
    K --> L[run_pflotran.log + TECPLOT output]
    L --> M[output/ на хосте]
```

## 6. Алгоритм Python-адаптера

```mermaid
flowchart TD
    A[Start soilflow_pflotran.py] --> B[read_params: листы 01-09]
    A --> C[read_weather: лист 10_Weather_Daily]
    B --> D[compute_derived]
    C --> D
    D --> E[generate_pflotran_input]
    C --> F[write_weather_csv]
    D --> G[write_summary]
    E --> H[pflotran.in]
    F --> I[forcing_daily.csv]
    G --> J[soilflow_run_summary.txt]
    H --> K{--run?}
    K -- нет --> L[stop после генерации]
    K -- да --> M[find PFLOTRAN_EXE]
    M --> N[mpirun/pflotran]
    N --> O[log + PFLOTRAN output]
```
