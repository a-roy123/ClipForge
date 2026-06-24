# ==========================================
# Stage 1: Build the static production assets
# ==========================================
FROM node:20-alpine AS build

WORKDIR /app

# Handle dependency installation via isolated cache layers
COPY package*.json ./
RUN npm install

# Ingest full client application codebase context
COPY . .

# Capture and inject build-time environmental variables for static compilation
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# Compile codebase and purge unused CSS utility properties
RUN npm run build

# ==========================================
# Stage 2: Deploy and execute the proxy server
# ==========================================
FROM nginx:alpine

# Stream compiled client assets direct to the Nginx content hosting pathway
COPY --from=build /app/dist /usr/share/nginx/html

# Deploy your proxy config context (handling /api and /ws socket upgrades) directly to virtual hosts directory
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80