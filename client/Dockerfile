FROM node:22 AS build

WORKDIR /client

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# API base URL is baked in at build time by Vite. The endpoints already include
# the `api/` prefix, so this is the site root - nginx proxies /api/ through to
# the server container locally, Traefik routes it in production.
ARG VITE_BASE_URL=/
ENV VITE_BASE_URL=$VITE_BASE_URL

RUN npm run build

# Serve the static build with nginx
FROM nginx:alpine

COPY --from=build /client/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
