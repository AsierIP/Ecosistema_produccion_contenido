# Validación de la primera versión

Fecha de comprobación local: 5 de septiembre de 2026.

- Suite central: 55 pruebas aprobadas. Incluye concurrencia real entre conexiones,
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

Prueba real de cada estilo, narración, música, sincronización, publicación y
verificación pública. Los adaptadores remotos y la migración de autoridad no
están terminados. La automatización diaria se creó pausada; no se presenta un
horario ni una prueba técnica como producción autónoma conseguida.
