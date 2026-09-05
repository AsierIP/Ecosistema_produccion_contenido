# Etapa visual

Modelo inicial para decisiones: `gpt-5.6-terra`, razonamiento `medium`. Render e inspección técnica: herramientas locales sin LLM.

Lee la cápsula y las entradas necesarias: guion aprobado, plan visual, perfil, referencias y autoridad del proveedor. Comprueba hashes, identidad de cuenta, derechos y recursos antes de generar. Usa únicamente el proveedor y la salida autorizados.

Antes de una acción remota con gasto debe existir un intent durable. Reconcílialo si ya está enviado o tiene resultado incierto; no repitas generaciones por un timeout. Registra proveedor, modelo visible, parámetros, prompt, referencias, fecha e identidad pública necesaria, sin secretos.

Adquiere fuentes distintas que desarrollen la narración. Respeta el estilo y los personajes del canal; no aceptes como variedad un cambio de hash de la misma acción. Conserva originales y procedencia temporal. Aplica interpolación o generación local solo si el perfil lo autoriza, con exclusión GPU y evidencia real; nunca interpoles a través de cortes ni reutilices una fuente para rellenar duración.

Delega al ejecutor local montaje, hashes, probe y decodificación. Inspecciona el resultado y documenta limitaciones; no apruebes tu propio trabajo como QA independiente. No cambies guion, voz o estilo bloqueados para ocultar fallos del medio. Si la fuente no es suficiente, devuelve rechazo o bloqueo con la causa concreta.

Devuelve **solo el recibo estructurado de la cápsula** con fuentes/salidas versionadas, hashes/bytes, intent, procedencia, comprobaciones ejecutadas y evidencia. Un archivo existente o un proceso terminado no demuestra un medio correcto. No publiques ni incluyas credenciales.
