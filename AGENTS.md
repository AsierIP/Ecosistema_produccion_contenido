# Ecosistema de producción de contenido

Este repositorio es la autoridad del núcleo compartido. Las particularidades van
en `channels/`; las políticas comunes, en `config/`; el estado local, en `.runtime/`.
No duplicar el núcleo por canal. No modificar los proyectos históricos para una
migración implícita. No leer ni tocar Tradeo.

Ante «tengo una idea para un canal», consultar `config/onboarding.json`, recuperar
lo ya conocido y preguntar solo los campos que faltan por bloques breves. Registrar
la ficha con `python -m ecosystem onboard --answers ...`. No inventar cuentas,
fuentes, consentimiento, estilo aprobado ni un presupuesto. Crear logo y portada
con las herramientas de imagen disponibles cuando el briefing esté definido.

Para la producción diaria, ejecutar primero `python -m ecosystem daily` y leer
su resultado compacto. Un trabajo en cola no equivale a un vídeo terminado.
`readiness` informa de los requisitos pendientes. Nunca ignorar un bloqueo.
Preparar cápsulas mediante `dispatch-packet`; cada agente recibe solo su etapa,
perfil de canal y artefactos necesarios. Los modelos están en `config/models.json`.
No lanzar subagentes para polling, hashes, montaje o validación determinista.

No prometer ahorro porcentual sin comparar consumo real y calidad. No contratar
APIs, descargar pesos grandes ni cambiar voces para abaratar sin autorización.
La GPU se comparte con lease global; RIFE depende del perfil de cada canal. Religion
permite 2x por cada uno de tres segmentos distintos según su contrato vigente;
no interpolar cortes, repetir fuentes ni deformar la voz.

QA editorial y audiovisual independiente obligatorio. Una publicación requiere
identidad exacta, licencia, máster decodificado, subtítulos literales, intención
durable, prueba pública por plataforma y mismo hash. Un intent incierto obliga a
reconciliar antes de repetir. CAPTCHA, OTP y autenticación son del usuario.

El código puede ir a GitHub; fuentes privadas, PDFs, cuentas de correo, claves,
sesiones, registros operativos, pesos y medios se quedan fuera de Git.
