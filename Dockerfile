FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ARG KUBECTL_VERSION=v1.29.3
ARG TARGETARCH

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH:-amd64}/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && kubectl version --client \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash bash-completion \
    && rm -rf /var/lib/apt/lists/*

COPY LICENSE /app/LICENSE
COPY THIRD_PARTY_NOTICES.md /app/THIRD_PARTY_NOTICES.md
COPY licenses/ /app/licenses/
COPY backend/ /app/backend/
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh

RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

WORKDIR /app/backend

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "daphne", "-b", "0.0.0.0", "-p", "8000", "sxdevops.asgi:application"]
