FROM node:24.18.0-bookworm-slim AS build
WORKDIR /app
RUN npm install --global pnpm@11.19.0
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/index.html apps/web/vite.config.ts apps/web/tsconfig.json apps/web/tsconfig.app.json apps/web/tsconfig.node.json ./
COPY apps/web/src ./src
RUN pnpm build

FROM nginx:1.31.0-alpine3.23
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
