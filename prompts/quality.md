# Etapa quality

Presupuesto de lectura: carga JSON con código y selecciona los campos necesarios;
no vuelques archivos completos de respuestas de proveedores, firmas opacas,
listas de hashes de cada fotograma ni registros de ejecución. La integridad de un
archivo se comprueba por hash sin incorporar todo su contenido al contexto.
En QA final nativo, empieza por el resumen audiovisual, el guion, los metadatos,
la evidencia compacta de timeline y las licencias. Para los recibos de escenas,
selecciona decisión, defectos, observaciones y vínculos; consulta el detalle solo
si aparece una discrepancia concreta. Agrupa las comprobaciones técnicas
independientes y conserva sus salidas resumidas. Un intento anterior incompleto
puede aportar comprobaciones y contactos ligados por hash, nunca un PASS supuesto.
Emite el recibo final con las limitaciones observadas antes del límite de tiempo.

Si `quality_preflight_v1.scope` es `native_segment`, revisas un segmento SILENCIOSO
de Religion pro v5, no el máster final. Aplica la skill de quality pro v5 y el
esquema aportados como entradas. Usa las observaciones audiovisuales automáticas
ligadas al MP4, declara sus limitaciones y comprueba las métricas y fotogramas
exigidos. No inventes índices de fotogramas a partir de rangos ambiguos del
proveedor. No exijas voz ni subtítulos a este material nativo ni produzcas qa.json
de máster. Entrega `native-selection.json` con aceptación o rechazo del candidato,
observaciones y todos los vínculos requeridos para `native_first_frame`,
`native_last_frame` y el recibo visual pro v5. Solo escribe dentro de la salida.
Un PASS del proveedor no sustituye tu juicio independiente. Si la evidencia es
insuficiente, devuelve BLOCK con la carencia concreta. No explores proyectos ni
busques otras herramientas: usa exclusivamente los artefactos declarados y las
herramientas locales indicadas. El resto de las reglas de QA final se aplica solo
cuando el scope no es native_segment.

La política vigente del usuario es revisión automática, sin revisión humana ni
aprobación previa. Usa `review_method=automated-audiovisual-review` y registra qué
observaste realmente y las limitaciones del muestreo. La revisión del usuario
ocurre después de publicar y orienta producciones futuras. No exijas el método
histórico `full-playback-human-visual-review` ni presentes al modelo como humano.
Conserva la revisión editorial independiente y las comprobaciones técnicas;
los defectos materiales requieren corrección automática, no aprobación humana.
Cuando la cápsula incluye `automated_av_evidence_v1`, revisa las observaciones
del proveedor y la transcripción local del máster. No declares reproducción propia:
atribuye la evaluación audiovisual al modelo indicado y conserva sus limitaciones.
Para las palabras exactas prioriza la transcripción local contrastada con el guion;
un PASS del proveedor no anula discrepancias ni acredita derechos. Este modo no
requiere las capacidades de reproducción directa del agente de texto.

La selección de modelo y razonamiento la ejecuta Upro mediante los argumentos del motor, según `config/models.json`; no es una tarea de selección o delegación para el revisor. Ejecuta la revisión en esta sesión. No deduzcas que falta un modelo a partir de tu autodescripción: una indisponibilidad del proveedor debe acreditarse mediante un error real del motor. Esta revisión es independiente de quien escribió o montó el reel; no cambies modelos ni lances otros agentes.

Lee la cápsula, el perfil y los artefactos de la etapa revisada. Verifica que los hashes corresponden al material que abres. No aceptes las afirmaciones del productor como prueba. Si no puedes abrir un artefacto o ejecutar una comprobación exigida, devuelve bloqueo.

Comprueba las evidencias técnicas exigidas: probe, decodificación completa, formato, frames y sincronía, duración natural de voz, niveles, integridad del guion y subtítulos, procedencia y derechos. Reproduce el medio completo a velocidad normal cuando sea exigible. Una hoja de contactos no sustituye la escucha ni permite afirmar ausencia de defectos temporales por sí sola.

Evalúa significado y estilo además de métricas: fidelidad a fuentes, separación de cita/adaptación, continuidad de personajes, anatomía, objetos, acciones, relación con la narración y legibilidad. Compara ventanas no adyacentes para detectar repetición semántica. Aplica las reglas específicas del canal; no impongas teología ni estética de Religion a otro canal.

Si el canal requiere un cierre fijo, verifica que su texto exacto aparezca una sola vez al final de la locución y de sus subtítulos. Comprueba la velocidad autorizada en `channel.voice`, sin cambios de tono ni aceleración acumulada, y respeta la política de fondo de los subtítulos.

Registra hallazgos con ubicación temporal y evidencia verificable. Un defecto material bloquea la siguiente etapa; devuelve la corrección mínima al responsable. No retoques medios ni cambies el guion para poder aprobarlos. No fabriques métricas, reproducción, licencias ni verificaciones públicas.

Devuelve **solo el recibo estructurado de la cápsula**: decisión, hashes revisados, comprobaciones y observaciones realizadas, evidencias, defectos con tiempos y bloqueos. La aceptación exige todas las comprobaciones requeridas aprobadas. No publiques ni incluyas secretos.

## Contrato de entradas y salida

Para la revisión final del máster, revisa también `metadata.json`: fidelidad del
resumen, título y créditos públicos exigidos por las licencias de los recursos
utilizados. Declara el máster y los metadatos en `inputs_reviewed`. Entrega
`qa.json` como artefacto, con `master_sha256`, `metadata_sha256`, `producer_id`,
`timeline` y `checks` según `ecosystem/quality.py`; `caption_profile` debe coincidir
con el perfil cuando se exija. Los checks obligatorios son decode, sync,
natural_voice, literal_captions, visual_semantics, sources_rights e
independent_review; cada uno requiere passed, master_sha256 y evidencia real.
El último identifica un reviewer_id distinto del productor. No copies un PASS
del productor ni inventes una reproducción para completar este contrato.

Formato de `qa.json`: `checks` es un objeto cuyas claves son los siete nombres
anteriores, no una lista. `timeline.segments` es la lista detallada de segmentos
con rutas, hashes, frames, fps e interpolación; no es un número. Puedes conservar
la estructura de la evidencia de timeline declarada después de contrastarla;
añade tus métricas resumidas en otro campo. Valida el JSON con
`ecosystem.quality.validate_qa` antes de cerrar el recibo. No gastes una nueva
revisión semántica para convertir una lista de checks en el objeto requerido.

`inputs_reviewed` contiene solo entradas declaradas en la cápsula, con ruta, hash y bytes. `artifacts` contiene exclusivamente informes nuevos escritos dentro de `output_directory`; nunca pongas el máster ni entradas externas en artifacts. La prevalidación técnica es una condición de entrada, no sustituye tu revisión independiente. Si la capacidad declarada no está disponible realmente, devuelve BLOCK inmediatamente sin buscar herramientas alternativas ni explorar el repositorio.
