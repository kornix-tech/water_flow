IMAGE_NAME ?= soilflow-pflotran:local

.PHONY: build run test test-strict test-linear test-hydrostatic test-unit-gradient test-transient dry-run dry-test dry-test-transient visualize visualize-demo visualize-test-linear visualize-test-hydrostatic visualize-test-unit-gradient visualize-test-transient visualize-selftest web-build web-up web-down web-logs web-open web-shell web-test-api web-sync api-smoke project-check check shell save clean

build:
	IMAGE_NAME=$(IMAGE_NAME) ./scripts/build_image.sh

run:
	IMAGE_NAME=$(IMAGE_NAME) ./scripts/run_demo_docker.sh

test:
	docker/run_test.sh all

test-strict:
	docker/run_test.sh all
	! grep -q '^TEST_SUITE_STATUS=PASS_WITH_WARNINGS' output/runs/_test_suite/TEST_SUITE_STATUS.txt

test-linear:
	docker/run_test.sh linear_darcy

test-hydrostatic:
	docker/run_test.sh hydrostatic_vg_no_flow

test-unit-gradient:
	docker/run_test.sh unit_gradient_unsat

test-transient:
	docker/run_test.sh transient_uniform_storage_vg

dry-run:
	IMAGE_NAME=$(IMAGE_NAME) ./scripts/dry_run_docker.sh

dry-test:
	docker/run_test.sh all --dry-run

dry-test-transient:
	docker/run_test.sh transient_uniform_storage_vg --dry-run

visualize:
	docker/run_visualize.sh demo_richards

visualize-demo:
	docker/run_visualize.sh demo_richards

visualize-test-linear:
	docker/run_visualize.sh _test_linear_darcy

visualize-test-hydrostatic:
	docker/run_visualize.sh _test_hydrostatic_vg_no_flow

visualize-test-unit-gradient:
	docker/run_visualize.sh _test_unit_gradient_unsat

visualize-test-transient:
	docker/run_visualize.sh _test_transient_uniform_storage_vg

visualize-selftest:
	docker/run_visualize.sh --self-test

web-build:
	docker compose build soilflow-web

web-up:
	docker compose up -d soilflow-web

web-down:
	docker compose down

web-logs:
	docker compose logs -f soilflow-web

web-open:
	@echo "Open http://localhost:8080"

web-shell:
	docker compose exec soilflow-web bash

web-test-api:
	curl -f http://localhost:8080/api/health

web-sync:
	./scripts/sync_to_running_container.sh

api-smoke:
	./scripts/api_smoke.sh

project-check:
	./scripts/check_project.sh

check:
	docker run --rm $(IMAGE_NAME) check

shell:
	IMAGE_NAME=$(IMAGE_NAME) ./scripts/shell_in_container.sh

save:
	IMAGE_NAME=$(IMAGE_NAME) ./scripts/save_image.sh

clean:
	./scripts/clean_output.sh
