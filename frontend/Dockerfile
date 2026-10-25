FROM node:20-slim AS build
WORKDIR /app

# npm ci si un package-lock.json est présent (build reproductible), sinon repli sur npm install
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then \
      npm ci --no-audit --no-fund; \
    else \
      echo "WARNING: package-lock.json absent -> npm install (commitez un lockfile pour utiliser npm ci)" && \
      npm install --no-audit --no-fund; \
    fi

COPY . .

ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV GENERATE_SOURCEMAP=false
# Nécessaire pour une CSP sans 'unsafe-inline' sur les scripts
ENV INLINE_RUNTIME_CHUNK=false

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
