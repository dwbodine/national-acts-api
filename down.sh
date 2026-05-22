#!/bin/bash

WEBSITES_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "-- compose down --"
docker compose -f $WEBSITES_ROOT/docker-compose-api.yml down -v
docker compose -f $WEBSITES_ROOT/docker-compose.yml down -v --remove-orphans
echo "-- removing images --"
docker rmi nationalactsdb:latest
docker rmi nationalactsvip/nationalactsapi:latest
echo "-- removing builds --"
docker buildx history rm --all
docker builder prune --all --force