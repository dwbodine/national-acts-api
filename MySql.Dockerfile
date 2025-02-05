FROM mariadb:10.6.20

ENV MYSQL_ROOT_PASSWORD=All41n14@ll \
    MYSQL_DATABASE=nationalacts20

COPY ./nationalacts_2025-02-05.sql /docker-entrypoint-initdb.d/

EXPOSE 3306