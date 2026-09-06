# Movimiento ambiental local

`ecosystem.ambient` produce vídeo de una ilustración con desplazamientos suaves
por regiones. Usa `grid_sample` de PyTorch en CUDA y codifica con NVENC bajo el
lease GPU común. No descarga modelos ni dependencias. No escribe una nueva
imagen raster editada: conserva el original y envía los fotogramas del vídeo
directamente al codificador.

Ejecutar `scripts/render-ambient.py manifiesto.json` con el Python CUDA ya
instalado. Requiere PyTorch, NumPy y Pillow en ese entorno y las herramientas
FFmpeg/ffprobe detectadas por el núcleo. Falla si CUDA no está disponible.

Ejemplo de manifiesto local:

```json
{
  "image": ".runtime/inputs/illustration.png",
  "output": ".runtime/work/ambient-v01.mp4",
  "evidence": ".runtime/work/ambient-v01.json",
  "frames": 240,
  "regions": [
    {"id":"water","rect":[0,0.65,1,1],"feather":0.05,"dx":12,"dy":4,"period":3,"spatial_y":40,"spatial_x":8}
  ]
}
```

Salida fija 1080 × 1920 a 24 fps, entre un fotograma y 120 segundos. `rect`
contiene las coordenadas normalizadas izquierda, arriba, derecha y abajo.
`feather` suaviza los bordes; `dx`/`dy` son amplitudes en píxeles; `period`, en
segundos. Los términos espaciales desplazan la fase de la onda dentro de la
región. Los manifiestos son instrucciones locales revisadas, no entradas remotas
arbitrarias. Las regiones deben evitar objetos rígidos y caras; revisar su efecto
en el vídeo real. No aplicar esta técnica a fotografías documentales.

La salida y su evidencia deben ser nuevas. El recibo registra GPU, uso del lease,
hashes, regiones, duración y decodificación; no declara QA artístico independiente.
La prueba B2 produjo 318 fotogramas con la RTX 5070. Esto verifica ejecución
local, no generación local del dibujo inicial ni un porcentaje de ahorro de tokens.

El vídeo puede alimentar una o varias escenas contiguas de `cutout` mediante
`video` e `in_frame`. El reloj y los subtítulos proceden de las primitivas comunes
de `ecosystem.comic_graphics`; los datos editoriales y tiempos viven en el trabajo.
