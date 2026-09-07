# Upro: motor local y etapas compartidas

Upro 0.2 es un programa local para Windows con interfaz web servida exclusivamente
en `127.0.0.1`. Abrir el ejecutable inicia el coordinador sin necesitar esta
conversación abierta. La generación y publicación autónomas completas siguen
pendientes de adaptar y cualificar en los dos canales. Un interruptor activado
expresa la preferencia del usuario; no convierte un bloqueo en una aprobación.

## Componentes

- `ecosystem/upro.py`: servidor, controles persistentes,
  exclusión de segunda instancia, planificación y dos trabajadores como máximo.
- `ecosystem/upro_queue.py`: etapas con entradas ligadas a hash, dependencias,
  reclamación transaccional, recibos y recuperación conservadora.
- `ecosystem/static/`: panel sin dependencias ni llamadas a modelos.
- `channels/`: personalidad, voz, fuentes, cadencia y publicación de cada canal.
- `config/models.json`: modelos y límites del ejecutor por función y excepciones
  de Religion pro v5; no se duplica el motor por canal.

La cola diaria reanuda primero el trabajo más antiguo. No acumula un reel nuevo
cada vez que se abre el programa. Los controles se guardan en
`.runtime/upro/controls.json`; los trabajos, pasos, medios y evidencias permanecen
fuera de Git. Cerrar la pestaña deja el motor abierto; el botón de cierre espera
que terminen las etapas en curso.

## Adaptadores disponibles y límites

| Etapa | Ejecución | Alcance |
|---|---|---|
| Coordinación y panel | Python local | Sin tokens |
| Guion, metadatos, revisión | Ejecutor Codex | Cápsula, modelo por rol y recibo |
| Movimiento ambiental | CUDA y NVENC existentes | Reserva global GPU y protección de objetos rígidos |
| Montaje cómic | FFmpeg y NVENC existentes | Máster local y evidencia técnica |
| Inspección de máster | FFprobe y FFmpeg | Decodificación completa; no sustituye revisión artística |
| Imagen individual | ImageGen mediante Codex con ChatGPT | Conexión probada; mantiene rechazo artístico y no repite variantes |
| Voz y publicación | Pendiente | No se presentan como producción automática validada |

Las etapas GPU adquieren y renuevan su reserva global en los adaptadores
existentes. Dos canales pueden avanzar en tareas distintas, pero no iniciar dos
renderizados GPU simultáneos. El sistema no descarga pesos, contrata APIs ni
cambia la voz para abaratar. El PC debe estar encendido y despierto para avanzar.

Las revisiones editorial y audiovisual independientes, identidad, licencias,
subtítulos literales e intención de publicación continúan siendo requisitos.
Una decodificación correcta permite mostrar un vídeo local para revisión y no
autoriza publicarlo. La línea Religion de cinco minutos permanece pausada.

## Registrar una etapa desde el código de producción

El panel nunca recibe rutas ni comandos arbitrarios. El productor registra un
plan local mediante `python -m ecosystem.upro --register plan.json`:

```json
{
  "schema_version": 1,
  "job_id": "identificador existente",
  "channel_id": "sabias-que",
  "adapter": "media_check",
  "mode": "validation",
  "inputs": [{"path": "E:/canal/master.mp4", "sha256": "hash real SHA-256"}],
  "depends_on": []
}
```

El modo `validation` solo permite inspeccionar un medio, sin publicación ni
generación; puede ejecutarse antes de cualificar la migración. El modo
`production` exige que `readiness` esté libre de bloqueos. Los adaptadores son
una lista de funciones conocidas, no comandos del manifiesto. Una etapa por
canal avanza a la vez; las dependencias deben pertenecer al mismo trabajo.

El modo `canary` permite la primera prueba sin exigir que esa misma prueba ya
haya pasado. Requiere autorización local ligada al canal, trabajo y adaptadores,
comprobada al registrar y justo antes de ejecutar. Conserva los requisitos de
la etapa y no permite publicar. El ámbito activo de plataformas evita que una
cuenta TikTok pendiente bloquee un trabajo limitado a YouTube; los canales que
generan imágenes con ImageGen no requieren una sesión Vibes.

Un montaje aceptado encadena automáticamente una inspección de medios. La
transición se recupera al abrir el programa si hubo un cierre entre etapas,
verifica el hash del máster y no vuelve a montar ni duplicar la inspección.
La actividad reciente se conserva entre reinicios. El panel distingue la etapa
actual de los requisitos pendientes para activar la producción diaria autónoma;
un vídeo técnicamente válido se muestra como pendiente de revisión.

## Comprobación del 7 de septiembre de 2026

Upro ejecutó cuatro animaciones CUDA/NVENC y el montaje de una prueba de
¿Sabías que?, con imágenes y voz ya existentes. Tras reiniciar el ejecutable,
encadenó por sí solo la decodificación y la vista previa del máster. Esto valida
ese tramo local; no valida la generación de nuevos recursos ni la publicación.

La comprobación inicial de conexiones se hizo dentro del entorno restringido y
no representaba la configuración real del usuario. Una segunda comprobación en
el entorno real confirmó autenticación ChatGPT y los servidores `cua_repl` y
`node_repl` habilitados. Esto acredita configuración, no disponibilidad funcional
del navegador tras cerrar la aplicación. Quedan por integrar y probar:
generación visual por proveedor, narración con la voz aprobada, revisión completa
de imagen y sonido, y publicación con identidad y recibo público. No activar el
indicador global de producción para ocultar esta dependencia. No usar cookies,
claves ni sesiones extraídas de la aplicación como atajo de integración.

