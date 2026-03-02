FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/
COPY lolz_bump /app/lolz_bump

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "lolz_bump"]
CMD ["--config", "/app/config.yml", "--db", "/app/state.db"]
