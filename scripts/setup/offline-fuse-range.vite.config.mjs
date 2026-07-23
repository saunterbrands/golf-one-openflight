import fs from 'node:fs';
import path from 'node:path';

const sourceDir = process.env.FUSE_SOURCE_DIR;
const outputDir = process.env.FUSE_OUTPUT_DIR;

if (!sourceDir || !outputDir) {
  throw new Error('FUSE_SOURCE_DIR and FUSE_OUTPUT_DIR are required');
}

const canonicalSourceDir = fs.realpathSync(sourceDir);

export default {
  root: path.resolve(canonicalSourceDir, 'examples'),
  base: './',
  publicDir: path.resolve(canonicalSourceDir, 'public'),
  resolve: {
    alias: {
      '@opengolfsim/fuse': path.resolve(canonicalSourceDir, 'src/index.ts'),
      '@': path.resolve(canonicalSourceDir, 'src'),
    },
  },
  build: {
    sourcemap: false,
    outDir: path.resolve(outputDir),
    emptyOutDir: true,
    target: 'es2020',
    chunkSizeWarningLimit: 5000,
    rollupOptions: {
      input: {
        range: path.resolve(canonicalSourceDir, 'examples/range/index.html'),
      },
    },
  },
};
