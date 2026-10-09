# ADR-004 — Pool único de memória CPU+GPU

- Estado: aceito.
- Data: 2026-10-08.
- Contexto: o PS5 expõe 12 GiB de direct memory compartilhada; o RADV
  a apresenta como GPU integrada. O Eden orçava 4 GiB → GC por frame a
  20–25 FPS; o modo Aggressive (6 GiB) estabilizou em 30 FPS com ~0,9 GB
  de folga (`main.cpp:654-658`). Caches decidem eviction pelo bloco
  livre do pool, não pelo contador do driver — que conta dobrado (VRAM +
  VRAM visível) (`performance.h:110-121`). Tabelas esparsas economizam
  ~1 GiB (`CMakeLists.txt:79-82`); blocos ≥2 MiB alinhados para huge
  pages (`memory_pages.cpp:42-47`); CPU mapeada abaixo de
  `0x4000000000` fora da janela RADV (`memory_pages.cpp:17-27`).

## Decisão

1. VRAM e sysmem nunca são orçadas como pools independentes (NFR-005).
2. "Memória em uso" gráfica = orçamento menos o maior bloco livre do
   pool (`graphics_memory_free`); `graphics_usage=driver` só como A/B.
3. GC (`gc_keep_dirty`) e `kShortMemory` (384 MiB) só mudam com curva de
   retenção/evicção medida no console.
4. `EDEN_PERF_DIRECT` (total, largest_free, free, regions, short) é a
   série de guarda de todo experimento; `largest_free` é métrica crítica
   do gate.

## Consequências

- H-08 mede o cache de shaders antes de qualquer teto novo; H-10 faz
  A/B de huge pages/tabelas esparsas sem mudar defaults.
- Vazamento/crescimento anormal aborta promoção (gate 06 §4).
