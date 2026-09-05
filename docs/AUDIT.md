# Auditoría de extracción de Religion

Fecha de inspección: 2026-09-05. Fuente: lectura local de `C:/Users/asier/Documents/Religion`. No se ejecutó producción, publicación ni modificación de ese proyecto durante la auditoría. La configuración y el estado encontrados son evidencia local; las sesiones y URLs públicas no se verificaron en vivo en esta inspección.

## Hallazgos vigentes

La autoridad de Religion está en `AGENTS.md` y `content/production/reel-team/contracts/reels-architecture-v03.json`. La línea v03 tiene seis roles: coordinator, creative, vibes, media-builder, quality y release. Observación y limpieza son rutinas deterministas; audio y localización son modos de media-builder. Los contratos de diez estaciones anteriores son historia, no una base para nuevos despachos.

La política visual cambió respecto a notas históricas. El contrato actual `reels-visual-quality-profile-v01.json` exige tres fuentes distintas y RIFE GPU 2× por segmento, 125→250 frames, sin reuso ni interpolación de cortes. El resultado visual de referencia tiene 750 frames y 31,25 segundos a 24 fps. Conservar como regla universal una prohibición histórica de RIFE sería incorrecto.

La línea pro v5 figura como `candidate-for-independent-testing`, solo por invocación expresa. Encadena cada fragmento desde el último frame real del anterior y añade revisión de continuidad de acción, emoción y mirada. Su contrato requiere un canary visual no publicado y comparación independiente contra ENS-003 a ENS-007. No se considera una sustitución validada de v03.

## Datos trasladables a un perfil

| Dato | Religion / LUMEN |
| --- | --- |
| Nombre público | Las Palabras de Cristo |
| YouTube | Canal `UCqi7xNodxQSP5-EDCMwL4PA`; handle `@laspalabrasdecristo` |
| TikTok | `@laspalabrasdecristo` |
| Contenido y narración | Contenido `es-ES`; voz Algenib `es-CO` |
| Fuente | Biblia RV1909, edición congelada en corpus local |
| Estilo reciente | `vibes-photoreal`: cine fotorrealista vertical 720×1280, 24 fps |
| Subtítulos | `early-reels-ivory-gold-v01`: Segoe UI Semibold 39, marfil `#FFF7E8`, halo `#D5A84E`, márgenes 54/54/336 |
| Estado observado | ENS-025 `ES_PUBLIC_VERIFIED`, sin etapa pendiente ni intents abiertos en el estado v03 |

Fuentes locales concretas:

- `content/production/reel-team/runs/ens-023-production-tracking-v01.json`: identidad pública de los destinos.
- `content/audio/manifests/lumen_narrator_google_colombia_v1.json`: voz y proveedor registrados. Describe `gemini-3.1-flash-tts-preview`; su disponibilidad actual requiere preflight.
- `content/series/las-ensenanzas/reels/ens-025/creative-package-v01.json`: guion, fuente, personajes y perfil visual.
- `content/series/las-ensenanzas/reels/ens-025/references/prompt-packs/ens_025_vibes_prompt_pack_v01.md`: dirección artística aplicada.
- `content/corpora/christianity/rvr1909/ebible-usfm-v2015-08-10/source`: corpus congelado.
- `content/production/reel-team/state/line-state-v03.json`: estado observado.

La narración se clasifica como `editorial_adaptation`; la cita literal y el contexto se conservan en su source lock. Las fichas de personajes son canon creativo, no prueba de apariencia histórica. Estas distinciones permanecen en la política de Religion.

¿Sabías que? no apareció en la búsqueda específica de Markdown, JSON y YAML en `content`, `.agents` y `docs` de Religion. Su alta se trata como un perfil propio del ecosistema: voz Kore bloqueada y logo neón sobre negro v04 aprobado según la configuración recuperada para ese canal; estilo visual inicialmente provisional. Su ficha está en `channels/sabias-que.json` y registra como fuente *Enciclopedia de las curiosidades: El libro de los hechos insólitos*, de Gregorio Doval. Después de la auditoría inicial, el usuario comunicó YouTube `@sabias-quecuriosidad` y autorizó reutilizar un correo Vibes almacenado solo localmente, al estar bloqueada por ahora la línea religiosa de cinco minutos. Ambos quedan pendientes de verificación de sesión; TikTok continúa sin configurar. El usuario eligió C · Cómic plano entre tres prototipos el 5 de septiembre de 2026. La dirección visual está aprobada; la animación de producción aún requiere validación. No se infieren cuentas del nombre ni de la identidad de Religion.

