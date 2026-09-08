# Etapa visual

Si la petición es `existing_image_review_v1`, la imagen ya fue generada y se
incluye en `source_image` y en las entradas de la cápsula. Abre exactamente ese
PNG con la herramienta de inspección; revisa formato, contexto, estilo y regiones
de movimiento. NO llames a ImageGen, no edites ni generes variantes. Devuelve
únicamente ese PNG como artefacto, con hash vacío y bytes=0 para que lo selle el
ejecutor, y el motion_plan descrito abajo si es válido. Si no es válido, devuelve
REJECT con defectos concretos. Este caso de revisión de imagen existente tiene
prioridad sobre las instrucciones de generación nueva del resto del documento.

Al aceptar una imagen del cómic, incluye una comprobación `motion_plan`, con
`passed=true` y `evidence` como JSON serializado. Debe contener `scope_evidence`
describiendo lo que realmente has visto, `protected_rects` para objetos rígidos
(edificios, chimeneas, caras y otros elementos inmóviles) y `regions` únicamente
para elementos ambientales que puedan moverse. Usa rectángulos normalizados
`[x0,y0,x1,y1]`, de 0 a 1. Cada región lleva `rect`, `dx`/`dy` (máximo 10 píxeles),
`period` de 1 a 10 segundos y opcionalmente `spatial_y` y `feather`.
`spatial_x` y `spatial_y` son números de 0 a 50, nunca booleanos; omitirlos
equivale a 0. `feather` es un número entre 0,005 y 0,2. No inventar tipos.
Las imágenes de reels deben ser verticales 9:16. Antes de aceptar, compara época,
tecnología y objetos con el contexto editorial recibido; un barco moderno no
representa una flota de vela histórica. No regeneres por iniciativa propia:
devuelve rechazo concreto para corregir únicamente el plano afectado.
No animar toda la imagen ni incluir estructura rígida en una región sin protegerla.
Comprueba que las regiones móviles tengan superficie fuera de la unión de los
rectángulos protegidos. Si toda la región está protegida, no se moverá ningún
píxel: vuelve a delimitar los objetos a partir de la imagen, sin desprotegerlos.
Si no puedes delimitar movimiento seguro, bloquear. El código guardará el plan;
no añadas un segundo artefacto a la salida ni fabriques una revisión independiente.

Usa el modelo y razonamiento indicados en la cápsula, incluidas las excepciones
por canal. Render e inspección técnica: herramientas locales sin LLM.

Para `generation_provider=imagegen`, el ejecutor local ya ha comprobado los
hashes y creado `imagegen.intent.json` para este intento. No recalcular hashes,
programar scripts, investigar herramientas ni explorar el repositorio. Leer la
petición `image_generation_request_v1`, ver su referencia declarada, llamar a
ImageGen exactamente una vez y revisar visualmente el resultado. No producir
variantes ni usar APIs de pago. Entregar en `artifacts` únicamente la ruta PNG
original devuelta por ImageGen, con `sha256` vacío y `bytes=0`: el ejecutor local
copia y sella esos campos. No copiar archivos con herramientas del agente.
La revisión visual solo describe defectos; no constituye QA independiente.
Si algo no funciona, devolver BLOCK con la causa concreta y parar; no depurar
el entorno. Este protocolo específico sustituye las tareas de archivo y hash
del procedimiento genérico descrito a continuación.

Lee la cápsula y las entradas necesarias: guion aprobado, plan visual, perfil, referencias y autoridad del proveedor. Comprueba hashes, identidad de cuenta, derechos y recursos antes de generar. Usa únicamente el proveedor y la salida autorizados.

Antes de una acción remota con gasto debe existir un intent durable. Reconcílialo si ya está enviado o tiene resultado incierto; no repitas generaciones por un timeout. Registra proveedor, modelo visible, parámetros, prompt, referencias, fecha e identidad pública necesaria, sin secretos.

Adquiere fuentes distintas que desarrollen la narración. Respeta el estilo y los personajes del canal; no aceptes como variedad un cambio de hash de la misma acción. Conserva originales y procedencia temporal. Aplica interpolación o generación local solo si el perfil lo autoriza, con exclusión GPU y evidencia real; nunca interpoles a través de cortes ni reutilices una fuente para rellenar duración.

Delega al ejecutor local montaje, hashes, probe y decodificación. Inspecciona el resultado y documenta limitaciones; no apruebes tu propio trabajo como QA independiente. No cambies guion, voz o estilo bloqueados para ocultar fallos del medio. Si la fuente no es suficiente, devuelve rechazo o bloqueo con la causa concreta.

Devuelve **solo el recibo estructurado de la cápsula** con fuentes/salidas versionadas, hashes/bytes, intent, procedencia, comprobaciones ejecutadas y evidencia. Un archivo existente o un proceso terminado no demuestra un medio correcto. No publiques ni incluyas credenciales.
