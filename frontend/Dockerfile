FROM node:24-alpine AS builder

WORKDIR /app

RUN npm install -g pnpm@10.24.0

# workspace 전체 필요 (pnpm lockfile이 모든 패키지 참조)
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ ./packages/
COPY frontend/ ./frontend/
COPY admin/ ./admin/

RUN pnpm install --frozen-lockfile
RUN pnpm --filter frontend build

FROM node:24-alpine

WORKDIR /app

# @astrojs/node standalone 산출물은 일부 패키지를 런타임 external import한다. pnpm의
# frontend/node_modules symlink가 루트 .pnpm 저장소를 가리키므로 둘을 함께 복사한다.
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/frontend/node_modules ./frontend/node_modules
COPY --from=builder --chown=node:node /app/frontend/dist ./frontend/dist

ENV HOST=0.0.0.0
ENV PORT=4321

EXPOSE 4321

USER node

CMD ["node", "./frontend/dist/server/entry.mjs"]
