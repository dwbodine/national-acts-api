FROM python:3.14.2-alpine

RUN apk update && \
    apk add --no-cache gcc musl-dev python3-dev libffi-dev openssl-dev mariadb-dev su-exec

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt

WORKDIR /app

RUN python -m pip install -r requirements.txt

COPY . /app

RUN mkdir -p /app/tmp && chmod a+rwx -R /app/tmp

EXPOSE 5000

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app

USER root
ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app", "--timeout", "300", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"]
