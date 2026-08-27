'use client';

import { FormEvent, useMemo, useState } from 'react';

type Tab = 'Главная' | 'Расписание' | 'Новости' | 'Домашние задания' | 'Учебники' | 'Файлы проекта' | 'Чат';
type ChatMessage = { role: 'assistant' | 'user'; text: string };

const navigation: { icon: string; label: Tab }[] = [
  { icon: '⌂', label: 'Главная' }, { icon: '□', label: 'Расписание' },
  { icon: '✦', label: 'Новости' }, { icon: '✓', label: 'Домашние задания' },
  { icon: '▤', label: 'Учебники' }, { icon: '⌘', label: 'Файлы проекта' },
];

const lessons = [
  { time: '08:30', end: '09:15', subject: 'Алгебра', room: '304', state: '1 урок', color: 'indigo' },
  { time: '09:25', end: '10:10', subject: 'Литература', room: '217', state: '2 урок', color: 'coral' },
  { time: '10:20', end: '11:05', subject: 'Английский язык', room: '412', state: '3 урок', color: 'mint' },
  { time: '11:25', end: '12:10', subject: 'Физика', room: '308', state: '4 урок', color: 'amber' },
];

const initialMessages: ChatMessage[] = [{ role: 'assistant', text: 'Привет! Я готов помочь с расписанием, письмами и домашним заданием. Подключение к n8n добавим следующим шагом.' }];

function SchedulePanel({ full = false }: { full?: boolean }) {
  return <section className="panel schedule-panel">
    <div className="panel-head"><div><span className="kicker">МЭШ + Calendar</span><h3>{full ? 'Расписание на сегодня' : 'Ближайшие уроки'}</h3></div><span className="source-pill">Демо</span></div>
    <div className="lesson-list">{lessons.slice(0, full ? lessons.length : 3).map((lesson, index) =>
      <article className={index === 0 ? 'lesson current' : 'lesson'} key={lesson.time}>
        <time>{lesson.time}<small>{lesson.end}</small></time><span className={`lesson-line ${lesson.color}`} />
        <div><strong>{lesson.subject}</strong><small>Кабинет {lesson.room}</small></div><span className="lesson-state">{lesson.state}</span>
      </article>)}</div>
  </section>;
}

function NewsPanel({ detailed = false }: { detailed?: boolean }) {
  const items = [
    ['Синхронизация почты', 'После подключения n8n здесь появится выжимка писем из личной и пересланной лицейской почты.', 'urgent'],
    ['Расписание МЭШ', 'Уроки будут автоматически сравниваться с Google Calendar без создания дубликатов.', 'ok'],
    ['Дедлайны', 'Важные даты из писем и календаря будут собраны в одном месте.', 'info'],
  ];
  return <section className="panel news-panel">
    <div className="panel-head"><div><span className="kicker">Gmail</span><h3>{detailed ? 'Новости и важные письма' : 'Важное'}</h3></div><span className="counter">{items.length}</span></div>
    {items.slice(0, detailed ? items.length : 2).map(([title, text, type]) =>
      <article key={title}><span className={`news-icon ${type}`}>{type === 'ok' ? '✓' : type === 'info' ? 'i' : '!'}</span><div><strong>{title}</strong><p>{text}</p></div></article>)}
  </section>;
}

