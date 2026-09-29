import type { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'AI Sentinel - Surveillance System',
    short_name: 'AI Sentinel',
    description: 'Real-Time Violence Detection System - Security Operations Center Dashboard',
    start_url: '/',
    display: 'standalone',
    orientation: 'any',
    background_color: '#090c0e',
    theme_color: '#090c0e',
    categories: ['security', 'surveillance', 'monitoring'],
    icons: [
      {
        src: '/icon-192x192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        src: '/icon-512x512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icon-512x512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  }
}
