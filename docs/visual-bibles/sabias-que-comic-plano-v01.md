# ¿Sabías que? · Cómic plano 2D · v01

El usuario eligió el prototipo **C · Cómic plano** el 5 de septiembre de 2026.
La dirección visual y su imagen de referencia están aprobadas. Falta calificar
una escena animada de producción y un reel completo con voz y subtítulos.

## Referencia canónica

- Imagen local: `media/style-prototypes/sabias-que/v01/c-comic-plano.png`.
- SHA256: `0836c73801b7b331351619c809570daea6ad644b2dd5ea0dcdc0718f66227f33`.
- Prompts y alternativas: `docs/prototypes/sabias-que-v01.json`.
- Generación: herramienta integrada `image_gen`. Los medios se guardan fuera de Git.
- El pulpo es una escena comparativa, no una mascota aprobada ni una afirmación
  editorial del libro. Cada curiosidad necesita sus propios sujetos y fuentes.

## Lenguaje visual

Ilustración 2D de cómic, contornos negros expresivos con ligera variación,
formas grandes y siluetas claras. Colores planos, sombreado mínimo y una zona
discreta de trama de puntos cuando ayude a la composición. Expresiones legibles
sin recargar la escena. Evitar apariencia 3D, iluminación fotográfica y detalles
que no se distingan en un móvil.

Conservar los acentos del logotipo existente: rosa intenso, verde lima y negro.
Usar marfil y fondos azul petróleo como apoyo, con contraste suficiente. El verde
lima sirve para destacar un objeto o idea, sin cubrir toda la escena. La paleta
de apoyo se deriva del prototipo; no sustituye al logotipo aprobado.

Componer en vertical 9:16. Reservar espacio para subtítulos y las interfaces de
las plataformas. La narración define el foco visual; no llenar el encuadre con
objetos ajenos al guion. Las letras se añaden en montaje para evitar texto
generado incorrecto. Tipografía, tamaño y colores de los subtítulos se validarán
en el primer reel completo.

## Movimiento sencillo y producción local

Preparar fondo, personajes y objetos en piezas separadas cuando necesiten
moverse. Usar traslaciones, rotaciones, entradas y salidas, parpadeos y dos o tres
poses clave. Una acción principal por plano; el movimiento debe explicar el guion.
Mantener contornos, colores y proporciones entre poses. No deformar rostros con
interpolación automática entre dibujos diferentes.

El acercamiento de cámara es un recurso auxiliar. Una muestra creada con una
sola imagen y cámara demuestra encuadre y ritmo; no demuestra animación de
personajes ni calidad de un reel de producción.

Componer y codificar localmente los fotogramas. Reutilizar configuración,
movimientos, tipografía y recursos gráficos neutros. Crear ilustraciones
específicas para cada historia y comprobar variedad semántica. La codificación
NVENC aprovecha la GPU; el consumo real y el tiempo se registran, sin afirmar
porcentajes de ahorro todavía.

## Comprobaciones antes de producir

El guion y las imágenes deben corresponder con la evidencia de la curiosidad.
La revisión debe comprobar anatomía, objetos y expresiones pertinentes, además
de continuidad visual, legibilidad, sincronización y ausencia de repeticiones
de escenas. Un dibujo de referencia aprobado no acredita esas comprobaciones.

Mantener `production_animation_qualified: false` hasta validar una escena con
movimiento y un reel completo. La elección C no verifica sesiones, no completa
la migración y no activa publicaciones.
