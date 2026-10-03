# Sabi Operations Console image: build the static bundle with Vite, then serve
# it with nginx. The console talks to the API gateway same-origin through the
# `/v1` path, so nginx proxies `/v1` to the gateway and falls back to index.html
# for the client-side router.
#
# Built from the repository root:
#
#   docker build -f infra/docker/console.Dockerfile \
#     --build-arg SABI_API_ORIGIN=https://api.sabi.ahmadkhidir.com -t <image> .

FROM node:22-slim AS build

WORKDIR /app

COPY apps/console/package.json apps/console/package-lock.json ./
RUN npm ci

COPY apps/console/ ./
# The build command is the package's own `build` script (tsc + vite build).
RUN npm run build

FROM nginx:1.27-alpine

# The gateway origin is read at container build time and written into the nginx
# config, so the same image serves any environment's gateway.
ARG SABI_API_ORIGIN=http://localhost:8000
ENV SABI_API_ORIGIN=${SABI_API_ORIGIN}

COPY infra/docker/console-nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

# The nginx image renders /etc/nginx/templates/*.template into conf.d at startup,
# substituting ${SABI_API_ORIGIN}.
