# Визуализация результатов SoilFlow/PFLOTRAN

## Что показывает визуализация

- эпюра объёмной влажности `theta(z,t)`;
- эпюра напора давления `h(z,t)`;
- жидкостная насыщенность `S_l(z,t)`;
- абсолютное давление `P(z,t)`.

## Как рассчитываются величины

```text
theta = phi * S_l
h = (P - P_atm) / (rho * g)
depth = z_top - z
```

Ось глубины на графиках направлена вниз: `0 м` сверху, максимум глубины снизу.

## Как запустить

После demo-расчёта:

```bash
make visualize-demo
```

После тестов:

```bash
make visualize-test-transient
make visualize-test-linear
make visualize-test-hydrostatic
make visualize-test-unit-gradient
```

Если `make` недоступен, используйте прямой Docker-скрипт:

```bash
docker/run_visualize.sh _test_transient_uniform_storage_vg
```

## Как менять скорость анимации

```bash
SPEED_MS=1000 make visualize-demo
SPEED_MS=200 make visualize-demo
```

В HTML доступны кнопки `0.25x`, `0.5x`, `1x`, `2x`, `5x`, `Play`, `Pause`.

## Где результаты

```text
output/runs/<run_name>/plots/profiles_animation.html
output/runs/<run_name>/plots/profile_frames_long.csv
output/runs/<run_name>/plots/profile_summary.csv
output/runs/<run_name>/plots/VISUALIZATION_STATUS.txt
```

Для открытия из Windows:

```bash
explorer.exe output/runs/_test_transient_uniform_storage_vg/plots
```

## Self-test

```bash
make visualize-selftest
```

Ожидаемый статус:

```text
output/visualization_selftest/VISUALIZATION_STATUS.txt
VISUALIZATION_STATUS=PASS
```

## Ограничения

- для 2D/3D по умолчанию строится средний профиль по глубине;
- прямые карты 2D/3D пока не строятся;
- если PFLOTRAN output не содержит `Porosity`, используется значение из XLSX или default;
- если временные метки отсутствуют в TECPLOT, используется `frame_index`;
- HTML самодостаточный: Plotly включается внутрь файла, внешний интернет не нужен.

## План развития

1. 2D-карты влажности `theta(x,z,t)`.
2. 2D-карты pressure head `h(x,z,t)`.
3. Анимация фронта инфильтрации в 2D.
4. Экспорт MP4/GIF через `imageio`/`ffmpeg`.
5. Сравнение двух сценариев на одном графике.
6. Отображение дренажных потоков и положения уровня грунтовых вод.
7. Web-dashboard на Dash/Panel/Streamlit, если потребуется интерактивный интерфейс.
