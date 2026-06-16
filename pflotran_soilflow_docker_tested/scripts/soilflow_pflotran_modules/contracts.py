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
