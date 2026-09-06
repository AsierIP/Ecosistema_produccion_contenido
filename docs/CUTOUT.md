# Adaptador local de animación por recortes

`ecosystem.cutout` monta ilustraciones, capas móviles, dibujos ASS y subtítulos
en un MP4 vertical. La cabecera aprobada se conserva por copia de vídeo; el
cuerpo se codifica con NVENC bajo el lease GPU común. Es un adaptador manual de
montaje: no genera ilustraciones ni voz, no publica y no activa `daily`.

El resultado `TECHNICAL_PASS` acredita las comprobaciones descritas abajo.
Mantiene `production_qualified: false` y ambas revisiones independientes en
`PENDING`. La elección de estilo, las licencias y la autorización para publicar
siguen perteneciendo al perfil y a la revisión del canal.

## Requisitos y ejecución

- Python 3.12 o posterior y las herramientas locales detectadas por `doctor`.
- FFmpeg con `ass`/libass, `overlay`, `concat` y `h264_nvenc`; ffprobe y una GPU
  NVIDIA compatible. Se pueden fijar `ECOSYSTEM_FFMPEG` y `ECOSYSTEM_FFPROBE`.
- Cabecera de 36 fotogramas, 1080 × 1920 y 24 fps, con audio que cubra 1,5 s.
  El vídeo se concatena por copia: usar H.264 High, yuv420p y dos B-frames,
  compatible con el cuerpo. Una cabecera con parámetros incompatibles puede
  fallar las comprobaciones finales; no se recodifica automáticamente.
- Narración WAV PCM16, mono y 48 000 Hz, con duración natural ya aprobada.
- Ilustraciones locales, capas con transparencia cuando se necesite y un ASS
  con fuentes instaladas. Los originales se leen y se comprueban por hash.

Desde la raíz del repositorio:

```powershell
python -m ecosystem doctor
python scripts/render-cutout.py examples/cutout/manifest.json
```

El ejemplo es una plantilla de seis segundos de narración y 1,5 s de cabecera.
Sus entradas de audio, vídeo e imagen son referencias a archivos locales que
hay que aportar; no se incluyen medios ni se descargan recursos. Sustituirlas
y ajustar los tiempos al audio real antes de ejecutar. Para producción diaria,
ejecutar primero `python -m ecosystem daily` y respetar sus bloqueos.

## Manifiesto

Ver [manifest.json](../examples/cutout/manifest.json) y el
[ASS de ejemplo](../examples/cutout/captions.ass). Todas las rutas relativas se
resuelven desde el directorio de ejecución, **no desde el directorio del JSON**.
El argumento `root` de la función Python solo determina el almacén del lease
GPU. Por eso los comandos anteriores se ejecutan desde la raíz del proyecto.

| Campo | Contrato |
| --- | --- |
| `fps`, `width`, `height` | Valores admitidos: 24, 1080 y 1920. Son también los valores predeterminados. |
| `intro` | Ruta de la cabecera aprobada de 36 fotogramas. |
| `narration` | Ruta del WAV aprobado; no se cambia velocidad ni tono. |
| `ass` | Subtítulos y gráficos del cuerpo, con tiempos desde el comienzo de la narración. |
| `work_dir` | Carpeta nueva o vacía para intermedios y registros de este intento. |
| `evidence_dir` | Carpeta local sin un `technical-qa.json` anterior. Puede contener el manifiesto y las entradas de revisión. |
| `output` | MP4 nuevo; no puede coincidir con `body.mp4` ni `intro-video.mp4` de la carpeta de trabajo. |
| `scenes` | Lista ordenada de escenas, cada una con un número entero positivo de `frames`. |
| `end_card_seconds` | Observación final opcional de 0 a 5 segundos. Amplía el vídeo, sin repetir ni estirar la voz. Predeterminado: 0. |

Los campos editoriales añadidos al JSON no se convierten en gates: el adaptador
no interpreta un título, una lista de fuentes o una declaración de permiso
como aprobación. Conservar esas evidencias en el expediente del trabajo.

