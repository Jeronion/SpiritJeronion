# Единый запуск SpiritJeronion

- Двойной клик по `Start SpiritJeronion.cmd` запускает AI Worker, n8n и Cloudflare Tunnel, затем открывает сайт.
- `Stop SpiritJeronion.cmd` останавливает компоненты SpiritJeronion, включая уже работавшие на его портах при запуске.
- `Install-Autostart.ps1` включает автоматический запуск при входе в Windows.
- `Uninstall-Autostart.ps1` удаляет автозапуск.

Локальные параметры, PID и журналы находятся в `.spirit-data` и не попадают в GitHub.

Без токена именованного Cloudflare Tunnel используется быстрый туннель. Его адрес меняется после перезапуска, автоматически копируется в буфер обмена и передаётся сайту при открытии. Секрет сохраняется в браузере отдельно и в URL не попадает. Чтобы адрес был постоянным, укажите токен именованного туннеля в `.spirit-data/launcher.json` в поле `cloudflareTunnelToken`.
