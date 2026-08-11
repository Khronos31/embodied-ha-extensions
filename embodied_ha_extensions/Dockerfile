FROM python:3.11-slim-bookworm

WORKDIR /app
COPY manager /app/manager
COPY catalog /app/catalog
COPY apps /app/apps
COPY run.sh /app/run.sh
RUN chmod 0755 /app/run.sh

CMD ["/app/run.sh"]
