#!/bin/bash
echo ""
echo "-- Running Black formatter --"
python -m black .
echo ""
echo "-- Running Pylint --"
python -m pylint ./**/*.py
echo "-- done --"
echo ""