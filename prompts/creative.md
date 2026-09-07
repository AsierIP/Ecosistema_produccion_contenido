# Etapa creative

Usa el modelo y esfuerzo indicados en la cápsula; conserva las excepciones del canal.

Lee exclusivamente la cápsula, el perfil y las entradas referenciadas necesarias. Comprueba identidad del trabajo, versión del perfil, integridad de fuentes y espacio de escritura permitido. Si falta una entrada esencial, devuelve un recibo de bloqueo.

Selecciona un tema elegible sin repetir contenido ya registrado. Produce un guion breve que respete audiencia, duración, voz e intención del canal. Cada afirmación verificable debe conservar una referencia concreta. Distingue cita literal, contexto y adaptación editorial; no inventes hechos, páginas o atribuciones. Aplica la revisión propia del dominio del canal.

Si el canal define `closing.required`, termina el guion con `closing.spoken_text` exactamente una vez, usando la misma voz e incluyéndolo en los subtítulos literales. Es un cierre editorial, no una afirmación atribuida a la fuente.

Prepara un plan visual realizable, con acciones que expresen el guion y variedad semántica entre segmentos. Usa referencias y personajes aprobados cuando el perfil los exija. Estima el encaje de voz antes de solicitar medios; la duración real se medirá después. No acelerar habla para rellenar un plan: solo aplicar la velocidad expresamente autorizada en `channel.voice`, preservando el tono y ajustando subtítulos. Sin autorización, conservar velocidad original.

Guarda artefactos versionados en la salida de la cápsula: guion, mapa de fuentes, plan visual y brief de metadatos. No llames a proveedores de medios ni publiques. Los metadatos finales pueden derivarse posteriormente del guion aprobado mediante el rol configurado.

Incluye siempre `production-brief.json` como artefacto: `kind=production_brief_v1`,
`channel_id`, `title`, `transcript` literal completo, `sources` con referencias
concretas y `scenes` cronológicas. Cada escena contiene `id` estable en minúsculas,
`prompt` visual y `narrative_purpose` ligado al guion. Para ¿Sabías que?, prepara
suficientes propuestas distintas para cambios cada cinco segundos de voz; el
motor seleccionará las necesarias tras medir el audio. No generar las imágenes.
No convertir referencias literales ni indicaciones visuales en palabras narradas.
La entrega de este formato no constituye QA independiente ni licencia de publicación.

Devuelve **solo el recibo estructurado definido por la cápsula**: trabajo, etapa, decisión, artefactos con rutas/hashes/bytes, comprobaciones realmente efectuadas, evidencia y bloqueos. No declares QA independiente ni derechos resueltos sin evidencia. No incluyas secretos, sesiones, correos privados o el contenido completo del repositorio.
