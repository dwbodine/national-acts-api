FROM mariadb:10.6.18

ENV MYSQL_ROOT_PASSWORD=All41n14@ll \
    MYSQL_DATABASE=nationalacts20

COPY ./nationalacts_2024-09-20.sql /docker-entrypoint-initdb.d/

EXPOSE 3306