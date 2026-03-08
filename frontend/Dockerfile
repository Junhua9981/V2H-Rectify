# ── Stage 1: 編譯 React/Vite 前端 ──────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# 先複製 package*.json，利用 Docker layer cache 加速安裝
COPY package.json package-lock.json* ./
RUN npm ci

# 複製原始碼並執行 production build
COPY . .
RUN npm run build

# ── Stage 2: 以 nginx 提供靜態檔案 ──────────────────────────────
FROM nginx:1.27-alpine

# 複製編譯產物
COPY --from=builder /app/dist /usr/share/nginx/html

# 複製自訂 nginx 設定
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
