# Etapa creative

Usa el modelo y esfuerzo indicados en la cápsula; conserva las excepciones del canal.

Lee exclusivamente la cápsula, el perfil y las entradas referenciadas necesarias. Comprueba identidad del trabajo, versión del perfil, integridad de fuentes y espacio de escritura permitido. Si falta una entrada esencial, devuelve un recibo de bloqueo.

Selecciona un tema elegible sin repetir contenido ya registrado. Produce un guion breve que respete audiencia, duración, voz e intención del canal. Cada afirmación verificable debe conservar una referencia concreta. Distingue cita literal, contexto y adaptación editorial; no inventes hechos, páginas o atribuciones. Aplica la revisión propia del dominio del canal.

Si el canal define `closing.required`, termina el guion con `closing.spoken_text` exactamente una vez, usando la misma voz e incluyéndolo en los subtítulos literales. Es un cierre editorial, no una afirmación atribuida a la fuente.

Prepara un plan visual realizable, con acciones que expresen el guion y variedad semántica entre segmentos. Usa referencias y personajes aprobados cuando el perfil los exija. Estima el encaje de voz antes de solicitar medios; la duración real se medirá después. No acelerar habla para rellenar un plan: solo aplicar la velocidad expresamente autorizada en `channel.voice`, preservando el tono y ajustando subtítulos. Sin autorización, conservar velocidad original.

Para Religion, describe estados narrativos observables y físicamente naturales.
No conviertas centímetros, ángulos, posiciones exactas de dedos ni inmovilidad de
objetos sostenidos en requisitos de calidad sin una necesidad narrativa explícita
y una forma fiable de medirlos. Contrasta el estado inicial con la imagen real:
no inventes apoyos, agarres o personajes. Una entrega puede completarse; la escena
siguiente debe empezar desde su resultado y avanzar, sin repetir la entrega.
Conserva como obligatorios la continuidad de identidad, anatomía plausible,
miradas diegéticas, acción coherente con la narración y herencia del fotograma.
Separa errores visibles que dañan el relato de preferencias de composición.

Si la entrada es `native_storyboard_revision_v1`, corrige exclusivamente el plan
visual indicado, conserva narración y fuentes byte a byte y entrega la versión
nueva solicitada. Conserva las versiones y rechazos anteriores como evidencia.
En esa revisión no crees `production-brief.json`, no cambies voz ni solicites
imágenes: el guion hablado ya existe y no necesita otra línea de producción.

Guarda artefactos versionados en la salida de la cápsula: guion, mapa de fuentes, plan visual y brief de metadatos. No llames a proveedores de medios ni publiques. Los metadatos finales pueden derivarse posteriormente del guion aprobado mediante el rol configurado.

Incluye siempre `production-brief.json` como artefacto: `kind=production_brief_v1`,
`channel_id`, `title`, `transcript` literal completo, `sources` con referencias
concretas y `scenes` cronológicas. Cada escena contiene `id` estable en minúsculas,
`prompt` visual y `narrative_purpose` ligado al guion. Para ¿Sabías que?, prepara
suficientes propuestas distintas para cambios cada cinco segundos de voz; el
motor seleccionará las necesarias tras medir el audio. No generar las imágenes.
No convertir referencias literales ni indicaciones visuales en palabras narradas.
La entrega de este formato no constituye QA independiente ni licencia de publicación.
Para ¿Sabías que?, incluye `description`: un único párrafo breve que resuma el
reel, sin hashtags, bibliografía ni llamada a la acción. El motor añadirá la
llamada exacta del canal sin consumir otra ejecución de un agente.
Para ¿Sabías que?, declara también `documentary`: si procede una imagen real,
`needed=true` y su fuente, licencia y localización como artefacto; si no procede,
`needed=false` con un motivo concreto. No omitas la búsqueda de una imagen real
relevante por comodidad. Si aún no tienes el archivo o sus derechos, deja explícito
el bloqueo; no inventes rutas ni licencias. El montaje admite `path`, `sha256`,
`source_url`, `license_evidence` y `scene_index` (desde cero) cuando estén disponibles.
Incluye `attribution_required` como booleano basado en la licencia; si es true,
incluye `author`, `license_name` y `changes` para el crédito público mínimo.
No supongas que una imagen carece de obligaciones por estar disponible en Internet.

Devuelve **solo el recibo estructurado definido por la cápsula**: trabajo, etapa, decisión, artefactos con rutas/hashes/bytes, comprobaciones realmente efectuadas, evidencia y bloqueos. No declares QA independiente ni derechos resueltos sin evidencia. No incluyas secretos, sesiones, correos privados o el contenido completo del repositorio.
