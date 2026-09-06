# Validación de la primera versión

Fechas de comprobación local: 5 y 6 de septiembre de 2026.

- Suite actual: 64 pruebas ejecutadas, 63 aprobadas y una regresión GPU optativa
  omitida. Incluye concurrencia real entre conexiones,
  CAS, intents inciertos, verificación dual, alteración de hashes, aislamiento de
  corpus, cápsulas, caché y corrupción de archivos.
- Ocho pruebas de medios incluyen FFmpeg real: decodificación, montaje y ASS en
  rutas Windows con espacios y caracteres especiales.
- Panel probado con Edge sin interfaz: escritorio 1440 px y móvil 390 px, sin
  errores JavaScript ni desbordamiento horizontal. Formulario descargado y JSON
  compatible con el alta de canales comprobado.
- RV1909 indexado localmente: 31.085 pasajes. Libro Doval: 634 fragmentos de un PDF
  de 330 páginas; página 1 sin texto registrada como portada no indexable. Los
  índices y el PDF no se han subido al repositorio.

## GPU: prueba técnica real, no reel aprobado

Se ejecutó Video2X 6.4.0 / RIFE v4.25 en la RTX 5070, con un patrón sintético
720×1280, CFR 24 fps y 125 fotogramas. La salida tiene 250 fotogramas y conserva,
píxel a píxel, todos los 125 originales en sus posiciones pares, además del
extremo final. Entrada, intermedio y resultado se decodificaron completamente.

El protocolo deriva del tratamiento de extremos encontrado en la herramienta
experimental de Religion; **no se promueve automáticamente al perfil activo**.
Usa tres guardas internas que se excluyen del resultado. La entrega contiene
124 intermedios calculados y una retención de un fotograma del extremo nativo.
Esto debe conciliarse con la terminología del contrato antiguo que contaba 125
intermedios antes de habilitar producción con este adaptador.

La herramienta informa procesamiento correcto, pero termina con el código de
fallo de cierre `3221225477`. El primer intento quedó bloqueado al cerrar y se
detuvo desde la sesión de esta prueba. Se incorporó la supresión heredable del
diálogo de fallo de Windows utilizada en el adaptador anterior, conservando el
código real. Ningún código de salida sustituye las pruebas de integridad.

En el patrón 720×1280, el registro del proveedor midió 6 segundos de procesamiento
RIFE para 255 fotogramas internos. No es el tiempo de un reel, no mide generación
de escenas originales y no establece calidad artística. Los artefactos conservan
`editorial_qa_passed=false` y `production_qualified=false`.

La regresión GPU es optativa mediante `ECOSYSTEM_GPU_TEST=1`; el resto de la suite
no enciende modelos. Se verifican hashes del ejecutable y los dos archivos del
modelo, procedencia de fotogramas, salida nueva y liberación de la reserva GPU.

## Pendiente

Completar Religion pro v5, escucha perceptiva del ensayo de ¿Sabías que?,
publicación y verificación pública. Los adaptadores remotos y la migración de
autoridad no están terminados. La automatización diaria se creó pausada; no se
presenta un horario ni una prueba técnica como producción autónoma conseguida.

## Primera prueba completa de cómic 2D

El ensayo «La guerra más breve registrada» tiene 426 fotogramas a 24 fps,
1080 × 1920 y 17,75 segundos. Incluye la cabecera aprobada de 36 fotogramas,
voz Kore previamente aprobada, ilustraciones nuevas, barco con desplazamiento
y balanceo, reloj animado, bandera de rendición y subtítulos literales.

Comprobaciones efectuadas sobre el máster real:

- Decodificación completa, pista de vídeo con inicio cero y cada timestamp a
  su posición exacta en la cadencia de 24 fps.
- Píxeles de los 36 fotogramas de cabecera conservados. Las muestras PCM de la
  narración se conservan en el montaje a +1,5 segundos; la entrega utiliza AAC.
- Transcripción local del máster completo coherente con cabecera y narración;
  sin muestras recortadas por saturación en el análisis de audio.
- Revisión independiente editorial, visual y de subtítulos aprobada para diez
  muestras de contacto y cinco fotogramas completos. Fuentes históricas primarias
  contrastadas; se mantiene la precisión «38–45 minutos, según la fuente».
- Escucha perceptiva independiente **no realizada**. No se afirma QA audiovisual
  completo ni cualificación automática de futuros vídeos a partir de estas muestras.

El render usa NVENC y el lease GPU del núcleo. El recibo local conserva tiempo,
hashes de fuentes, máster y límites de revisión. No se ha publicado el vídeo ni
activado la producción diaria. Este ensayo no mide un ahorro porcentual de tokens.

Religion tiene su prueba [pro v5](RELIGION-PRO-V5.md) preparada, pendiente de
recuperar el control de un navegador compatible. No existe aún su máster de ensayo.
