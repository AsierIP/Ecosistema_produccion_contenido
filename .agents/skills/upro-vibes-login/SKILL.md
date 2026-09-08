---
name: upro-vibes-login
description: Gestionar el acceso autorizado a las cuentas de Vibes de los canales de Upro usando códigos reenviados al buzón central conectado.
---

# Acceso multicanal a Vibes

El usuario establece una cuenta propia de Vibes para cada canal de YouTube que
use ese proveedor. Los códigos se reenvían al buzón central declarado en
`.runtime/authorizations/vibes-email-login-codes.json`. Leer esa configuración
antes de autenticar; no inventar cuentas ni considerar configurado el reenvío de
un canal que todavía no tenga su correspondencia registrada.

La autorización del usuario permite solicitar, leer e introducir esos códigos
para las cuentas de Vibes registradas, sin pedir permiso rutinario de nuevo.
El destinatario original identifica la cuenta de Vibes; el buzón central solo
recibe sus códigos. Mantener un perfil de navegador separado por canal.

Verificar que el perfil del conector Gmail coincide con `code_inbox`. Buscar solo
mensajes recientes de Vibes/Meta ligados al destinatario original `login_email`
y a la solicitud actual. Usar el código más reciente vigente de esa solicitud;
no cruzar códigos entre canales ni reutilizar códigos de otra operación. Serializar
las solicitudes de acceso para evitar mezclar mensajes simultáneos. No mostrar
ni guardar códigos en logs, Git o respuestas.

Reutilizar primero la sesión de Upro. Si hay que autenticar, registrar la operación
sin secretos, solicitar un código una sola vez y comprobar la cuenta y el proyecto
al entrar. Si el proveedor confirma caducidad, solicitar un único reemplazo. Ante
CAPTCHA, identidad ambigua o rechazo reiterado, conservar el estado y solicitar
la intervención concreta necesaria. Nunca repetir una generación para probar login.

La autorización y el reenvío declarado no prueban que el ejecutable tenga acceso
Gmail autónomo: comprobar sus herramientas reales. Si solo está disponible el
conector de esta conversación, no afirmar que Upro ya puede autenticarse solo.
Guardar direcciones y correspondencias en la configuración local excluida de Git.
