import { defineConfig, enforceTdd } from '@nizos/probity'

export default defineConfig({
  rules: [
    {
      files: ['api/**/*.py', 'live/**/*.py'],
      rules: [enforceTdd()],
    },
  ],
})
