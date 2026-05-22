#!/bin/bash
docker compose rm -s -v -f nationalactsapi
docker rmi 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi:latest
docker pull 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi:latest
docker compose up -d --no-deps nationalactsapi