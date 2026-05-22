#!/bin/bash

WEBSITES_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

aws ecr get-login-password --region us-east-1 --profile deployment_nationalacts | docker login --username AWS --password-stdin 804363746695.dkr.ecr.us-east-1.amazonaws.com
DOCKER_BUILDKIT=1 docker build --no-cache -f $WEBSITES_ROOT/MySqlBackup.Dockerfile -t nationalactsvip/mysql-backup .
docker tag nationalactsvip/mysql-backup:latest 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/mysql-backup:latest
docker push 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/mysql-backup:latest