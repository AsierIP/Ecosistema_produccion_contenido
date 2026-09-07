# Upro en Windows

Upro es el panel local del ecosistema. Al iniciarlo abre el navegador y mantiene
el motor en el PC. Cada línea conserva su configuración, controles de calidad y
estado. Las líneas habilitadas se atienden según sus permisos, recursos y
adaptadores disponibles. Una línea bloqueada se muestra como bloqueada: abrir
el programa no equivale a haber generado o publicado un vídeo.

## Abrir el programa

Haz doble clic en `Upro.cmd`, en la raíz del repositorio. Si se ha construido el
ejecutable, ese acceso inicia `.runtime/dist/Upro/Upro.exe`; también puedes abrir
el ejecutable directamente o crear un acceso directo de Windows hacia él.
La dirección predeterminada del panel es `http://127.0.0.1:8765/`.

Una segunda apertura recupera el panel de la misma carpeta. Si ese puerto
pertenece a otro programa o a otro repositorio Upro, el lanzador lo indica y no
lo reutiliza. El servidor solo escucha en el propio PC. No expongas ese puerto
a Internet ni abras el firewall para Upro.

La ventana del navegador es el panel; cerrarla no detiene el motor. Para detenerlo
usa el control de apagado del panel. Para detener solo una línea, usa su
interruptor. Las pausas y bloqueos respetan los límites de las etapas en marcha;
no son una garantía de cancelación instantánea de un servicio externo.

## Construir Upro.exe

Necesitas Python 3.12 o posterior. El modo predeterminado usa el compilador .NET
Framework incluido en Windows; no descarga ni instala dependencias:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-upro.ps1
```

Este **ejecutable ligero** inicia el Python instalado con el código actual del
repositorio. Por eso las mejoras en el motor y el panel se aplican al reiniciar
Upro sin recompilar el lanzador. El ejecutable necesita conservar acceso al
repositorio y al intérprete con el que se construyó. No es un instalador autónomo.
Si cambia la ruta de Python, reconstruye o define `UPRO_PYTHON` con su ruta
completa. No hace falta distribuir fuentes privadas, pesos ni credenciales.

Para un paquete que incluya el intérprete y el backend, usa un entorno que ya
tenga PyInstaller instalado:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-upro.ps1 -Mode Bundled -Python ruta\python.exe
```

Ese modo incluye los archivos del panel de `ecosystem/static`. Conserva toda la
carpeta de salida, incluido `_internal`, junto al ejecutable. La configuración y
el estado siguen en el repositorio externo; no se escriben en `_internal`.
El paquete Bundled debe reconstruirse cuando cambia el código integrado.

Ambos modos producen `.runtime/dist/Upro/Upro.exe`, comprueban que puede cargar
el programa y devuelven su hash. El resultado se queda fuera de Git: Git guarda
el código y la receta de construcción, nunca los registros ni los medios.
La comprobación de instalación no certifica la producción completa.

## Diagnóstico

Desde la raíz del proyecto:

```powershell
python scripts/upro_launcher.py --check
python scripts/upro_launcher.py --no-browser --port 8765
python -m ecosystem.upro --root . --port 8765 --no-browser
```

`--check` verifica la ruta y la carga del programa sin iniciar producción.
`--no-browser` mantiene el servidor en primer plano para diagnóstico, sin abrir
otra pestaña. `--root` permite seleccionar una carpeta de proyecto explícita.
Los errores del lanzador se guardan en `.runtime/upro/launcher-error.log`.

## Alcance y costes

El PC debe permanecer encendido y conectado para los servicios externos. La
generación visual, voz y publicación requieren adaptadores operativos y sesiones
válidas. Una verificación de Google, CAPTCHA u OTP se resuelve en la cuenta del
usuario. El panel no sustituye esos servicios ni convierte adaptadores pendientes
en capacidades disponibles. Las pruebas reales y los bloqueos del motor deciden
qué etapas puede ejecutar cada línea.

El panel, planificación, comprobaciones locales y control de procesos no necesitan
un agente por refresco. Los modelos de las etapas editoriales se definen en
`config/models.json`; se envía solo la cápsula y los artefactos necesarios para
esa etapa. Los trabajos recuperables y el uso compartido de GPU evitan duplicados.
El consumo debe medirse con los recibos reales; no se promete un porcentaje de
ahorro sin una comparación de calidad y consumo.
