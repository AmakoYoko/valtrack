# Build stage
FROM node:20-alpine AS build
WORKDIR /src

# Copie package.json ET, si présent, package-lock.json
COPY package*.json ./

# Installe les deps (utilise le lock si dispo)
RUN test -f package-lock.json && npm ci || npm install

COPY . .
RUN npm run build

# Serve stage
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
