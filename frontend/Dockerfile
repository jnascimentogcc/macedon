# syntax=docker/dockerfile:1

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
# The API and Keycloak addresses are compiled in: edit src/app/config.ts to change them.
RUN npm run build -- --configuration production


FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/macedon-web/browser /usr/share/nginx/html
EXPOSE 8080
