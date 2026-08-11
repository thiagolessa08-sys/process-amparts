import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
//
// O app é servido em https://www.processintelligence.com.br/amparts — não na
// raiz do domínio. `base` reescreve as URLs dos assets no index.html gerado, e
// `outDir` põe o build dentro de `dist/amparts` para que o servidor estático
// (`serve dist`) exponha exatamente esse caminho. Mudar um sem o outro quebra:
// os assets passam a ser buscados num caminho que não existe.
export default defineConfig({
  base: '/amparts/',
  build: { outDir: 'dist/amparts' },
  plugins: [react()],
})
