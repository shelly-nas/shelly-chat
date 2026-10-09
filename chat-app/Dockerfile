FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# BACKEND_URL is only used at build time for the rewrite config
ARG BACKEND_URL=http://generating:8000
ENV BACKEND_URL=${BACKEND_URL}
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Set BACKEND_URL for runtime API routes
ARG BACKEND_URL=http://generating:8000
ENV BACKEND_URL=${BACKEND_URL}
# standalone output includes its own node_modules subset
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
