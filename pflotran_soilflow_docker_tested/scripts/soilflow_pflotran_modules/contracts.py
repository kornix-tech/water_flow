from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedFileContract:
    name: str
    purpose: str


@dataclass(frozen=True)
class ReplaceableAdapterContract:
    name: str
    current_module: str
    responsibility: str
    replacement_rule: str


GENERATED_FILE_CONTRACTS: tuple[GeneratedFileContract, ...] = (
    GeneratedFileContract("pflotran.in", "Входной deck PFLOTRAN для выбранной постановки."),
    GeneratedFileContract("forcing_daily.csv", "Суточные атмосферные и управляющие воздействия."),
    GeneratedFileContract("soilflow_run_summary.txt", "Сводка постановки, параметров и расчетных допущений."),
    GeneratedFileContract("run_pflotran.log", "Журнал запуска PFLOTRAN и диагностика solver-а."),
)


MODULE_BOUNDARIES = {
    "input_contract": "Чтение, приведение типов и базовая валидация JSON-снимка исходных данных расчета.",
    "physical_models": "Модели водоудерживания, влагопроводности и проверка допустимых пар.",
    "demo_deck_writer": "Генерация стандартного PFLOTRAN input deck без запуска внешнего solver-а.",
    "profile_carrier": "Генерация PFLOTRAN profile-carrier deck'ов для аналитических тестов.",
    "surface_balance": "Нормализация погодного форсинга, верхний поток и производные параметры почвы.",
    "result_diagnostics": "Парсинг результатов, solver diagnostics и единая запись статуса.",
    "result_contract": "Solver-neutral профиль, diagnostics и статус для будущих parser-adapter реализаций.",
    "solver_runner": "Поиск и запуск внешнего solver-а без знания физической постановки.",
    "test_evaluation": "Единая сборка PASS/WARN/FAIL, UNKNOWN/PFLOTRAN_ERROR и suite status.",
    "test_suite_artifacts": "Запись suite summary в TXT/JSON/CSV для машинного анализа verification-suite.",
    "test_registry": "Реестр verification/profile тестов, выбор сценариев и рабочие пути suite.",
    "test_artifacts": "Общие CSV/SVG artifacts и diagnostics аналитического overlay.",
    "profile_benchmarks": "Генерация аналитических profile overlay и оценка TECPLOT-ready статуса профильных benchmarks.",
    "profile_benchmark_cases": "Case metadata и strict-readiness plan для profile benchmark'ов: физическое семейство, carrier readiness и blockers strict evaluator-а.",
    "profile_benchmark_evaluators": "Диагностические evaluator-метрики для profile benchmark overlay без повышения их до strict verification.",
    "profile_strict_evaluators": "Strict-кандидаты для profile benchmark'ов, готовые к подключению после замены carrier deck'ов физическими постановками.",
    "richards_mms_case": "Richards MMS source-term candidate deck, adapter artifacts, initial-profile artifacts и uniform storage RATE LIST.",
    "richards_test_cases": "Dataclass-параметры, PFLOTRAN deck'и и аналитические artifacts strict/partial Richards-тестов.",
    "richards_test_evaluators": "Сравнение PFLOTRAN профилей с analytical strict/partial Richards-метриками.",
    "richards_test_runner": "Запуск strict/partial Richards-тестов: artifacts, solver и выбор evaluator-а.",
    "profile_test_runner": "Запуск profile-smoke benchmark'ов: reference artifacts, profile-carrier deck, solver и TECPLOT-ready status.",
    "test_solver_execution": "Общий test-runner adapter для native/WSL PFLOTRAN запуска и ошибок внешнего solver-а.",
    "verification_runner": "Suite-router режима _test: чтение JSON, выбор сценариев, рабочие папки и suite status.",
    "analytical_tests": "Аналитические профили и метрики сравнения численных тестов.",
}


REPLACEABLE_ADAPTERS: tuple[ReplaceableAdapterContract, ...] = (
    ReplaceableAdapterContract(
        name="solver",
        current_module="soilflow_pflotran_modules.solver_runner",
        responsibility="Найти расчетное ядро, запустить его в рабочей папке и вернуть код завершения/лог.",
        replacement_rule="Новый solver не должен зависеть от surface_balance и должен писать результаты в parser-совместимый каталог.",
    ),
    ReplaceableAdapterContract(
        name="surface_balance",
        current_module="soilflow_pflotran_modules.surface_balance",
        responsibility="Преобразовать погодные строки и параметры испарения/инфильтрации в верхний поток модели.",
        replacement_rule="Новая ET/инфильтрационная модель должна возвращать тот же weather contract или явный расширенный forcing contract.",
    ),
    ReplaceableAdapterContract(
        name="result_parser",
        current_module="soilflow_pflotran_modules.result_diagnostics",
        responsibility="Прочитать численные профили, временные ряды, предупреждения solver-а и итоговый статус.",
        replacement_rule="Для другого solver-а нужен parser-adapter, который возвращает soilflow_pflotran_modules.result_contract.",
    ),
)
