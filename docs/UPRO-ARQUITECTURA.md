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

El adaptador `release` admite peticiones `youtube_operation_v1` para `upload`
y `schedule`, con máster, QA y metadatos declarados por hash. Antes de iniciar
el agente reserva el intent; una subida verificada prepara y encola la fase de
programación dependiente de ella. El agente solo puede ejecutar la fase indicada
en `operation.json`. Las pruebas simulan respuestas privadas, públicas erróneas
y repetición de intentos: no son evidencia de una subida real. Falta probar ambas
operaciones con un máster que haya superado la revisión independiente completa,
y conectar la verificación pública posterior a la fecha programada.

La fase `verify_public` ya se encadena desde la programación verificada, con
`not_before` persistente hasta 30 segundos después de `publishAt`. El agente solo
consulta el vídeo; no pulsa Publicar. Una URL pública verificada cierra el trabajo
si todas las plataformas activas del canal tienen sus recibos y el QA sigue
vinculado al máster. El contrato antiguo sigue exigiendo ambas plataformas por
defecto; Upro transmite explícitamente su alcance activo. Las pruebas de reloj,
reinicio y cierre YouTube-only usan evidencias simuladas; falta la comprobación
real de todo el ciclo. El panel distingue la espera programada de una cola normal.

## Consumo y calidad

En cada arranque o ciclo, `seed_ready_jobs` detecta trabajos diarios habilitados
sin etapas y prepara su cápsula de guion. Indexa las fuentes locales con caché,
reserva hasta tres extractos por fuente y guarda el paquete bajo el trabajo.
Una reapertura conserva esa selección; un cambio en la fuente reservada exige
reconciliación. Las líneas no habilitadas o sin readiness no arrancan.
Las reservas evitan repetir localizadores, no prueban variedad semántica ni
elegibilidad editorial: el agente debe rechazar índices, portadas y pasajes sin
contexto suficiente. Falta conectar automáticamente todos los artefactos del
guion con sus escenas y el montaje; este arranque no acredita un reel completo.

`production-brief.json` establece el intercambio entre guion y medios: título,
narración literal, referencias y storyboard con IDs estables. Un guion aceptado
prepara `voice_generate`; su audio técnicamente válido determina cuántas imágenes
requieren los intervalos de cinco segundos del canal cómic. Se seleccionan planos
a lo largo de todo el storyboard, sin generar los sobrantes. Si faltan propuestas
visuales, se informa del bloqueo en lugar de repetir imágenes o estirar el audio.
La distribución inicial es editorial aproximada; aún requiere verificación de
sincronía y semántica antes de publicación. Los enlaces se reconstruyen tras una
interrupción parcial. Los errores se registran por trabajo y no detienen los
demás canales. Los recibos antiguos sin ese formato no se migran por inferencia.
Vibes conserva su adaptador pendiente, y falta enlazar las imágenes aceptadas con
animación, subtítulos y montaje finales.

Las imágenes nuevas aceptadas deben incluir un `motion_plan` observado sobre la
imagen: regiones ambientales y rectángulos de protección para estructuras rígidas.
El ejecutor sella el plan con el hash de la imagen y prepara `ambient` en GPU.
La duración de cada escena se guarda en fotogramas; la última puede ser menor de
cinco segundos para terminar con la narración. `local.json` guarda `media_root`
e `intro_path`, fuera de Git. La prueba real repetida con una ilustración existente
de Tambora produjo 120 fotogramas en RTX 5070 y superó decodificación y protección
de píxeles. El render tardó 2.407 segundos, sin generar otra imagen ni usar agentes.
El contador de fotogramas con cambios detecta planes que no producen movimiento
visible; no prueba por sí solo que el movimiento tenga sentido narrativo.

La voz terminada prepara también `captions` para el canal cómic. Usa el Whisper
large-v3 ya instalado, con red deshabilitada y CPU para dejar libre la GPU de
animación. No descarga pesos. Los tiempos observados se comparan con la narración
canónica; se conservan sus palabras, puntuación y tildes en ASS, abajo, en rosa y
lima y sin panel negro. Los números enteros reconocidos como cifras (hasta 9999)
pueden alinearse con sus palabras españolas; sus tiempos internos son subdivisiones
aproximadas y quedan anotados. Otras discrepancias impiden continuar automáticamente.
La prueba real del cierre reconoció todas sus palabras y produjo dos bloques de
subtítulos sin llamadas externas. No acredita revisión audiovisual independiente.

La etapa `voice_generate` está conectada al ejecutor y usa el generador Google
recuperado en `scripts/providers/`, sin modificar ni ejecutar código del proyecto
histórico. Envía un solo texto y una sola voz por petición; no reintenta errores.
Antes de enviar persiste un intent y ocupa el recurso remoto. Tras una respuesta
válida encadena `voice` para comprobar procedencia y aplicar el ritmo aprobado.
La configuración real del script pasó `ValidateOnly` en Windows, sin lectura de
credenciales ni llamada de red. Una prueba posterior realizó una única petición
real de Kore para el cierre aprobado del canal. Google guardó el WAV, pero faltó
el cmdlet `Get-FileHash` en ese proceso. Se sustituyó por SHA-256 de .NET y se
recuperó el audio ya devuelto, conservando el manifiesto fallido. Resultado final
2.9831 segundos a ×1,15, decodificación completa y reutilización comprobadas.
La recuperación no volvió a llamar a Google y no acredita escucha independiente.
`reconcile_saved_audio` solo admite este fallo concreto posterior al guardado del
WAV; otros fallos o respuestas ambiguas continúan bloqueados.

Con presupuesto adicional cero, necesita evidencia reciente (máximo 24 horas) en
`.runtime/providers/google-tts-free-tier.json`: modelo, fecha de comprobación,
facturación desactivada, vínculo verificado entre proyecto y credencial,
ruta/hash del registro DPAPI configurado y evidencia de la comprobación. No
contiene la clave. Ver proyectos gratuitos en Studio no prueba por sí solo ese
vínculo; no inventar `credential_project_verified=true`. Falta automatizar esta
comprobación para que su caducidad no requiera intervención en producción diaria.
En la prueba real se contrastó la referencia enmascarada única de la tabla de
claves y su nivel gratuito con el sufijo de la credencial en memoria protegida;
solo se devolvió coincidencia y hash del registro cifrado, nunca la clave.

La etapa `voice` consume una petición `voice_from_provider_v1` con canal, texto
canónico y manifiesto Google ligado por hash. Reutiliza únicamente el audio
original cuya voz, idioma, texto y hash coinciden. Conserva velocidad natural en
Religion y aplica `atempo=1.15` a Kore en ¿Sabías que?, sin cambiar el tono.
Una repetición idéntica reutiliza el resultado; un archivo modificado o una
operación interrumpida se detiene para reconciliar. No genera voces nuevas aún.

Prueba real con el audio original de Tambora: 24.0306 segundos, decodificación
completa y caché comprobadas; cero llamadas de proveedor y cero tokens de agente
en esa etapa local. No es una medida del consumo total de un reel. La escucha
independiente y la revisión de condiciones comerciales siguen pendientes.
El comprobador de medios admite audio sin debilitar el requisito de pista de
vídeo que conserva por defecto al validar un máster.

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
