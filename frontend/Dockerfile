# syntax=docker/dockerfile:1.7
# EMF-Visu frontend: static build served by nginx, which also proxies /api to the API service.
# Build context: ./frontend
# Base images are overridable so a registry mirror can be used (see README).
ARG NODE_IMAGE=node:22-slim
ARG NGINX_IMAGE=nginx:1.29-alpine
FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
# The optional "extra_ca" build secret lets the build work behind a TLS-inspecting proxy.
RUN --mount=type=secret,id=extra_ca,target=/run/extra-ca.pem,required=false \
    if [ -s /run/extra-ca.pem ]; then export NODE_EXTRA_CA_CERTS=/run/extra-ca.pem; fi && \
    npm install -g pnpm@10.28.0 && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM ${NGINX_IMAGE}
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
