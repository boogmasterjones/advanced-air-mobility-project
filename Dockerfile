# Build the frontend, then serve it and the API from one container (Cloud Run friendly).
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
# libgomp1: the forecaster (LightGBM) needs the OpenMP runtime, which the slim image lacks.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY eval/results/ eval/results/
COPY --from=web /web/dist frontend/dist
WORKDIR /srv/backend
# ROUTE_LOOKUP=live lets the app ask the public OSRM router for pairs that are not saved.
ENV PORT=8080 LLM_PROVIDER=offline ROUTE_LOOKUP=live
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
