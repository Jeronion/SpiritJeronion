# SpiritJeronion

Личный школьный ИИ-ассистент с отдельным веб-интерфейсом. Объединяет расписание МЭШ, Google Calendar, почтовую выжимку, домашние задания и поиск по учебникам.

## Состав проекта

- `github-pages` — публичная статическая панель для `https://jeronion.github.io/SpiritJeronion/`.
- `spiritjeronion-web` — адаптивный личный кабинет и чат.
- `mesh-parser` — локальный безопасный адаптер расписания МЭШ.
- `docs` — архитектура и план развития.
- `workflows` — место для обезличенных экспортов n8n.

## Безопасность

Настоящие `.env`, credentials n8n, OAuth-файлы, учебники и личные workflow не попадают в GitHub. В репозитории хранятся только код, примеры настроек и документация.

## Публикация

После отправки ветки `main` workflow `.github/workflows/pages.yml` публикует каталог `github-pages`. В настройках репозитория GitHub Pages нужно выбрать источник **GitHub Actions**.

## Локальный запуск интерфейса

```powershell
cd C:\SpiritJeronion\spiritjeronion-web
npm install
npm run dev
```

После запуска интерфейс доступен на `http://localhost:3000`.
