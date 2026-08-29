# Content worker

Worker получает только уже подтверждённые предложения из n8n.

- события записывает в `WebsiteHosting/data/calendar.json`;
- задачи — в `WebsiteHosting/data/tasks.json`;
- конспекты и решения создаёт через видимый Chrome с `ChatGPTAutomation`;
- сохраняет файлы из Telegram в приватной локальной памяти `.cache/memory` и индексирует TXT, MD, DOCX и PDF;
- при наличии `GITHUB_TOKEN` обновляет те же файлы через GitHub Contents API.

Для первого запуска:

1. Запустить `setup.ps1`. Он учитывает несовместимый upstream-pin `pywin32==306` на Python 3.14.
2. Заполнить нужные значения в едином локальном файле `C:\SpiritJeronion\.env`.
3. Сначала оставить `CHATGPT_AUTOMATION_ENABLED=false` и проверить `/api/health`.
4. Затем включить автоматизацию. При первом запуске Chrome может потребовать ручной вход и проверку Cloudflare.

Библиотека использует Selenium и не поддерживает headless-режим, поэтому Chrome должен быть доступен в интерактивном сеансе Windows.

Файлы памяти не публикуются в GitHub. Они отправляются во внешний ChatGPT только при явном выборе файла в подтверждённом запросе.
