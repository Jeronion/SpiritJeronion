# n8n workflows

Сюда будут добавляться только обезличенные экспорты workflow: без credential IDs, Telegram User ID, OAuth-конфигурации и других личных значений.

`spirit-core.example.json` содержит три защищённых webhook: передачу новых сведений, подтверждение предложений и чтение состояния. Перед активацией замените `REPLACE_BEFORE_ACTIVATING` в узлах `Validate Intake`, `Validate Decision` и `Validate State` на одинаковый случайный секрет.
