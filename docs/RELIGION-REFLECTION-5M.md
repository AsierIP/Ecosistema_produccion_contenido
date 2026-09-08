# Reflexiones de cinco minutos

Perfil independiente: `config/profiles/religion-reflection-5m-prototype-v1.json`.
Esta línea combina autoayuda espiritual cristiana original con fuentes RV1909.
No modifica el contrato de los Shorts ni sus reglas de mirada diegética.

## Norma visual del prototipo

- Jesús es el personaje central y mira directamente al espectador.
- Una imagen de identidad común, diez animaciones sencillas y composición fija.
- Zoom lento de entrada o salida, respiración, parpadeo y viento discretos.
- Se permiten personas secundarias quietas; no hacen falta acciones complejas.
- Cada clip nativo se interpola por separado con GPU RIFE v4.25 a seis veces
  los fotogramas y se reproduce a 24 fps. No se interpolan los cortes.
- Diez bloques cubren la narración continua de unos cinco minutos. No se
  ralentiza, acelera ni repite la voz para completar la duración.
- Subtítulos literales, legibles y sin tapar los ojos. Imágenes y fuentes
  licenciadas, guion, cita literal y adaptación editorial se registran aparte.

## Ejecución recuperable

`scripts/upro-reflection-vibes.cjs` anima medios identificados de un proyecto
de Vibes mediante el navegador propio de Upro. Guarda una intención antes de
solicitar cada animación y descarga únicamente el vídeo identificado. Un
resultado de imagen no se considera un vídeo terminado. Las solicitudes
inciertas se reconcilian; no se repiten silenciosamente.

`scripts/render-reflection-prototype.py` recibe `--workspace`,
`--native-directory` y `--output`. Reutiliza bloques verificados y ejecuta
`ecosystem/reflection_media.py`: reserva global de GPU, interpolación, montaje,
mezcla, subtítulos, recuento real de fotogramas y decodificación completa.
Los MKV requieren recuento con ffprobe; no siempre incluyen `nb_frames`.

La revisión automática usa `review-google-video.ps1 -ReviewKind Reflection`.
Su contrato acepta expresamente la mirada a cámara y la sencillez. El muestreo
visual de un cuadro por segundo complementa las comprobaciones locales; no
equivale a revisión humana de todos los fotogramas. Los archivos remotos se
eliminan después de la revisión y se conserva su comprobante.

## Calidad y recursos

Se reutilizan las tomas de voz y la música existentes que conserven sus hashes.
La transcripción y el montaje se ejecutan localmente. Se revisan solo los
fragmentos donde ASR discrepa antes de regenerar voz. Las variantes audibles se
reflejan en los subtítulos; no se presenta una adaptación como cita literal.

El objetivo del prototipo es terminar y aprender. Las imperfecciones estéticas
menores se anotan para el siguiente vídeo. No se omiten narración completa,
subtítulos fieles, identidad, licencias ni integridad técnica.

Las solicitudes, cuentas, medios y comprobantes operativos permanecen fuera de
Git. Este adaptador de prototipo no activa por sí mismo la producción diaria de
la línea: finalizar un vídeo y habilitar su planificación automática son pasos
distintos.
