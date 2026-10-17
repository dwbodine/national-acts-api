#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Commit the release first; refusing to tag an uncommitted build" >&2
  exit 1
fi
REVISION="$(git rev-parse HEAD)"
REPOSITORY="804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsapi"
aws ecr get-login-password --region us-east-1 --profile deployment_nationalacts |
  docker login --username AWS --password-stdin "${REPOSITORY%%/*}"
# Enable ECR tag immutability too, to protect against concurrent publishers.
if aws ecr describe-images --region us-east-1 --profile deployment_nationalacts \
    --repository-name nationalactsvip/nationalactsapi --image-ids "imageTag=$REVISION" >/dev/null 2>&1; then
  echo "Release tag already exists: $REVISION" >&2
  exit 1
fi
docker build --label "org.opencontainers.image.revision=$REVISION" -t "$REPOSITORY:$REVISION" .
docker push "$REPOSITORY:$REVISION"
DIGEST="$(aws ecr describe-images --region us-east-1 --profile deployment_nationalacts \
  --repository-name nationalactsvip/nationalactsapi --image-ids "imageTag=$REVISION" \
  --query 'imageDetails[0].imageDigest' --output text)"
echo "On EC2: bash release-api.sh '$REPOSITORY@$DIGEST'"
