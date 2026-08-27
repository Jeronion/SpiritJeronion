# Обновление панели через n8n

GitHub Pages читает безопасные данные из каталога `github-pages/data`. n8n может обновлять их через GitHub API или узел GitHub.

## Файлы данных

- `schedule.json` — массив уроков с полями `start`, `end`, `subject`, `room`, `label`.
- `news.json` — массив выжимок с полями `title`, `summary`.
- `homework.json` — массив заданий с полями `subject`, `task`, `due`.
- `books.json` — каталог с полями `title`, `description`, `url`.
- `meta.json` — время обновления и статус источника.

## Безопасная схема

1. n8n получает данные из МЭШ, Gmail и Calendar.
2. Code node удаляет адреса, токены, cookies и лишние персональные данные.
3. GitHub node заменяет нужный JSON-файл в ветке `main`.
4. GitHub Actions заново публикует панель.

Не сохраняйте GitHub token, OAuth credentials, cookies МЭШ и содержимое личных писем в JSON-файлах или workflow-экспортах.
