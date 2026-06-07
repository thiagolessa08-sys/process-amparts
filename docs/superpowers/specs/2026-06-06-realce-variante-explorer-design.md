# Realce/animação do caminho de uma variante no Variant Explorer

Data: 2026-06-06

## Objetivo

No Variant Explorer ([frontend/src/ScreenExplorer.jsx](../../../frontend/src/ScreenExplorer.jsx)),
permitir que o usuário reproduza o caminho de uma variante específica: uma linha
luminosa é "desenhada" do INÍCIO ao FIM seguindo exatamente os nós e desvios
daquela variante — inspirado no caminho destacado do Celonis.

## Comportamento

- Cada linha de variante (`.vrow`) ganha um botão **▶ play** independente da
  checkbox de seleção. Clicar nele **não** altera a seleção (`e.stopPropagation`).
- Ao dar play, o grafo continua mostrando a **união das variantes selecionadas**,
  mas desenha por cima uma **linha luminosa** percorrendo o caminho da variante.
  Nós usados pela variante que não estavam na seleção são **adicionados
  temporariamente** (`graphData` = `selectedIds ∪ {playingId}`).
- A linha é desenhada do começo ao fim, **repete 2 vezes** e fica destacada
  (estática) ao terminar. O botão vira **■ stop** durante a reprodução.
- **Stop** (ou dar play em outra variante) limpa o realce e troca o foco.

## Abordagem técnica (escolhida)

Linha SVG única animada por `stroke-dashoffset`:

- **Estado em `ExplorerScreen`:** `playingId` (variante em foco ou `null`),
  `replayKey` (incrementa a cada play → reinicia a animação via `key`).
- **Sidebar:** botão play/stop dentro de `.vrow`, com `stopPropagation`. Ícone
  `play` já existe; adicionar `stop` (quadrado) em `icons.jsx`.
- **Grafo:** `graphData` construído sobre `selectedIds ∪ {playingId}`. A variante
  em foco é passada ao `Graph`.
- **Geometria:** no `useLayoutEffect` que já mede `nodeRefs`, montar a string `d`:
  terminal INÍCIO → 1º nó do `path` → segmentos consecutivos (reto pelo centro
  quando adjacentes na coluna; curva de *bypass* quando é pulo) → último nó →
  terminal FIM. Adicionar `ref` aos dois `.terminal`. Renderizar
  `<path className="variant-trace">` sobreposto no `.bypass-svg`.
- **Animação:** `@keyframes` de `dashoffset: L → 0`, `iteration-count: 2`,
  `fill: both`. `onAnimationEnd` devolve o botão a ▶. Cor roxa com `drop-shadow`.

## Arquivos

- `frontend/src/ScreenExplorer.jsx` — estado, botão, união, geometria, render.
- `frontend/src/icons.jsx` — ícone `stop`.
- `frontend/src/theme.css` — `.variant-trace`, `.vplay`, keyframes.

## Casos de borda

- Stop no meio limpa tudo.
- Play em B durante A: troca foco e reinicia.
- Variante de 1 nó: INÍCIO → nó → FIM.
