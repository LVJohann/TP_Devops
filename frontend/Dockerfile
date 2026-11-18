# syntax=docker/dockerfile:1

# Image nginx officielle qui tourne sans root (port 8080 au lieu de 80)
FROM nginxinc/nginx-unprivileged:1.28-alpine

# URL de l'API vers laquelle nginx relaie /api/* (surchargée par compose / k8s)
ENV API_URL=http://api:8000

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY public/ /usr/share/nginx/html/

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
