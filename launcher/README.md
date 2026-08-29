# Единый запуск SpiritJeronion

Все пользовательские файлы запуска находятся в этой папке. Дважды щёлкни `launcher/Start SpiritJeronion.cmd`. Скрипт запускает n8n, МЭШ, content worker, Telegram-бота, локальный сайт и Cloudflare Quick Tunnel. После запуска он открывает GitHub Pages и автоматически сохраняет новый tunnel URL и `SPIRIT_QUEUE_SECRET` только в `localStorage` текущего браузера.

Секрет не записывается в GitHub Pages и не отправляется GitHub: конфигурация передаётся через URL fragment (`#setup=...`), который браузер не включает в HTTP-запрос, а затем сразу удаляет из адресной строки.

Для остановки используй `launcher/Stop SpiritJeronion.cmd`.

GitHub Pages публикуется автоматически workflow из `.github/workflows/pages.yml` после push в `main`; локальный launcher не создаёт автоматических Git-коммитов.
