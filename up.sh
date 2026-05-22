#!/bin/bash

WEBSITES_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "-- compose database -- "
docker compose -f $WEBSITES_ROOT/docker-compose.yml up --build -d
echo "-- compose api -- "
docker compose -f $WEBSITES_ROOT/docker-compose-api.yml up --build -d