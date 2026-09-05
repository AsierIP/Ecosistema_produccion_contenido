# Ecosistema de producción de contenido

Núcleo compartido para canales de YouTube Shorts y TikTok. Cada canal conserva
libro, identidad, voz y estilo; las mejoras de producción se realizan aquí.

**Estado: primera versión local probada, migración pendiente. La producción y
publicación diaria de extremo a extremo aún no están activadas.**

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
- Panel local con estado de los canales y cuestionario descargable de alta.

## Inicio

Python 3.12 o posterior; el núcleo usa biblioteca estándar. Para indexar PDF se
necesita `pypdf` en el intérprete elegido. FFmpeg, ffprobe, GPU, pesos y sesiones
son recursos locales que se detectan con `doctor`; no se descargan solos.

```powershell
python -m ecosystem doctor
python -m ecosystem readiness
python -m ecosystem daily
python -m ecosystem dashboard
python -m unittest discover -s tests -v
```

El panel se crea en `.runtime/dashboard.html`. `daily` organiza y reanuda trabajo;
**no genera ni publica vídeos por sí mismo**. El script `scripts/run-daily.ps1`
ejecuta ese plan y actualiza el panel. La programación en Codex se gestiona desde
la app y no se instala un segundo programador de Windows.

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
3. Verificar la sesión de YouTube `@sabias-quecuriosidad` y la cuenta Vibes
   asignada localmente, completar TikTok y validar la animación sencilla del
   cómic plano 2D elegido para ¿Sabías que?. La referencia C y su biblia visual
   están en `docs/visual-bibles/sabias-que-comic-plano-v01.md`.
   Su voz Kore y su logo neón v04 ya están aprobados. El correo Vibes permanece
   exclusivamente en configuración local, fuera de Git.
4. Fijar presupuesto, disponibilidad del PC, horarios y política de publicación
   de ¿Sabías que?; después activar la cadencia diaria.

La GPU detectada es una RTX 5070 de 12 GB. El perfil vigente de Religion permite
RIFE 2× por tres segmentos distintos; esa regla no se impone a otros canales.
El adaptador específico de RIFE comprueba el tratamiento de fotogramas extremos
de la herramienta instalada y conserva su evidencia; sigue pendiente la
cualificación por canal. Nunca se usa una repetición indefinida para completar
duración ni se estira la voz.

## Documentación

- [Arquitectura común](docs/ARCHITECTURE.md)
- [Auditoría y conocimiento extraído](docs/AUDIT.md)
- [Operación, recuperación y migración](docs/OPERATIONS.md)
- [Modelos y costes](docs/MODELS-AND-COST.md)
- [Pruebas y límites verificados](docs/VALIDATION.md)

Código, perfiles públicos, prompts y pruebas están versionados. Los libros,
medios, pesos, bases de datos, cachés y credenciales quedan fuera de Git.
