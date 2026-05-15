# Consejos para inferencia con Qwen2.5-3B-Instruct-AWQ

Modelo pequeño (3B parámetros, cuantizado AWQ). Los consejos aplican especialmente
a tareas de análisis de transcripciones de llamadas de ventas de telefonía argentina.

---

## Estructura del prompt

### Múltiples pasadas en lugar de una sola instrucción compleja
Dividir el análisis en varias llamadas LLM, cada una con una tarea concreta.
Un modelo 3B pierde precisión cuando tiene que resolver muchas cosas a la vez.

**Estrategia recomendada para una llamada:**
- Pasada 1 — primeros 20 turnos → empresa origen/destino, tipo de campaña
- Pasada 2 — últimos 30 turnos → resultado (venta/no_venta/sin_definir), cierre comercial leído
- Pasada 3 (solo si no_venta) — turnos intermedios → objeción principal
- Pasada 4 (solo si venta) — turnos intermedios → precio y plan ofrecido

### Máximo 3-4 campos por llamada LLM
A partir de 5-6 campos el modelo empieza a confundir entidades
(ej: pone el nombre del cliente como empresa, mezcla valores entre campos).

### Siempre enums, nunca texto libre
Los campos de texto libre generan loops repetitivos que se truncan al llegar a max_tokens.
Si necesitás capturar un motivo, definir categorías fijas:

```json
"motivo_rechazo": {
  "type": "string",
  "enum": ["precio_alto", "no_le_interesa", "ya_tiene_servicio",
           "mala_experiencia_previa", "necesita_consultar", "sin_definir"]
}
```

### Instrucciones negativas explícitas
El modelo tiende a confundir entidades. Agregar aclaraciones directas:
- "NO uses el nombre del cliente como empresa"
- "Si no se menciona el precio, responde null — NO inventes un valor"
- "empresa_origen es la compañía telefónica actual del cliente, NO su nombre"

### Few-shot: incluir 1-2 ejemplos en el prompt
Los modelos 3B mejoran notablemente con ejemplos concretos dentro del mismo prompt.

```
Ejemplo de respuesta correcta:
{"resultado": "venta", "empresa_origen": "Claro"}

Ejemplo de respuesta cuando no hay información suficiente:
{"resultado": "sin_definir", "empresa_origen": "desconocido"}
```

---

## Manejo del contexto

### Límite de tokens de input
- max_model_len: 4096 tokens
- Dejar mínimo 200 tokens para la respuesta
- Límite práctico de input: ~3500 tokens (~500-600 palabras de conversación)
- Una conversación larga (200+ turnos) supera fácilmente ese límite

### Estrategia de batches por segmento de la llamada
No truncar arbitrariamente — elegir qué parte de la conversación es relevante
para cada pregunta:

| Pregunta | Parte relevante |
|---|---|
| Empresa origen/destino | Primeros 20 turnos |
| Resultado de la llamada | Últimos 30 turnos |
| Precio y plan ofrecido | Búsqueda en turnos intermedios |
| Objeción principal | Turnos intermedios |
| Cierre comercial leído | Últimos 20 turnos |

### Extraer números como string, parsear en Python
El modelo maneja mejor strings que números en contextos ambiguos:

```json
"precio_ofrecido": {"type": ["string", "null"]}
```

Luego en Python extraer el número con regex. Evita que el modelo genere
valores incorrectos al intentar formatear un número.

---

## Contexto de dominio a incluir en el prompt

### Sobre la transcripción
```
IMPORTANTE: Esta transcripción fue generada automáticamente y puede contener
errores ortográficos, palabras mal reconocidas o frases cortadas.
No descartes un segmento solo porque tenga errores de tipeo.
```

### Sobre la diarización
```
IMPORTANTE: Los roles de los hablantes están marcados como DESCONOCIDO porque
la diarización automática no identificó vendedor y cliente correctamente.
El vendedor suele ser quien inicia la llamada, presenta el producto y hace
preguntas de calificación. El cliente suele responder y expresar dudas.
```

### Sobre el dominio
```
Esta es una llamada de ventas de portabilidad de telefonía móvil en Argentina.
El vendedor trabaja para Movistar e intenta convencer al cliente de cambiar
su línea desde otra empresa (generalmente Claro o Personal) a Movistar.
Términos del rubro: gigas/GB, chip, portabilidad, abono, plan, descuento fijo,
cierre comercial, tienda Movistar, fibra óptica, WhatsApp gratis.
Expresiones coloquiales argentinas comunes (no son información relevante):
"te robo un segundo", "no te voy a mentir", "dale", "buenísimo", "sabes".
```

### Sobre el cierre comercial
```
El "cierre comercial" es un texto formal/legal que el vendedor lee al final
de la llamada para confirmar los datos del cliente y los términos del servicio.
Se reconoce porque el vendedor empieza a repetir datos: número de línea,
nombre completo, email, precio, plan contratado, dirección de tienda.
```

---

## Manejo de incertidumbre

- Siempre incluir `null` o `"desconocido"` como opción válida en enums
- Preferir `sin_definir` sobre forzar una clasificación incorrecta
- Si una llamada se corta antes del cierre, el resultado es `sin_definir`, no `no_venta`

---

## Parámetros de inferencia recomendados

```python
SamplingParams(
    temperature=0.0,      # determinista — sin creatividad
    max_tokens=150,       # suficiente para 3-4 campos JSON, evita loops
)
```

Para campos que solo devuelven 1-2 valores (ej: solo resultado):
```python
max_tokens=50
```

---

## Resumen de restricciones del modelo

| Característica | Límite |
|---|---|
| Campos por llamada LLM | Máximo 4 |
| Turnos de conversación por llamada | Máximo 50-60 |
| Tokens de input | Máximo ~3500 |
| Campos de texto libre | Evitar — usar enums |
| Campos numéricos | Extraer como string, parsear en Python |
