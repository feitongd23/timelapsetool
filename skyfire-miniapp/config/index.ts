import { defineConfig } from '@tarojs/cli'

export default defineConfig({
  projectName: 'skyfire-miniapp',
  sourceRoot: 'src',
  outputRoot: 'dist',
  framework: 'react',
  compiler: 'webpack5',
  plugins: [],
  designWidth: 750,
  deviceRatio: { 640: 2.34 / 2, 750: 1, 828: 1.81 / 2 },
  mini: {
    postcss: {
      autoprefixer: { enable: true },
      cssModules: { enable: false }
    }
  }
})
