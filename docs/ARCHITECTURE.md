# Arquitectura del ecosistema

El ecosistema separa un núcleo de producción compartido de los datos y las decisiones editoriales de cada canal. Una mejora en coordinación, montaje o validación puede aplicarse a varios canales sin cambiar sus fuentes, voz, identidad o estilo. La primera versión está en **migración pendiente de canary**: tener código, perfiles y un plan diario no demuestra todavía una producción y publicación autónomas completas.

## Núcleo y perfiles

El núcleo usa Python y su biblioteca estándar, con SQLite para persistir trabajos, etapas y sus transiciones. La lógica de calendario, coordinación y comprobaciones deterministas no necesita un agente. Las llamadas a modelos se reservan para decisiones editoriales, dirección visual, revisión independiente y la interacción remota que aún no tenga adaptador oficial operativo.

Un perfil de canal contiene identidad editorial, destinos públicos, idiomas, corpus y edición, política de fuentes, voz, estilo, subtítulos, música, derechos, cadencia y estado de activación. Las credenciales pertenecen al entorno local o al almacén del proveedor; nunca al perfil versionado, a Git ni a una cápsula.

Las restricciones religiosas pertenecen al perfil de Religion. La revisión de datos divulgativos pertenece al perfil de ¿Sabías que? Ambos heredan integridad de activos, evidencia de calidad, idempotencia y verificación de publicación. Una regla artística de Religion no se convierte automáticamente en regla global.

## Flujo de un reel

1. Resolver el trabajo del día y comprobar perfil, fuentes, derechos, destinos y recursos disponibles.
2. Seleccionar un tema elegible y preparar guion, referencias y metadatos de trabajo.
3. Congelar el guion y sus fuentes; comprobar que cabe en la duración prevista con voz natural.
4. Adquirir o generar medios según el perfil visual; conservar originales y procedencia.
5. Revisar las fuentes visuales y construir el máster visual.
6. Generar la narración autorizada, música y subtítulos; montar el máster audiovisual.
7. Ejecutar controles locales y una revisión independiente del resultado completo.
8. Publicar en destinos configurados y verificar cada URL pública.
9. Cerrar el trabajo con recibos, copias verificadas y medidas de coste y retrabajo.

El detalle de las etapas y sus nombres lo define el runtime. Un bloqueo de un canal o proveedor permite continuar los trabajos independientes elegibles. Ninguna etapa posterior puede tratar un dato ausente como una aceptación.

## Modelos por responsabilidad

| Responsabilidad | Ejecutor inicial | Motivo y condición |
| --- | --- | --- |
| Calendario, coordinación, estado, caché | Python local | Operaciones deterministas, sin LLM. |
| Guion y selección editorial | `gpt-5.6-terra`, `medium` | Comprensión de fuentes y adaptación con referencias. |
| Dirección visual e interacción de generación | `gpt-5.6-terra`, `medium` | Decisiones sobre escenas y proveedor; render separado. |
| Revisión editorial y visual independiente | `gpt-5.6-sol`, `medium` | Puerta de calidad; no reducir a Terra sin evaluación comparativa. |
| Publicación asistida por navegador | `gpt-5.6-terra`, `low` | Solo cuando el adaptador oficial no esté operativo y el navegador esté autorizado. |
| Metadatos derivados del guion aprobado | `gpt-5.6-luna`, `low` | Transformación acotada, sin añadir afirmaciones. |
| Render, inspección técnica, hashes y archivos | Herramientas locales | CPU/GPU según operación; sin LLM. |

Son asignaciones iniciales, no resultados de un benchmark. La disponibilidad real de los modelos y el gasto se comprueban en el entorno de ejecución. Un fallo de calidad permite escalar la tarea concreta; no obliga a repetir el resto del reel.

## Cápsulas y recibos

Cada agente recibe una cápsula cerrada: canal, trabajo, etapa, versión de perfil, autoridad de publicación aplicable, referencias exactas a entradas, hashes, comprobaciones exigidas y ubicación de salida. Lee su prompt breve y esas entradas. No relee el repositorio Religion, históricos o contratos monolíticos para cada reel.

