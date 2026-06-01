FROM node:20-alpine

RUN addgroup -S app && adduser -S appuser -G app

WORKDIR /app

COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN chown -R appuser:app /app

USER appuser

EXPOSE 3000
CMD ["npm", "run", "dev"]
