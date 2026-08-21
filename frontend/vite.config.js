import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The FastAPI backend is the single source of truth. In dev we proxy its routes
// so the relative image URLs the API returns ("/images/123.jpg") resolve without
// any rewriting on the client.
const API = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'
// Only API routes are proxied. `/browse/:section` is a client-side route, so
// the API's browse endpoint lives under `/catalog` to avoid the collision.
const proxied = ['/recommend', '/health', '/images', '/products', '/categories', '/catalog']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxied.map((path) => [path, { target: API, changeOrigin: true }])
    ),
  },
})