La salida es un recibo estructurado con identidad de trabajo y etapa, decisión, referencias a artefactos y evidencia, y motivo de bloqueo o rechazo cuando corresponda. El coordinador valida el recibo y acepta la transición. El agente no modifica directamente el estado central.

La conformidad de un JSON no demuestra calidad del contenido. Una aceptación necesita los archivos y observaciones que justifican sus comprobaciones. El autor del guion o del montaje no sustituye al revisor independiente.

## Estado y efectos externos

La unidad diaria es un trabajo por canal y fecha local en `Europe/Madrid`. La política inicial es un reel al día, publicado en YouTube y TikTok cuando ambos destinos estén configurados y activos. Ejecutar de nuevo el planificador debe recuperar el mismo trabajo, no crear otro.

Las transiciones deben ejecutarse en transacciones y comprobar la revisión esperada. El historial conserva la relación entre intento, entrada, salida y decisión. La coordinación protege los recursos compartidos: una operación GPU a la vez y la exclusión requerida por cada cuenta remota. Un claim caducado no prueba que un proceso haya terminado; su recuperación requiere comprobar actividad y reconciliar el intento.

Antes de una llamada que genere gasto o una publicación se registra un intent con clave idempotente. Si el resultado es incierto, se consulta el proveedor o la plataforma para resolverlo antes de repetir. Un intent desconocido no debe convertirse automáticamente en un nuevo clic de subida.

La publicación se completa por plataforma. Para Religion se conserva YouTube público antes de TikTok. El cierre dual requiere identidad correcta, máster correspondiente y URL pública comprobada en ambas plataformas. Un formulario enviado, una tarjeta de Studio o un estado de revisión no bastan.

## Uso del PC y la GPU

FFmpeg/ffprobe cubren inspección y montaje; la transcripción o alineación local, cuando esté instalada y validada, aporta tiempos de subtítulos. La GPU se reserva para generación o interpolación autorizada, render compatible y otros trabajos que aporten una mejora medida. No se instalan pesos ni se cambia de proveedor por el mero hecho de tener GPU libre.

El perfil actual importado de Religion autoriza tres fuentes distintas y RIFE 2× por segmento: 125 frames nativos pasan a 250 frames, con cero interpolación a través de cortes y cero reutilización de fuente. Esta autorización y sus comprobaciones son específicas del perfil. La línea experimental pro v5 conserva su aislamiento y su canary propio.

Los binarios, pesos, MP4 y cachés no forman parte del código Git. El repositorio guarda configuración pública, adaptadores, pruebas y referencias de instalación; los activos viven en almacenamiento local con manifiestos y copias verificadas.

## Caché y costes

La clave de caché incluye contenido de entrada, perfil, versión del adaptador, parámetros y, cuando corresponda, proveedor/modelo/voz. Un cambio relevante invalida la salida. Un archivo en caché se verifica antes de reutilizarlo; su presencia no demuestra que esté completo.

Se cachean el análisis de corpus, los artefactos técnicos y las respuestas repetibles. Se reutilizan las evidencias de licencias hasta su vencimiento o cambio aplicable. La identidad de cuenta, el estado de un intent y el resultado público de una publicación requieren observación actual.

Por etapa se registran tokens cuando el proveedor los devuelve, tiempo activo, espera externa, GPU, llamadas, caché y retrabajo. Un dato no disponible se marca como tal; no se transforma en cero. La mejora se evalúa por coste por reel aceptado y calidad, sin porcentajes de ahorro supuestos.

## Límite de esta entrega

Los comandos del núcleo organizan trabajo y preparan información para ejecutar las etapas. Los adaptadores, sesiones y evidencias de una producción real deben conectarse y superar un canary antes de activar la publicación diaria. El planificador local necesita el PC encendido y el entorno operativo; un horario guardado no sustituye esta validación.
