# ¿Sabías que? · B2 eléctrico · v02

Dirección seleccionada explícitamente por el usuario el 6 de septiembre de 2026.
Sustituye la dirección C inicial y el uso generalizado de rosa y verde en escenas.

## Referencia aprobada

- `media/style-prototypes/sabias-que/v03/b2-electrico-intenso.png`
- SHA256 `A78F6BE9F2FDB50B2F601E575E605B558EB2EEFE11FB120E6405E295DD5E6036`
- Prompts y comparación: `docs/prototypes/sabias-que-v03.json`.

Cartoon de proporciones exageradas, tinta negra marcada, formas reconocibles y
colores intensos. Cada objeto conserva su familia cromática: mar y cielo azules,
vegetación verde, edificios de tonos propios y materiales reconocibles. Colores
eléctricos no significa pintar todo como el logotipo ni convertir los objetos
en fuentes de luz. El logo y la cabecera existentes conservan su identidad.

## Movimiento

Cambiar de plano cada cinco segundos, incorporando ilustraciones distintas.
La cabecera de marca conserva su duración propia. Proteger explícitamente barcos,
chimeneas, edificios y otros objetos rígidos; el humo no debe arrastrar su chimenea.
Comprobar en cada fotograma que los píxeles protegidos y ajenos a las regiones
móviles son idénticos al original antes de codificar. Revisar también las máscaras
en imagen: una comprobación numérica no identifica por sí sola los objetos.

Las escenas de cómic mantienen movimiento ambiental continuo y pertinente:
olas, humo, hojas, cabello o ropa según el contenido. La cámara es un complemento.
Utilizar capas o regiones acotadas y suaves, evitando deformar caras, arquitectura
o elementos que deberían permanecer rígidos. Los fotogramas y el montaje se
calculan localmente cuando sea viable; la reserva GPU es común a todos los canales.

La animación por regiones CUDA es una técnica para ilustraciones. No constituye
generación local del dibujo original, ni convierte una fotografía fija en un
documento que capture movimiento real. No aplicar esa deformación a fotos de archivo.

## Material documental

Buscar fotografías, documentos u objetos reales relacionados cuando aporten
contexto. Verificar identidad, procedencia y derechos; mantener fuente y licencia
con el máster. Ajustar moderadamente contraste y encuadre sin inventar contenidos
ni colorizar por IA como si fueran originales. Un movimiento suave de cámara
puede acompañar la foto. Guardar créditos en las notas de entrega y descripción,
respetando la solicitud de no añadir otros rótulos en pantalla.

## Texto y voz

Un único bloque inferior contiene exclusivamente lo que narra la voz. No duplicar
frases como titulares superiores ni añadir números/rótulos que repitan el dato.
Fucsia `#FF009D` y lima `#C8FF00`, con contorno negro y contraste legible. El
resaltado puede seguir la voz dentro del mismo bloque. Los gráficos pueden
explicar el dato sin convertirlo en un segundo texto.

Mantener Kore, su identidad y el timbre cálido original, con acento español
peninsular. Expresividad intermedia, cercana y natural, sin exageración publicitaria
ni grandes subidas de tono. Mantener un ritmo fluido parecido al original;
no acelerar ni cambiar el tono del archivo posterior. Recortar
únicamente silencios de los extremos cuando esté comprobado que no corta habla.

La duración queda subordinada al contenido y a la locución. Se permite dejar
tiempo final para observar un documento, sin repetir la voz. Estas decisiones
de estilo no equivalen a un PASS audiovisual ni activan publicaciones.
