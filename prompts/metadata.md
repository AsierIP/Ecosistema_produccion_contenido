# Metadatos desde el guion aprobado

Lee exclusivamente el guion, su mapa de fuentes y la ficha del canal incluidos
en la cápsula. No investigues de nuevo afirmaciones ya revisadas ni añadas hechos.
Produce título, descripción y etiquetas en el idioma autorizado; evita promesas
engañosas y clickbait que contradiga la narración. Respeta la divulgación de IA.
Para `sabias-que`, aplica `.agents/skills/sabias-que-descripciones/SKILL.md`:
solo un párrafo de resumen y «Dale like y suscríbete para saber más cosas.»;
sin hashtags ni bibliografía, salvo la atribución pública mínima exigida por
la licencia de los recursos. Usa el ajuste de plataforma para declarar IA.
No publiques ni modifiques identidades. Guarda el JSON de metadatos dentro de la
salida asignada y devuelve el recibo estructurado con su hash, bytes y las
comprobaciones realmente hechas. Si falta el guion aprobado, devuelve BLOCK.
