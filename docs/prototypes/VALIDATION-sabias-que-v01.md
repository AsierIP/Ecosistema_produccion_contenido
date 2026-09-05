# Validación del prototipo de estilo · 5 de septiembre de 2026

Se generaron tres referencias visuales con `image_gen` integrado, usando la
misma escena y paleta. El usuario eligió C · Cómic plano. Los prompts exactos
están en `sabias-que-v01.json`. Las tres imágenes se conservaron en
`media/style-prototypes/sabias-que/v01/`, fuera de Git.

Se renderizó `c-muestra-camara-v01.mp4` localmente con
`ecosystem.style_preview.render_style_preview`, encoder `h264_nvenc` y reserva
exclusiva de GPU. Salida comprobada: H.264, 1080×1920, 24 fps, 144 fotogramas,
6 segundos, sin audio y decodificación íntegra. El recibo local
`c-muestra-camara-v01.preview.json` vincula fuente y salida mediante SHA256.

La muestra usa un acercamiento centrado de 1,035× sobre una sola imagen. Sirve
para evaluar encuadre y cámara. No demuestra animación del personaje, sincronía
con voz, calidad editorial ni un reel terminado. La calificación de animación
de producción permanece pendiente y bloquea la activación del canal.

Uso reutilizable: pasar PNG, MP4 nuevo, `approved_source_sha256`,
`encoder="h264_nvenc"` y `execute=True` a `render_style_preview`. Sin ejecución
explícita devuelve el plan; `libx264` selecciona CPU. No cambia de encoder
silenciosamente ni sobrescribe muestras o recibos.
