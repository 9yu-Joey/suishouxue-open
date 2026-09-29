# 随手学 Private · 服务镜像
#
# 构建上下文是仓库根目录：
#   docker compose -f deploy/docker-compose.yml build
#
# 镜像本身默认只监听容器内 127.0.0.1，直接 `docker run -p` 暴露端口会被拒绝启动；
# 对外服务请使用 deploy/docker-compose.yml（由 Caddy 提供 HTTPS）。

FROM python:3.12-slim

# git / openssh-client：可选的 Pro Git 同步需要
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 suishouxue

WORKDIR /app
COPY kb-mcp/requirements.txt kb-mcp/requirements.txt
RUN pip install --no-cache-dir -r kb-mcp/requirements.txt

COPY kb-mcp/ kb-mcp/
COPY profiles/ profiles/

ENV PYTHONUNBUFFERED=1 \
    SUISHOUXUE_CARDS_DIR=/data/cards \
    SUISHOUXUE_TOKENS_FILE=/data/tokens.json \
    SUISHOUXUE_HTTP_PORT=8765

RUN mkdir -p /data/cards && chown -R suishouxue:suishouxue /data
USER suishouxue
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=3)"

CMD ["python", "kb-mcp/server.py", "--transport", "http"]
