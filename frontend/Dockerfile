FROM node:20-slim AS build

WORKDIR /app

COPY package*.json ./
# À modifier dans votre frontend/Dockerfile
RUN npm install --legacy-peer-deps


COPY . .
RUN npm run build

# Utilisation de Nginx pour servir le build statique en production
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
