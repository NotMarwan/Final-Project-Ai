/** @type {import('postcss-load-config').Config} */
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const projectRoot = path.dirname(fileURLToPath(import.meta.url))

const config = {
  plugins: {
    '@tailwindcss/postcss': { base: projectRoot },
  },
}

export default config
