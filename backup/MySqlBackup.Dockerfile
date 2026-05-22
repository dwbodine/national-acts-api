FROM alpine:3.20

RUN apk add --no-cache \
    mysql-client \
    aws-cli \
    docker-cli \
    tzdata \
    bash

ENV TZ=UTC

COPY backup.sh /backup.sh
COPY restore.sh /restore.sh
COPY fetch-latest-backup.sh /fetch-latest-backup.sh
COPY crontab /etc/crontabs/root

RUN chmod +x /backup.sh
RUN chmod +x /restore.sh
RUN chmod +x /fetch-latest-backup.sh

CMD ["crond", "-f", "-l", "2"]