El usuario fija cero euros adicionales: usar su suscripción actual de ChatGPT
y los recursos locales. `monthly_budget_eur=0` se refiere a nuevos servicios,
no al precio de esa suscripción. `paid_api_enabled=false` permanece vigente;
no contratar servicios ni comprar créditos. Los agentes deben usar el acceso
ChatGPT admitido por Codex. Si se alcanza el límite incluido, detener los agentes
hasta que vuelva a estar disponible; nunca cambiar a una API de pago.

Tras un cierre inesperado las etapas en curso pasan a inciertas. No se vuelven a
ejecutar. Hay que inspeccionar evidencias y procesos antes de usar
`--reconcile ID --evidence resultado.json` con `checked: true` y `reason`.
Esto archiva el intento; cualquier corrección necesita un plan nuevo. Tampoco se
repite una publicación cuyo resultado aún no se haya reconciliado.

## Prueba funcional del ejecutor y generación visual

La prueba de un proceso CLI real confirmó conexión al navegador y disponibilidad
de ImageGen usando ChatGPT. No acreditó percepción completa de audio ni vídeo;
no crear un preflight QA con esas capacidades a true. Tampoco se ha comprobado
el navegador con la aplicación Codex cerrada.

La primera ejecución visual descubrió un error real de esquema estructurado:
`inputs_reviewed` debía figurar en `required`. Se corrigió y se añadió una prueba
de compatibilidad estricta para todos los objetos del esquema. El fallo se
reconcilió antes de un segundo intento: no había ocurrido generación remota.

El segundo intento generó un PNG real y lo rechazó por composición insuficiente
para los subtítulos. Se conserva el resultado sin aprobarlo ni regenerarlo. La
telemetría de ese intento fue 714817 tokens de entrada (640256 en caché) y 6667
de salida; estas cifras no incluyen el trabajo de desarrollo ni son una medida
de ahorro. La coordinación y sellado de archivos se trasladaron después al
código local para evitar esa actividad repetitiva del agente. Este cambio está
probado localmente; su ahorro real aún no se ha medido con una nueva generación.

Cada petición `image_generation_request_v1` lleva `channel_id`, `scene_id`,
`image_count=1`, `prompt` y `source_basis`. Los intentos se limitan por escena,
para que la tercera escena de un reel no se interprete como el tercer reintento.
Un resultado incierto sigue bloqueando el trabajo hasta reconciliarlo.
El agente devuelve una sola ruta generada; el ejecutor restringe su origen,
copia el PNG, calcula hashes y conserva procedencia sin atribuirse QA artística.

Todos los agentes usan `forced_login_method="chatgpt"`; las variables heredadas
`OPENAI_API_KEY` y `CODEX_API_KEY` se excluyen de su proceso. Las credenciales
no se copian ni se escriben en Git. La voz original sigue siendo Google Gemini
TTS; su existencia no significa que esté incluida en ChatGPT Pro.

## Publicación diferida en YouTube

Todos los canales actuales y futuros heredan `config/ecosystem.json` →
`youtube_release`: tras QA, subir como privado sin aprobación del usuario y
programar en YouTube para dos horas después de completar la subida. Sustituye
el antiguo horario fijo propuesto. La cápsula de publicación incluye esta regla
y su caché cambia al modificarla. `ecosystem.release.youtube_schedule` calcula
la fecha UTC y, para Studio, redondea al minuto siguiente si es necesario.

Registrar por separado subida, programación y verificación pública: programado
no significa publicado. No recalcular el plazo en cada reinicio ni enviar una
fecha vencida. Las líneas pausadas siguen pausadas. La regla está implementada
en la configuración, cálculo y cápsulas; la ejecución remota sigue pendiente
de la conexión completa del publicador indicada arriba.

`prepare-youtube-schedule --upload-intent ID` persiste el intent desde una subida
privada verificada y conserva la fecha original tras reiniciar. Rechaza identidad
distinta, subidas incompletas, resultados inciertos y fechas vencidas. El almacén
valida la respuesta de programación contra vídeo, cuenta, hash y fecha exactos;
una programación verificada no completa el trabajo ni acredita visibilidad pública.
Estas garantías están comprobadas con pruebas de reinicio y fallos simulados;
todavía falta verificar la ejecución remota completa en YouTube.

## Consumo y calidad

La coordinación, actualización cada cinco segundos, hashes, montaje y validación
técnica usan código local. Los agentes reciben referencias y contexto específico
de su etapa; caché y presupuesto de intentos impiden repetir el mismo trabajo.
Los cambios de política y esquema invalidan la caché. Una revisión sin las
capacidades y evidencias requeridas se bloquea antes de iniciar el agente.

Los límites de salida son objetivos de prompt, no cuotas duras del proveedor.
Hay límites de tiempo por función. Se guardan tokens de los eventos de turno
completado incluso cuando una ejecución posterior termina con error. Entrada
incluye tokens en caché: no se suma caché otra vez al total. Una ausencia de
telemetría significa desconocido, nunca consumo cero. El panel excluye el trabajo
de desarrollo de esta conversación.

Los eventos `turn.completed` y las respuestas con `--output-schema` siguen el
contrato del [modo no interactivo de Codex](https://learn.chatgpt.com/docs/non-interactive-mode).

No se promete un porcentaje de ahorro: queda pendiente medir varios reels
completos con su revisión independiente y comparar consumo, fallos y calidad.
Religion pro v5 conserva Sol medium en todos sus roles de agente.

## Acceso local

El servidor valida Host y Origin, exige un token para los cambios y no habilita
CORS. Los vídeos se sirven únicamente desde inspecciones registradas, con hash
verificado y soporte de reproducción parcial. Otro programa que ya controle esta
misma cuenta de Windows queda dentro del ámbito de confianza local; este servidor
no es un servicio para exponer a Internet.
