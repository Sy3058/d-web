FROM node:24-alpine AS builder

WORKDIR /app

RUN npm install -g pnpm@10.24.0

# workspace 전체 필요 (pnpm lockfile이 모든 패키지 참조)
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ ./packages/
COPY admin/ ./admin/
COPY frontend/ ./frontend/

RUN pnpm install --frozen-lockfile
RUN pnpm --filter admin build

FROM nginx:alpine

COPY --from=builder /app/admin/dist /usr/share/nginx/html
COPY admin/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