Cada escena acepta `image` como fondo, o `color` si no hay imagen. El color
predeterminado es `0xFFF1D2`. Una imagen de fondo se amplía manteniendo proporción
y se recorta a 1080 × 1920. `background_filter` permite sustituir ese tratamiento
por una cadena FFmpeg local revisada que debe entregar ese mismo tamaño y
mantener la cadencia. No cargar manifiestos ni expresiones de procedencia no
confiable: los filtros se interpretan como instrucciones de composición.

`layers` contiene capas en orden de fondo a primer plano. Cada capa requiere
`image`, `width`, `x` e `y`. `width` es su anchura en píxeles; la altura conserva
la proporción. Las coordenadas aceptan expresiones de `overlay`, como
`"-300+420*min(t/2,1)"`. El tiempo `t` empieza en cero en **cada escena**. El ASS
se aplica después de reunir todas las escenas, sobre las capas de imagen.

Las imágenes fijas permanecen visibles durante los fotogramas asignados y sus
capas pueden moverse. Este contrato de ilustración 2D no cambia las reglas de
fuentes nativas o RIFE de otros perfiles. El adaptador no usa RIFE.

Una escena también puede aportar `video` e `in_frame` (entero, predeterminado 0).
Debe existir suficiente metraje a 24 fps para el tramo: el adaptador recorta el
intervalo indicado sin hacer bucles y conserva el hash de ese vídeo. Permite
utilizar la animación local continua de [ambient](AMBIENT.md). Los tiempos de
`background_filter` empiezan en cero en cada escena después del recorte.

## Duración, audio y subtítulos

Si la narración contiene `N` muestras a 48 000 Hz, el cuerpo debe sumar
`ceil(N × 24 / 48000)` fotogramas, más `round(end_card_seconds × 24)` cuando
se solicita una observación final. El total de vídeo es ese número más 36.
Se redondea únicamente el final visual, menos de un fotograma; la narración
conserva todas sus muestras y su duración.

El montaje PCM coloca la narración en la muestra 72 000, después de los 1,5 s
de audio de cabecera. Se verifica la igualdad exacta de sus muestras antes de
codificar el audio final a AAC. El AAC entregado es una compresión con pérdida;
la igualdad de muestras se refiere al intermedio PCM, no a su decodificación.

Los tiempos del ASS excluyen la cabecera: un subtítulo a `0:00:01.00` aparece
a los 2,5 s del máster. Deben seguir el texto literal y los tiempos reales de
la voz; el compositor no transcribe ni alinea automáticamente. Los colores ASS
usan `AABBGGRR`. El ejemplo distingue el estilo `Caption` del estilo `Graphic`
y demuestra un dibujo vectorial sencillo. Es una muestra técnica, sin aprobación
de estilo para ningún canal.

## Evidencia y recuperación

La salida compacta muestra estado, ruta, SHA-256, duración, fotogramas y
`NOT_PUBLISHED`. El recibo completo es `evidence_dir/technical-qa.json` y contiene:

- Probe y decodificación completa del MP4.
- Recuento final, inicio en cero, 24 fps y timestamp exacto de cada fotograma.
- Igualdad de píxeles decodificados de los 36 fotogramas de cabecera.
- Igualdad de las muestras originales de narración en el intermedio PCM.
- Hashes de entradas y máster, y comprobación de que las entradas no cambiaron.
- Duración de la fase de render, codificador y uso del lease GPU.

El tiempo de render no mide todo el trabajo, consumo de tokens ni coste externo.
La revisión editorial debe comprobar las afirmaciones, licencias y literalidad
de subtítulos; la audiovisual, el máster real completo, sincronía, legibilidad,
continuidad, movimiento y audio. El recibo técnico no certifica esas condiciones.

Un fallo deja intermedios y registros para diagnosticarlo. Conservarlos y crear
otro `work_dir`, `evidence_dir` y nombre de salida para el siguiente intento;
no borrar evidencia para forzar el mismo comando. Una salida existente o una
carpeta de trabajo ocupada se rechaza antes de renderizar, y un recibo anterior
no se sobrescribe. No ejecutar dos intentos sobre las mismas carpetas.

Guardar manifiestos reales, ASS con contenido de producción, logs, recibos y
medios bajo `.runtime/` o en el almacenamiento local autorizado. Las rutas
absolutas y las referencias privadas de los recibos quedan fuera de Git. El
ejemplo versionado contiene únicamente texto ficticio y rutas genéricas.
