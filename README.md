# Upro · producción de contenido multicanal

Núcleo compartido para canales de YouTube Shorts y TikTok. Cada canal conserva
libro, identidad, voz y estilo; las mejoras de producción se realizan aquí.

**Upro 0.2: aplicación local con ejecutable Windows y panel de controles.
La producción y publicación diaria de extremo a extremo todavía requieren
conectar y cualificar las etapas pendientes de cada canal.**

Abrir `Upro.cmd` o el ejecutable generado inicia el motor local y el panel. Cada
línea tiene un interruptor persistente; hay pausa general, actividad, vídeos y
consumo registrado. El panel y la coordinación no invocan modelos. La línea de
Religion de cinco minutos continúa desactivada. [Cómo abrir Upro](docs/UPRO-INICIO.md).

Incluye los perfiles de **Las Palabras de Cristo / Religion** y **¿Sabías que?**,
recuperados de los contratos actuales de sus proyectos. No modifica sus archivos
ni hereda cuentas entre canales.

## Qué funciona

- Plan diario de un reel por canal, con recuperación del trabajo pendiente.
- Estado SQLite, transacciones, registros inmutables y exclusión GPU/remota.
- Intents de publicación que impiden repetir una subida incierta o verificada.
- Perfiles visuales y revisión de evidencia QA ligados al hash del máster.
- Índices locales de libros/corpus y recuperación de fragmentos con referencias.
- Cápsulas y ejecutor de etapas editoriales con modelo por rol, presupuesto de
  contexto, recibo estructurado y medición del consumo que devuelve el proveedor.
- Inspección y decodificación real con FFmpeg, planes de montaje CPU/NVENC.
- Adaptador RIFE por segmento, probado en la GPU real con conservación de todos
  los fotogramas nativos; aún pendiente de cualificación artística por canal.
- Montaje local de cómic 2D con capas animadas, gráficos y subtítulos, usando
  NVENC y la reserva GPU compartida. Primera prueba completa de ¿Sabías que?
  renderizada y decodificada; revisión editorial y visual aprobada dentro del
  alcance muestreado, escucha perceptiva pendiente.
- Panel local con estado de los canales y cuestionario descargable de alta.

## Inicio

Python 3.12 o posterior; el núcleo usa biblioteca estándar. Para indexar PDF se
necesita `pypdf` en el intérprete elegido. FFmpeg, ffprobe, GPU, pesos y sesiones
son recursos locales que se detectan con `doctor`; no se descargan solos.

```powershell
.\Upro.cmd
# Generar Upro.exe usando el compilador Windows existente, sin descargas:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-upro.ps1
```

El ejecutable queda en `.runtime/dist/Upro/Upro.exe`. Utiliza Python y el código
de este repositorio: las mejoras del motor se aplican al volver a abrir Upro.
Los binarios de compilación permanecen fuera de Git; la receta y todo su código
están versionados. No necesita mantener abierta la conversación para coordinar
las etapas locales que estén preparadas y habilitadas.

```powershell
python -m ecosystem doctor
python -m ecosystem readiness
python -m ecosystem daily
python -m ecosystem dashboard
python -m unittest discover -s tests -v
```

El panel HTML antiguo se crea en `.runtime/dashboard.html`; Upro usa el panel
interactivo de `http://127.0.0.1:8765`. `daily` organiza y reanuda trabajo;
**no genera ni publica vídeos por sí mismo**. El script `scripts/run-daily.ps1`
ejecuta ese plan y actualiza el panel. La programación en Codex se gestiona desde
la app. Upro comprueba la cola mientras está abierto; la automatización antigua
debe permanecer pausada durante la migración para evitar dos productores.

Copiar `local.example.json` a `local.json` y ajustar rutas en otra máquina. En la
máquina de desarrollo ya se ha guardado la configuración local ignorada por Git.

```powershell
python -m ecosystem questionnaire
python -m ecosystem onboard --answers ruta-al-brief.json
python -m ecosystem index-source --source-id mi-libro --path ruta-al-libro.pdf
python -m ecosystem search-source --source-id mi-libro --query "tema concreto"
python -m ecosystem dispatch-packet --job ID --role creative --artifact ficha-fuentes.json
python -m ecosystem run-stage --job ID --role creative --artifact ficha-fuentes.json --execute
python -m ecosystem usage
python -m ecosystem media-probe master.mp4 --decode
python -m ecosystem conform-rife --source segmento-125-frames.mp4 --output candidato-250-frames.mp4
```

`run-stage` ejecuta creative, metadata o quality con la sesión Codex existente.
Visual y release generan cápsulas, pero requieren adaptadores cualificados para
ejecutarse. Un recibo ACCEPT nunca cierra por sí solo una producción.

## Qué falta para la operación completa

1. Terminar y cualificar los adaptadores de generación visual, voz, montaje RIFE
   y publicación, con un reel real por perfil y QA independiente.
2. Reconciliar la autoridad de los productores anteriores antes del cambio.
3. Incorporar las verificaciones y resultados manuales al contrato central:
   identidad de las sesiones, destino TikTok pendiente y animación B2 de
   ¿Sabías que?. La biblia actual está en
   `docs/visual-bibles/sabias-que-b2-v02.md`. Kore con acento español y velocidad
   1,15, subtítulos sin fondo y cierre con like/suscripción siguen aprobados.
   Cuentas de correo y credenciales permanecen en configuración local.
4. Completar la validación técnica y de migración. La publicación automática de
   ¿Sabías que? tras QA está autorizada; esa autorización no sustituye las
   verificaciones pendientes. No se contratan APIs ni se supone un presupuesto.

La GPU detectada es una RTX 5070 de 12 GB. El perfil vigente de Religion permite
RIFE 2× por tres segmentos distintos; esa regla no se impone a otros canales.
El adaptador específico de RIFE comprueba el tratamiento de fotogramas extremos
de la herramienta instalada y conserva su evidencia; sigue pendiente la
cualificación por canal. Nunca se usa una repetición indefinida para completar
duración ni se estira la voz.

## Documentación

- [Abrir y compilar Upro](docs/UPRO-INICIO.md)
- [Motor, etapas y límites de Upro](docs/UPRO-ARQUITECTURA.md)
- [Arquitectura común](docs/ARCHITECTURE.md)
- [Auditoría y conocimiento extraído](docs/AUDIT.md)
- [Operación, recuperación y migración](docs/OPERATIONS.md)
- [Modelos y costes](docs/MODELS-AND-COST.md)
- [Pruebas y límites verificados](docs/VALIDATION.md)
- [Montaje local de cómic 2D](docs/CUTOUT.md)
- [Contrato y estado de la prueba Religion pro v5](docs/RELIGION-PRO-V5.md)

Código, perfiles públicos, prompts y pruebas están versionados. Los libros,
medios, pesos, bases de datos, cachés y credenciales quedan fuera de Git.
