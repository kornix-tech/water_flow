from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedFileContract:
    name: str
    purpose: str


GENERATED_FILE_CONTRACTS: tuple[GeneratedFileContract, ...] = (
    GeneratedFileContract("pflotran.in", "Входной deck PFLOTRAN для выбранной постановки."),
    GeneratedFileContract("forcing_daily.csv", "Суточные атмосферные и управляющие воздействия."),
    GeneratedFileContract("soilflow_run_summary.txt", "Сводка постановки, параметров и расчетных допущений."),
    GeneratedFileContract("run_pflotran.log", "Журнал запуска PFLOTRAN и диагностика solver-а."),
)


MODULE_BOUNDARIES = {
    "input_contract": "Чтение и валидация JSON-снимка исходных данных расчета.",
    "physical_models": "Модели водоудерживания, влагопроводности и проверка допустимых пар.",
    "deck_writer": "Генерация PFLOTRAN input deck без запуска внешнего solver-а.",
    "analytical_tests": "Аналитические профили и метрики сравнения численных тестов.",
    "runner": "Запуск PFLOTRAN, обработка кодов возврата и запись диагностик.",
}
