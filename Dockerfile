# Build the frontend, then serve it and the API from one container (Cloud Run friendly).
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY --from=web /web/dist frontend/dist
WORKDIR /srv/backend
ENV PORT=8080 LLM_PROVIDER=offline
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
