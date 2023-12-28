FROM mariadb:10.6.16

ENV MYSQL_ROOT_PASSWORD=All41n14@ll \
    MYSQL_DATABASE=nationalacts20

ADD nationalacts20.sql /docker-entrypoint-initdb.d

EXPOSE 3306