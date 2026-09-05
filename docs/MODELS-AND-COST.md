# Modelos y ahorro de consumo

El reparto inicial está en `config/models.json`: Terra/medium para guion y dirección visual, Sol/medium para revisión independiente, Terra/low para publicación mediante navegador y Luna/low para metadatos derivados. Coordinación, índices, archivos, montaje y QA técnica son tareas locales sin LLM. Es una propuesta inicial que requiere comparar resultados; no afirma un ahorro medido.

El catálogo oficial consultado el 5 de septiembre de 2026 distingue Terra por equilibrio de capacidad/coste y Luna por cargas sensibles al coste. La disponibilidad indicada por la app no prueba acceso a una API ni disponibilidad de cuota en un instante concreto. [Catálogo oficial](https://developers.openai.com/api/docs/models).

El núcleo prepara y ejecuta etapas editoriales mediante `codex exec` con modelo, esfuerzo y respuesta estructurada explícitos. Usa la autenticación existente de Codex; no copia credenciales ni convierte una suscripción en autorización para APIs adicionales. `run-stage` prepara por defecto y requiere `--execute` para consumir cuota. [Modo no interactivo oficial](https://learn.chatgpt.com/docs/non-interactive-mode).

Medidas implementadas:

- Índice local SQLite de fuentes con referencia a archivo, versículo o página. Se recuperan hasta ocho fragmentos, evitando releer el libro en cada etapa.
- Cápsulas de contexto acotadas y prompts cortos por responsabilidad; la cápsula inicial de creative sin medios ocupa unos 4.200 caracteres. Los límites de caracteres y las metas de salida no son un contador exacto de tokens.
- Caché por hashes de entradas, perfil, prompt y modelo. La caché verifica los archivos antes de reutilizarlos.
- Registro de llamadas por etapa y modelo; recoge tokens reales de los eventos cuando existen y deja `null` cuando no están disponibles. No atribuye coste cero a datos ausentes.
- Una ejecución fallida o incierta no se repite automáticamente. El máximo inicial es dos ejecuciones distintas por trabajo y rol; la recuperación necesita revisar la causa.
- SQLite coordina recursos y evita nuevos trabajos duplicados por canal/fecha.

Si se autoriza una API de pago en el futuro, un prefijo de prompt estable permite aprovechar el cacheo del proveedor, sujeto a las condiciones del modelo y sin garantizar aciertos. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

Para lotes editoriales que toleren espera, Batch ofrece un descuento oficial del 50% respecto al procesamiento síncrono y una ventana de hasta 24 horas. Es una opción futura; **esta versión no envía lotes de pago**. No corresponde aplicar ese descuento al consumo de una suscripción Codex. [Batch API](https://developers.openai.com/api/docs/guides/batch).

Antes de abaratar quality se comparará un lote idéntico contra las referencias aceptadas: errores críticos cero, fidelidad al texto, voz natural, anatomía, continuidad, subtítulos, variedad y verificación de publicación. Medir coste por reel aceptado, incluyendo intentos descartados; el precio por token por sí solo no decide el modelo.

La automatización completa todavía necesita adaptadores de medios y publicación cualificados. La API de YouTube y Direct Post de TikTok pueden imponer visibilidad privada a clientes no verificados/auditados; no basta con integrar un endpoint para prometer publicación pública. [YouTube videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert), [TikTok Direct Post](https://developers.tiktok.com/doc/content-posting-api-get-started).
