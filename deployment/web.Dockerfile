FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS build
RUN corepack enable && corepack prepare pnpm@10.17.1 --activate
WORKDIR /workspace
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY edw-web/package.json edw-web/package.json
RUN pnpm install --frozen-lockfile
COPY edw-web/index.html edw-web/eslint.config.js edw-web/tsconfig.app.json edw-web/tsconfig.json edw-web/tsconfig.node.json edw-web/vite.config.ts edw-web/
COPY edw-web/src edw-web/src
RUN pnpm --filter edw-web build
FROM nginx:1.29.1-alpine3.22@sha256:42a516af16b852e33b7682d5ef8acbd5d13fe08fecadc7ed98605ba5e3b26ab8
ARG EID_SOURCE_FINGERPRINT
LABEL io.eid.source-fingerprint="${EID_SOURCE_FINGERPRINT}"
COPY --from=build /workspace/edw-web/dist /usr/share/nginx/html
COPY deployment/nginx/web.conf /etc/nginx/conf.d/default.conf
