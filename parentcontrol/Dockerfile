FROM python:3.13-alpine

RUN apk add --no-cache nodejs && pip install --no-cache-dir yt-dlp

COPY app /app
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
