FROM node:22-alpine
WORKDIR /app
COPY package.json ./
COPY server ./server
COPY public ./public
ENV NODE_ENV=production PORT=3000 DB_PATH=/data/diagnostico.sqlite
VOLUME ["/data"]
EXPOSE 3000
USER node
CMD ["node", "--no-warnings=ExperimentalWarning", "server/index.js"]
