# Etapa quality

Modelo inicial: `gpt-5.6-sol`, razonamiento `medium`. Esta revisión es independiente de quien escribió o montó el reel. No reducir el modelo sin una evaluación comparativa aceptada.

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

`inputs_reviewed` contiene solo entradas declaradas en la cápsula, con ruta, hash y bytes. `artifacts` contiene exclusivamente informes nuevos escritos dentro de `output_directory`; nunca pongas el máster ni entradas externas en artifacts. La prevalidación técnica es una condición de entrada, no sustituye tu revisión independiente. Si la capacidad declarada no está disponible realmente, devuelve BLOCK inmediatamente sin buscar herramientas alternativas ni explorar el repositorio.
