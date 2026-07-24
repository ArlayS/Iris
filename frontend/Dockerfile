FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install --force
COPY . .

# Récupère l'ARG passé par docker-compose et l'expose comme variable d'env pour le build
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN npm run build

# Utilisation de Nginx pour servir le build statique en production
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