export default function Home() {
  const [active, setActive] = useState<Tab>('Главная');
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [sending, setSending] = useState(false);
  const date = useMemo(() => new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date()), []);

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim(); if (!text || sending) return;
    setMessages(value => [...value, { role: 'user', text }]); setDraft(''); setSending(true);
    try {
      const response = await fetch('/api/assistant', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }) });
      const data = await response.json() as { reply?: string };
      setMessages(value => [...value, { role: 'assistant', text: data.reply || 'Ответ от n8n пока не получен.' }]);
    } catch { setMessages(value => [...value, { role: 'assistant', text: 'Сайт работает, но соединение с n8n пока не настроено.' }]); }
    finally { setSending(false); }
  }

  return <main className="app-shell">
    <aside className="sidebar">
      <button className="brand" onClick={() => setActive('Главная')}><span className="brand-mark">S</span><span>SpiritJeronion</span></button>
      <nav aria-label="Основная навигация">{navigation.map(item =>
        <button className={active === item.label ? 'nav-item active' : 'nav-item'} key={item.label} onClick={() => setActive(item.label)}><span>{item.icon}</span>{item.label}</button>)}</nav>
      <button className={active === 'Чат' ? 'nav-item chat-link active' : 'nav-item chat-link'} onClick={() => setActive('Чат')}><span>◌</span>Чат с ассистентом</button>
      <div className="system-card"><span className="status-dot waiting" /><div><strong>Интерфейс готов</strong><small>Ожидается подключение n8n</small></div></div>
    </aside>

    <section className="content">
      <header className="topbar"><div><p className="eyebrow">{date}</p><h1>{active}</h1></div><button className="avatar" aria-label="Открыть профиль">J</button></header>

      {active === 'Главная' && <><section className="hero-card"><div><span className="hero-label">Следующий урок</span><h2>Алгебра</h2><p>08:30–09:15 · кабинет 304</p></div><div className="countdown"><strong>18</strong><span>минут</span></div></section><div className="dashboard-grid"><SchedulePanel /><NewsPanel /></div></>}
      {active === 'Расписание' && <div className="page-grid"><SchedulePanel full /><section className="panel action-panel"><span className="kicker">Быстрые действия</span><h3>Календарь</h3><button>Синхронизировать МЭШ</button><button className="secondary">Открыть Google Calendar</button><p>При синхронизации существующие уроки не дублируются.</p></section></div>}
      {active === 'Новости' && <div className="page-grid"><NewsPanel detailed /><section className="panel action-panel"><span className="kicker">Почта</span><h3>Источники</h3><div className="connection-row"><span className="gmail-dot" />Личный Gmail <b>готов</b></div><div className="connection-row"><span className="school-dot" />Почта лицея <b>пересылка</b></div><button>Обновить выжимку</button></section></div>}
      {active === 'Домашние задания' && <section className="workspace-card"><div className="workspace-copy"><span className="kicker">Помощник по ДЗ</span><h2>Что нужно сделать?</h2><p>Напиши задание или прикрепи фотографию. Ассистент найдёт нужный учебник и объяснит решение.</p><div className="suggestions"><button>Сделать конспект</button><button>Решить упражнение</button><button>Разобрать фото</button></div></div><div className="task-box"><textarea placeholder="Например: сделай конспект параграфа 7 по истории…" /><label className="drop-zone"><input type="file" accept="image/*,.pdf" /><span>＋</span><strong>Добавить фото или PDF</strong><small>Файл останется в твоём хранилище</small></label><button className="primary">Начать выполнение</button></div></section>}
      {active === 'Учебники' && <section><div className="section-title"><div><span className="kicker">Библиотека</span><h2>Учебники</h2></div><button className="primary compact">＋ Добавить PDF</button></div><div className="book-grid">{['Алгебра · 9 класс','История России · 9 класс','Физика · 9 класс'].map((book,index)=><article className="book-card" key={book}><div className={`book-cover cover-${index+1}`}>▤</div><strong>{book}</strong><span>{index === 0 ? 'Готов к поиску' : 'Пример карточки'}</span></article>)}</div></section>}
      {active === 'Файлы проекта' && <section className="repo-layout"><div className="panel repo-panel"><div className="panel-head"><div><span className="kicker">GitHub</span><h3>SpiritJeronion</h3></div><span className="branch">main</span></div>{[['app','Интерфейс сайта'],['mesh-parser','Интеграция с МЭШ'],['workflows','Экспорты n8n'],['docs','План и инструкции'],['README.md','Описание проекта']].map(([name,desc],i)=><div className="file-row" key={name}><span>{i<4?'▸':'#'}</span><strong>{name}</strong><small>{desc}</small></div>)}</div><aside className="panel repo-about"><span className="kicker">Репозиторий</span><h3>Всё под контролем</h3><p>Код и история изменений будут находиться в GitHub. Секреты и личные данные останутся только на твоём компьютере.</p><button>Подключить GitHub</button></aside></section>}
      {active === 'Чат' && <section className="chat-page"><div className="chat-history">{messages.map((message,index)=><div className={`bubble ${message.role}`} key={index}>{message.text}</div>)}{sending && <div className="bubble assistant typing">Думаю…</div>}</div><form className="chat-compose" onSubmit={sendMessage}><input value={draft} onChange={event=>setDraft(event.target.value)} placeholder="Напиши сообщение…" /><button type="button">＋</button><button className="send" type="submit">↑</button></form></section>}
      {active !== 'Чат' && <form className="assistant-bar" onSubmit={event => { sendMessage(event); setActive('Чат'); }}><span className="spark">✦</span><input value={draft} onChange={event=>setDraft(event.target.value)} aria-label="Сообщение ассистенту" placeholder="Спроси про расписание, письма или домашнее задание…" /><button type="button" aria-label="Прикрепить файл">＋</button><button className="send" type="submit" aria-label="Отправить">↑</button></form>}
    </section>
  </main>;
}
