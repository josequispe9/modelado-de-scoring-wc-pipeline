# Consejos para inferencia con vLLM — análisis de transcripciones

Aplican especialmente a tareas de análisis de transcripciones de llamadas de
ventas de telefonía argentina.

---

## Modelo en uso

| Parámetro | Valor |
|---|---|
| Modelo | `Qwen/Qwen2.5-7B-Instruct-AWQ` |
| GPU | RTX 3060 8 GB VRAM |
| `gpu_memory_utilization` | 0.85 |
| `max_model_len` | 4096 |
| Pesos en VRAM (aprox.) | ~5 GB |
| Resto del 85% | KV cache pre-allocado |
| Margen libre (15%) | ~1.2 GB — reserva para overhead de CUDA/kernels |

**Modelo anterior probado:** `Qwen/Qwen2.5-3B-Instruct-AWQ` con `gpu_memory_utilization=0.50`
(valor sin justificación documentada, se subió a 0.85 con el 7B sin problema).

### Resultado del test con 10.485 archivos
El modelo 7B-AWQ completó el análisis completo sin crashes.
Temperatura 0.0, salida JSON estructurada con `StructuredOutputsParams`.
Tiempo promedio por archivo: ~0.3 s.

### Si crashea durante inferencia (OOM)
El crash indica que el overhead de CUDA está presionando la VRAM libre.
**Solución:** bajar `gpu_memory_utilization` de 0.85 a 0.80.
No bajar `max_model_len` — con prompts de ~750 tokens no impacta en nada.
La GPU compartida (shared memory) sirve de overflow lento pero no previene crashes OOM.

---

## Estructura del prompt

### Múltiples pasadas en lugar de una sola instrucción compleja
Dividir el análisis en varias llamadas LLM, cada una con una tarea concreta.
El modelo pierde precisión cuando tiene que resolver muchas cosas a la vez.

**Estrategia recomendada para una llamada:**
- Pasada 1 — primeros 20 turnos → empresa origen/destino, tipo de campaña
- Pasada 2 — últimos 30 turnos → resultado (venta/no_venta/sin_definir), cierre comercial leído
- Pasada 3 (solo si no_venta) — turnos intermedios → objeción principal
- Pasada 4 (solo si venta) — turnos intermedios → precio y plan ofrecido

### Máximo 3-4 campos por llamada LLM
A partir de 5-6 campos el modelo empieza a confundir entidades
(ej: pone el nombre del cliente como empresa, mezcla valores entre campos).
El 7B es más robusto que el 3B en este aspecto, pero la limitación sigue siendo válida.

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

Para campos binarios o de pocos valores (ej: `{"problema_senal": "si/no"}`):
```python
max_tokens=30
```

**Nota:** con `StructuredOutputsParams(json=schema)` el modelo respeta el schema
y no genera loops. `max_tokens=30` fue suficiente para todos los archivos en la prueba.

---

## Calidad observada — clasificador `problema_senal`

Test sobre 10.485 archivos con el modelo 7B-AWQ. Muestra manual de 45 archivos "si":

| Categoría de FP | Descripción | % aprox. de FPs |
|---|---|---|
| Vago | "no me funcionó", "no me va bien", "muchos problemas" sin mencionar señal | ~60% |
| Carrier equivocado | Queja de señal de Claro (su compañía actual), no de Movistar | ~20% |
| Infraestructura laboral | Subsuelo con antenas internas de otro operador | ~10% |
| Otro servicio | Wi-Fi hogar / internet fijo, no señal móvil | ~10% |

**Tasa de FP estimada: ~22%** (10/45 en muestra).
El modelo 7B detecta más casos que el 3B (335 vs 252 "si") pero con más FPs por ser
más interpretativo con frases vagas.

### Prompt pendiente de ajuste
Para reducir FPs, el prompt de `problema_senal` debería exigir mención **explícita**
de señal/cobertura de Movistar. Además, este clasificador se va a expandir a una
categoría más amplia `mala_experiencia_previa` con subcategorías:
- `senal` — sin cobertura geográfica
- `sin_sucursal` — no tiene oficina/atención presencial en la zona
- `infraestructura` — subsuelo o edificio con infraestructura exclusiva de otro operador
- `servicio_general` — mala experiencia sin especificar
- `precio` — se fue porque era caro

---

## Resumen de restricciones del modelo

| Característica | Límite |
|---|---|
| Campos por llamada LLM | Máximo 4 |
| Turnos de conversación por llamada | Máximo 50-60 (segmento todo_40 probado OK) |
| Tokens de input promedio (todo_40) | ~400-600 tokens |
| Tokens de input máximo observado | ~750 tokens |
| Campos de texto libre | Evitar — usar enums |
| Campos numéricos | Extraer como string, parsear en Python |
