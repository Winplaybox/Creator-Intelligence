# Local development

1. Copy `.env.example` to `.env` and replace secrets for your environment.
2. Start infrastructure: `docker compose up -d postgres redis`.
3. API: `cd apps/api && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && uvicorn app.main:app --reload`.
4. Web: `pnpm install && pnpm --filter web dev`.
5. API health: `http://localhost:8000/health`; docs: `http://localhost:8000/docs`.

Never use the sample credentials outside local development.
