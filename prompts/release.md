# Etapa release

## Contrato del ejecutor Upro

Si la entrada contiene `youtube_operation_v1`, ejecutar únicamente esa operación.
Leer `operation.json` en la carpeta de salida: el código local ya ha persistido
y reservado su intent. No crear otro intent ni realizar otra fase.
Para `upload`, comprobar la cuenta exacta en Studio, subir el máster declarado,
aplicar los metadatos declarados y guardar como PRIVADO. No programar ni publicar.
Registrar `youtube-result.json` con `account_id`, `video_id`, `master_sha256`,
`privacyStatus=private`, `upload_complete=true`, `never_public=true`,
`upload_completed_at` real con zona horaria y `evidence` de la verificación.
Para `schedule`, abrir únicamente el vídeo del intent, confirmar cuenta y estado
privado y programar el `publishAt` guardado. Registrar cuenta, vídeo, hash,
`privacyStatus=private`, `publishAt`, `scheduled=true` y evidencia observada.
Si la fecha ha vencido, bloquear y reconciliar; nunca programar una fecha pasada.
En ambos casos incluir ese JSON en los artefactos del recibo estructurado.
Un ACCEPT acredita solamente la operación reservada, nunca publicación pública.
Estas instrucciones específicas limitan las reglas generales siguientes.
Para `verify_public`, hacer únicamente una comprobación de lectura del vídeo
guardado en el intent. No subir, programar ni pulsar Publicar. Acreditar URL
pública canónica de ese ID, cuenta exacta y correspondencia con el máster.
No confundir verlo con una sesión propietaria con acceso público. Registrar
`account_id`, `url`, `master_sha256`, `public_verified=true` y evidencia real de
acceso público en `youtube-result.json`. Si aún no es público, devolver BLOCK.

## YouTube: regla común para todos los canales

La política `youtube_release` de la cápsula prevalece sobre antiguos horarios o
peticiones de vista previa. Tras QA completo, subir automáticamente como privado,
sin aprobación del usuario. Registrar la finalización real de la subida y fijar
la publicación en YouTube dos horas después de ese instante (7200 segundos).
Usar `ecosystem.release.youtube_schedule` para calcular la fecha UTC; mostrar la
hora local de Europe/Madrid cuando Studio la solicite. Si Studio solo permite
minutos, redondear hacia arriba: nunca acortar las dos horas.

Guardar un intent separado `schedule` ligado a vídeo, cuenta, hash y fecha antes
de confirmar la programación. Verificar en YouTube la privacidad y la fecha
programada. Un reinicio no reinicia las dos horas ni duplica la subida. Una fecha
ya vencida requiere reconciliar; nunca enviarla como programación nueva porque
podría publicar de inmediato. No marcar el trabajo publicado ni completo por
estar programado: verificar la URL pública después de la hora prevista.
Esta regla no reactiva líneas pausadas ni omite QA, licencias o autenticación.

Preparar ese intent mediante `prepare-youtube-schedule --upload-intent ID`.
El recibo verificado de `upload` debe contener `account_id`, `video_id`,
`master_sha256`, `privacyStatus=private`, `upload_complete=true`,
`never_public=true`, `upload_completed_at` con zona horaria y `evidence`.
La preparación es local: no confirma nada en YouTube. El recibo remoto de
`schedule` debe coincidir en cuenta, vídeo, hash y `publishAt`, y acreditar
`privacyStatus=private`, `scheduled=true` y `evidence`. No inventar esos valores.

Publicador preferente: adaptador oficial operativo. Cuando la cápsula autorice navegador porque el adaptador no esté listo: `gpt-5.6-terra`, razonamiento `low`.

Lee la cápsula, el destino confirmado, la autoridad del canal/idioma, el recibo de QA independiente y el máster final. Comprueba que título, descripción, divulgación IA, licencia y hash corresponden al trabajo. Identidad ausente o dudosa implica bloqueo de esa plataforma.

Antes de subir o publicar, exige un intent durable con clave idempotente. Si existe intento enviado o resultado incierto, reconcilia el estado remoto antes de actuar. No dupliques subidas, no cambies de cuenta y no interpretes una autorización de otro canal como propia.

Publica únicamente el máster y metadatos aprobados dentro del alcance autorizado. En Religion conserva el orden YouTube público verificado antes de TikTok. Respeta el orden del perfil en otros canales. Un fallo de la segunda plataforma no invalida ni repite la publicación verificada de la primera.

Comprueba la URL pública, identidad del destino y correspondencia del contenido. No declares éxito por un formulario enviado, una tarjeta de Studio, visibilidad privada o revisión pendiente. Conserva intent y resultado parcial. Si hay autenticación manual o un reto humano, solicita solo la intervención pendiente mediante el coordinador; no lo resuelvas ni lo eludas.

Devuelve **solo el recibo estructurado de la cápsula** con resultado por plataforma, ID/URL, momento y evidencia de verificación, hash del máster, intent y bloqueos. No inventes URLs ni evidencia. No expongas claves, cookies, correos privados o códigos de acceso.
