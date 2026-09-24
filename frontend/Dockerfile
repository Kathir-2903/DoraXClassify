# ---- deps ------------------------------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---- dev: Vite dev server with HMR (source is bind-mounted by compose) ----------
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---- build -------------------------------------------------------------------------
FROM deps AS build
COPY . .
ARG VITE_API_URL=""
ARG VITE_SHOW_DEMO_LOGINS="true"
ENV VITE_API_URL=$VITE_API_URL VITE_SHOW_DEMO_LOGINS=$VITE_SHOW_DEMO_LOGINS
RUN npm run build

# ---- prod: static files on nginx, /api proxied to the backend --------------------
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
