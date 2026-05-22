#!/bin/bash
docker compose down -v
docker system prune --all --volumes --force
aws s3 cp s3://nationalactsvip-mysql-seeds/nationalacts20.sql ./seeds/nationalacts20.sql
docker compose up -d
docker compose -f docker-compose-import.yml run --rm db-import
