/** @type {import('next').NextConfig} */
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    const backend = 'http://localhost:8002'
    return [
      { source: '/video_feed', destination: backend + '/video_feed' },
      { source: '/alerts', destination: backend + '/alerts' },
      { source: '/health', destination: backend + '/health' },
      { source: '/system/:path*', destination: backend + '/system/:path*' },
      { source: '/face/:path*', destination: backend + '/face/:path*' },
      { source: '/notifications/:path*', destination: backend + '/notifications/:path*' },
      { source: '/reports/:path*', destination: backend + '/reports/:path*' },
      { source: '/cameras/:path*', destination: backend + '/cameras/:path*' },
      { source: '/api/:path*', destination: backend + '/api/:path*' },
      { source: '/clips/:path*', destination: backend + '/clips/:path*' },
      { source: '/audio/:path*', destination: backend + '/audio/:path*' },
      { source: '/security/:path*', destination: backend + '/security/:path*' },
      { source: '/audit/:path*', destination: backend + '/audit/:path*' },
      { source: '/demo_start/:path*', destination: backend + '/demo_start/:path*' },
      { source: '/demo_stop/:path*', destination: backend + '/demo_stop/:path*' },
      { source: '/demo_video/:path*', destination: backend + '/demo_video/:path*' },
      { source: '/download_evidence/:path*', destination: backend + '/download_evidence/:path*' },
      { source: '/download_report/:path*', destination: backend + '/download_report/:path*' },
      { source: '/set_threshold', destination: backend + '/set_threshold' },
      { source: '/set_cooldown', destination: backend + '/set_cooldown' },
      { source: '/switch_camera', destination: backend + '/switch_camera' },
      { source: '/evidence_chain/:path*', destination: backend + '/evidence_chain/:path*' },
      { source: '/decision_layer/:path*', destination: backend + '/decision_layer/:path*' },
    ]
  },
}

export default nextConfig
