# Operación y migración

El objetivo operativo es producir un reel al día por canal activo y publicarlo en sus destinos YouTube y TikTok. La entrega inicial está en **migración pendiente de canary**. Un comando diario puede preparar trabajo sin haber generado vídeo ni publicado nada. Consultar siempre el estado del trabajo y sus evidencias antes de informar de finalización.

## Comandos del núcleo

Desde la raíz del repositorio, consultar `python -m ecosystem --help` y la ayuda del subcomando para ver los argumentos disponibles. Las funciones previstas son:

| Comando | Uso |
| --- | --- |
| `onboard` | Preparar el alta y el cuestionario de un canal. |
| `readiness` | Mostrar requisitos resueltos y pendientes de activación. |
| `daily` | Resolver la planificación diaria con idempotencia por canal/fecha. |
| `status` | Consultar trabajos y etapas persistidos. |
| `dispatch-packet` | Preparar la cápsula acotada de una etapa elegible. |
| `media-probe` | Inspeccionar un archivo audiovisual mediante herramientas locales. |

La salida de cada comando determina lo que ocurrió. `readiness` no inicia sesión por sí solo; `dispatch-packet` no demuestra ejecución del agente; un probe técnico no sustituye la revisión semántica ni la reproducción completa.

## Alta de canal

Cuando el usuario diga que tiene una nueva idea, abrir el cuestionario y reutilizar los datos que ya estén confirmados. Debe cubrir nombre, temática, audiencia, libro y edición, permiso de uso, idiomas, voz, estilo artístico, referencias, duración, música, subtítulos, destinos, horario y política de publicación. No volver a preguntar datos bloqueados salvo que el usuario solicite cambiarlos o haya una contradicción concreta.

El alta produce un perfil provisional y una lista visible de faltantes. La creación de logo y portada utiliza un brief de marca compartido con el estilo del canal. Se conservan versiones y la variante elegida; un logo aprobado no implica aprobación del estilo de vídeo o autorización de un destino nuevo.

Para Religion se conserva el perfil actual y su fuente RV1909. Para ¿Sabías que? se conservan Kore, el logo neón negro v04 y la fuente registrada de Gregorio Doval; estilo visual provisional e identidades Vibes/YouTube/TikTok pendientes. No usar la identidad de Religion como fallback.

El libro debe quedar identificado por título, autor, edición, idioma y referencia local o fuente autorizada. La posesión de una copia no resuelve por sí sola su uso comercial. Separar citas literales, contexto y adaptación; guardar la referencia concreta que sustenta cada afirmación. Resolver los derechos aplicables antes de enviar fragmentos a proveedores o publicar.

## Preflight de producción

Antes de habilitar una ejecución real, comprobar:

1. Perfil completo, versiones fijadas y política editorial aplicable.
2. Destinos públicos e identidad de las sesiones o credenciales autorizadas.
3. Fuentes y licencias ligadas al contenido y a sus activos.
4. Espacio y herramientas locales; GPU disponible cuando la etapa la requiera.
5. Estado e intents previos reconciliados, sin otra ejecución del mismo trabajo.
6. Adaptadores configurados y ruta de salida permitida para ese canal.

No introducir claves, cookies, tokens de sesión o correos privados en Git, recibos públicos, prompts o logs. El proveedor de voz recibe exclusivamente el texto autorizado y los parámetros necesarios, nunca el contexto del repositorio.

## Ejecución diaria

La fecha del trabajo se interpreta en `Europe/Madrid`. Ejecutar de nuevo el planificador para el mismo canal y fecha debe recuperar el trabajo existente. Un canal incompleto se registra como bloqueado con motivo; los demás pueden continuar. El backlog no se publica en bloque al volver a encender el PC sin una política explícita de recuperación.

El planificador local requiere que el PC esté encendido y el entorno disponible. Si el sistema se apaga o pierde sesión, se reanuda desde el último punto verificado. No lanzar nuevas generaciones o subidas por haber expirado un tiempo de espera.

El núcleo prepara cápsulas pequeñas para creative, visual, quality y release. Montaje, inspección técnica, hashes y calendario se ejecutan localmente. Conservar las fuentes inmutables y crear una versión nueva al cambiar guion, voz o medios; invalidar solo las salidas dependientes.

El revisor recibe el máster real y sus evidencias. Debe distinguir una prueba técnica aprobada de una valoración visual o editorial aprobada. Si no puede abrir un medio o comprobar una condición exigida, registra bloqueo en lugar de fabricar un PASS.

## Publicación y recuperación

Preferir un adaptador oficial configurado y probado. La asistencia por navegador solo se usa con una sesión autorizada y destino confirmado cuando ese adaptador no está listo. Las comprobaciones de identidad, máster, derechos e intent se mantienen en ambos caminos.

La autorización de publicación se lee del perfil y de su alcance. No trasladar una autorización de un canal, idioma o cuenta a otro. Para Religion se conserva la autoridad ya concedida para español dentro de sus destinos y gates; los destinos ingleses requieren configuración expresa.

Antes de subir se registra el intent. Un error de red después del envío deja resultado incierto: revisar el estado remoto y buscar el mismo contenido antes de reintentar. Para un fallo parcial entre plataformas, reanudar la plataforma pendiente conservando el resultado verificado de la otra.

Aplicar la divulgación IA y los metadatos autorizados. En Religion verificar YouTube público antes de la subida a TikTok. El cierre dual necesita URLs públicas correctas, asociadas al máster y al trabajo. Una revisión pendiente o visibilidad privada impide declarar publicación completa.

Ante una autenticación manual, OTP, 2FA o reto humano, conservar el trabajo y pedir únicamente la intervención que falta. Continuar las etapas independientes elegibles. No resolver ni eludir desafíos de seguridad ni reutilizar credenciales de otro canal.

## Migración reversible y canary

1. Importar configuración pública y registrar procedencia; mantener Religion sin cambios.
2. Resolver faltantes de cada perfil y comprobar adaptadores sin publicar.
3. Ejecutar el plan diario en modo preparatorio y confirmar que no duplica trabajos.
4. Completar un reel de prueba por perfil con guion, fuentes, audio, montaje y QA real.
5. Comparar calidad con referencias aceptadas y medir llamadas, tokens disponibles y retrabajo.
6. Ejecutar publicación de prueba dentro de la autoridad del canal y comprobar cada destino.
7. Activar la cadencia solo después de aceptar el canary y retirar la autoridad antigua para ese mismo trabajo.

No ejecutar simultáneamente el publicador anterior y el central para el mismo canal. La vuelta atrás desactiva la nueva ejecución, conserva estado e intents para reconciliación y retoma la autoridad anterior desde un punto comprobado. No borra evidencias ni vuelve a subir publicaciones ya existentes.

## Archivos y mantenimiento

Versionar código, configuración pública, prompts y pruebas. Mantener los medios, pesos, cachés, bases de datos operativas y secretos fuera de Git. Cada máster entregado debe tener manifiesto, hash, comprobación de decodificación y copia útil verificada antes de limpiar temporales.

Registrar después de cada reel aceptado tiempo activo, espera externa, llamadas y tokens disponibles, GPU, aciertos de caché y causa de retrabajo. No atribuir tokens cero a datos ausentes. Los cambios de modelo se comparan con la misma exigencia de calidad; la QA independiente permanece en Sol hasta justificar otra asignación con evaluación.

Usar comprobaciones de release durante producción normal. Al cambiar contratos, runtime o herramientas, ejecutar pruebas focales y casos adversos correspondientes. Un incidente requiere evidencia reproducible y una regresión causal, no repetir preventivamente toda la historia de Religion.
