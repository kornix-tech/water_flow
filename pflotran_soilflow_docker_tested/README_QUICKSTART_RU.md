# Быстрый старт

```bash
cd pflotran_soilflow_docker
chmod +x docker/*.sh
docker/build_image.sh
docker/check_image.sh
docker/run_demo.sh
```

Результаты:

```text
output/demo_richards/
```

Сохранить переносимый образ:

```bash
docker/save_image.sh
```

Подробности: `README_DOCKER_RU.md`.

## Быстрый верификационный тест

```bash
./scripts/build_image.sh
./scripts/run_test_docker.sh
cat output/runs/_test_linear_darcy/TEST_STATUS.txt
```

Описание: `docs/VERIFICATION_TEST_RU.md`.

## Проверочный `_test`

```bash
make test
```

или:

```bash
docker/run_test.sh
```

Результат будет в:

```text
output/runs/_test_linearized_column/
```