## Código útil y límites de reutilización

| Archivo en Religion | Aprendizaje o código candidato | Límite |
| --- | --- | --- |
| `tools/reel-line/lumen_reels_v03.py` | Secuencia de etapas y validación de registros | Es selector/validador, no ejecutor autónomo completo. Rutas e identidad están fijadas. |
| `tools/reel-line/lumen_reel_line.py` | Escritura atómica, recibos inmutables, journal e intents | Monolito de aproximadamente 452 KB con historia y autoridades específicas; extraer unidades pequeñas. |
| `tools/reel-line/schemas/reel-execution-record-v03.schema.json` | Evidencia compacta por etapa | Parametrizar canal, idioma y autoridad. |
| `tools/build_ensenanzas_captions.py` | Silencios, límites de lectura y subtítulos sin cambiar narración | El fallback ponderado por texto necesita revisión real de sincronía; estilo parametrizado. |
| `tools/build_native_allframes_qa_evidence.py` | Decodificación y contactos exhaustivos | Contiene máscaras y recortes ligados a escenas bíblicas; no generalizarlos sin adaptación. |
| `tools/reel-music/lumen_reel_music.py` | Asignación transaccional de tramos musicales | Separar biblioteca, licencia, cursores y política de repetición. |
| `tools/reel-line/Invoke-LumenReelsProV5Rife.ps1` | Ejecución RIFE local y evidencia | Extraer ejecutor, conservando aislamiento del contrato experimental. |
| `tools/reel-line/validate_reel_release_rights.py` | Gate de derechos ligado a activos | Cada canal necesita sus fuentes y licencias aplicables. |

No se importa íntegro `tools/automation/longform-agent-line/ledger_v2.py`, de aproximadamente 1,15 MB: su complejidad responde a Longform e incidentes históricos. Tampoco se copian colas, journals, claims, credenciales, órdenes históricas, pesos, binarios o archivos multimedia al repositorio nuevo.

Un defecto observado en `lumen_reels_v03.py` es que la ausencia de `jsonschema` devuelve una lista vacía de errores. El nuevo núcleo no debe interpretar una validación no ejecutada como aprobada. Del mismo modo, un contrato que enumera controles no demuestra que el runtime los haya ejecutado.

## Optimización apoyada en evidencia

`content/production/reel-team/runs/ens-022-production-retrospective-v01.json` registra 59,23 minutos de producción activa y atribuye el 38,7 % de ese trabajo al ajuste tardío de la voz. El 89,4 % del tiempo total registrado fue espera externa. Son medidas de ese reel, no previsiones para el ecosistema.

Las medidas prioritarias son comprobar sesiones al comienzo, presupuestar palabras antes de generar medios, medir la voz pronto, congelar metadatos durante el render y mantener trabajo local independiente durante esperas. Para ese estilo y voz, la retrospectiva propone 55–60 palabras; otros canales necesitan calibración propia.

La arquitectura v03 ya reduce duplicación documental mediante un registro por etapa y separa validación de release, cambios e incidentes. Esta división se conserva: no ejecutar suites amplias durante cada publicación, pero sí pruebas focales cuando cambia el runtime o un contrato.

El ecosistema desplaza coordinación y operaciones técnicas a código local; usa cápsulas breves, caché por hash y modelos por responsabilidad. La QA semántica queda independiente y empieza en Sol. No se atribuye un ahorro de tokens hasta obtener medidas comparables de reels aceptados.

## Estado de migración

La extracción conserva Religion como fuente de consulta y permite volver a su flujo anterior. Los perfiles importados empiezan pendientes de canary. No se crea una segunda autoridad de publicación activa mientras la anterior siga produciendo el mismo canal y fecha.

Para afirmar autonomía faltan adaptadores conectados, preflight real de identidades, ejecución completa con evidencia y verificación pública por destino. Los contratos, pruebas locales y trabajos diarios preparados son avances distintos de esa demostración.
