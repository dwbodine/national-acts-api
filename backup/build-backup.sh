#!/bin/bash
docker compose rm -s -v -f mysql-backup
docker rmi 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/mysql-backup:latest
docker pull 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/mysql-backup:latest
docker compose up -d --no-deps mysql-backup