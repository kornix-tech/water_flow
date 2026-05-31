# Roadmap verification-тестов

Следующий этап должен быть диагностическим и отчётным, без расширения физики модели.

1. Прямой face-flux test: включить стабильный вывод liquid velocity/flux и сравнить face flux с аналитическим `q`.
2. Атмосферная верхняя граница: тест переключения `flux boundary` -> `pressure/ponding boundary`.
3. Дренаж: тест линейного drain sink `Q = C * max(H - Hdrain, 0)`.
4. Испарение: тест верхнего sink с ограничением доступностью воды.
5. Root uptake: manufactured sink по глубине с аналитическим изменением storage.
