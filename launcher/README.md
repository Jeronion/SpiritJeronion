# Единый запуск SpiritJeronion

Для управления всем проектом используется один пользовательский файл: `launcher/SpiritJeronion.cmd`. Дважды щёлкни его и выбери `1` для запуска или `2` для остановки. При запуске включаются n8n, МЭШ, content worker, Telegram-бот, локальный сайт и Cloudflare Quick Tunnel. После запуска открывается GitHub Pages, а новый tunnel URL и `SPIRIT_QUEUE_SECRET` сохраняются только в `localStorage` текущего браузера.

Секрет не записывается в GitHub Pages и не отправляется GitHub: конфигурация передаётся через URL fragment (`#setup=...`), который браузер не включает в HTTP-запрос, а затем сразу удаляет из адресной строки.

Внутренние PowerShell-скрипты находятся в `launcher/internal`; запускать их вручную не требуется.

GitHub Pages публикуется автоматически workflow из `.github/workflows/pages.yml` после push в `main`; локальный launcher не создаёт автоматических Git-коммитов.
