# lolz-bump

Сервис для автоматического поднятия тем LOLZ по расписанию окон.

## Что делает

- Поддерживает лимит поднятий за окно (`window_limit`).
- В каждом окне сначала поднимает все `important_threads`.
- Оставшиеся слоты заполняет `regular_threads` по круговой очереди.
- Индекс очереди `regular_threads` сохраняется в SQLite и переживает перезапуск.
- Если поднятие одной темы падает, окно продолжается для остальных тем.

## Требования

- Python 3.11+
- Токен в ENV: `LOLZ_API_TOKEN`

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
# заполнить LOLZ_API_TOKEN
cp config.example.yml config.yml
python -m lolz_bump --config config.yml --db state.db
```

Однократный прогон окна без планировщика:

```bash
python -m lolz_bump --config config.yml --db state.db --dry-run
```

## Конфиг

Пример в `config.example.yml`.

Поля:

- `window_limit`: лимит тем за одно окно.
- `api_timeout_seconds`: timeout HTTP-запроса к API в секундах (по умолчанию `30`).
- `timezone`: временная зона, например `Europe/Moscow`.
- `schedule_times`: список стартов окон в формате `HH:MM`.
- `important_threads`: важные темы (должно быть `<= window_limit`).
- `regular_threads`: неважные темы для ротации.

## Docker Compose (рекомендуется)

Подготовка:

```bash
cp .env.example .env
cp config.example.yml config.yml
mkdir -p data
```

Запуск одной командой:

```bash
docker compose up -d --build
```

Остановка:

```bash
docker compose down
```

## Docker (альтернатива без compose)

```bash
docker build -t lolz-bump .
docker run --rm \
  --env-file .env \
  -v "$(pwd)/config.yml:/app/config.yml" \
  -v "$(pwd)/data:/data" \
  lolz-bump --config /app/config.yml --db /data/state.db
```

## Тесты

```bash
pytest
```

## Open Source

- Лицензия: [MIT](LICENSE)
- Правила вклада: [CONTRIBUTING.md](CONTRIBUTING.md)
- Безопасность: [SECURITY.md](SECURITY.md)
- Кодекс поведения: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
