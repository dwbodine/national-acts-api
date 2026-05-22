#!/bin/bash

WEBSITES_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

aws ecr get-login-password --region us-east-1 --profile deployment_nationalacts | docker login --username AWS --password-stdin 804363746695.dkr.ecr.us-east-1.amazonaws.com
DOCKER_BUILDKIT=1 docker build --no-cache -f $WEBSITES_ROOT/MySql.Dockerfile -t nationalactsvip/nationalactsdb .
docker tag nationalactsvip/nationalactsdb:latest 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsdb:latest
docker push 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsdb:latest