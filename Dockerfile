FROM node:24-bookworm-slim

WORKDIR /app

COPY package.json ./
COPY packages ./packages
COPY apps ./apps
COPY scripts ./scripts

RUN npm install --omit=dev

RUN mkdir -p /data /keys \
    && chown -R node:node /app /data /keys

USER node

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=8787 \
    HAA_DB_PATH=/data/haa.db \
    HAA_AUTHORITY_KEY_FILE=/keys/authority-key.pem

EXPOSE 8787

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||8787)+'/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "--experimental-strip-types", "apps/haa-server/src/server.ts"]
