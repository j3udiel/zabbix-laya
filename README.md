# Laboratorio Laya: alertas de Zabbix

Prueba local con ocho alertas ficticias. No se conecta a Zabbix ni ejecuta acciones sobre servidores.

Proyecto independiente para experimentar con Laya; no es una integración oficial de Laya ni de Zabbix.

## Instalación desde cero (Linux, CPU)

Probado en Ubuntu con Python 3.10 y 4 GB de RAM. Necesitas Git, Python con soporte para `venv`, conexión a Internet durante la instalación y espacio para las dependencias y el modelo (aproximadamente 2 GB, más margen temporal). No requiere GPU ni credenciales de Zabbix.

En Debian/Ubuntu, si faltan Git o el módulo `venv`:

```bash
sudo apt-get install git python3-venv
```

Clona el repositorio e instala las dependencias en un entorno aislado:

```bash
git clone https://github.com/j3udiel/zabbix-laya.git
cd zabbix-laya
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements.txt
```

Descarga el modelo y ejecuta una primera prueba con Internet disponible:

```bash
.venv/bin/python evaluar.py --caso disco_lleno
```

Este paso es necesario antes de abrir la interfaz: los pesos no están incluidos en el repositorio. Se descargan en `.cache/huggingface` dentro del proyecto. La primera carga puede tardar; las siguientes reutilizan esa caché. Las predicciones se calculan localmente.

## Interfaz web

```bash
.venv/bin/python ui.py
```

Abre http://127.0.0.1:8765. Para acceder desde otro equipo de una red de confianza, inicia con `--host 0.0.0.0` y abre `http://IP_DEL_EQUIPO:8765`. Es un servidor de laboratorio sin autenticación; no debe publicarse en Internet.

Selecciona un ejemplo, cambia el título, métricas o contexto y pulsa **Evaluar con Laya**. Muestra categorías, puntuaciones y probabilidades, permite editar preguntas y descargar cada prueba como JSON. Las últimas diez pruebas se conservan únicamente en la memoria de la pestaña hasta recargarla. No se guardan las alertas introducidas en el servidor. El modelo permanece cargado entre consultas y funciona sin conexión a Internet.

Una comparación útil: prueba una caída de host de producción y luego cambia el contexto a mantenimiento de un servidor de pruebas. Observa si cambia la estimación de impacto.

## Propuesta de negocio

La página independiente [propuesta.html](propuesta.html), disponible en `/propuesta` al iniciar la UI, recoge la propuesta de monitorización proactiva: casos de uso, arquitectura, automatización, métricas y hoja de ruta. Se puede abrir directamente como archivo, imprimir a PDF y anotar ideas. Las notas se conservan únicamente en el navegador; la página no consulta Zabbix ni Laya. Es una propuesta para evaluar, no una promesa comercial ni un panel operativo.

## API para integraciones locales

La UI conserva el mismo contrato. Otro proceso local puede consultar `GET /api/health` (estado, versión de Laya y revisión del modelo) y enviar `POST /api/predict` con `state`, `questions` y opcionalmente `strict_context: true`. Este modo rechaza con HTTP 422 las entradas o preguntas que el modelo truncaría. La respuesta incluye `result.answers`, `seconds`, `laya_version` y `model_revision`; no genera texto libre.

El orquestador debe calcular y minimizar las features, validar las salidas y conservar su evidencia. Este servicio no recibe tokens ni escribe en Zabbix. La integración predictiva vive separadamente en AI Monitoring; la autorización de escritura corresponde exclusivamente a su fase LAB. Los errores 400/422 indican entradas inválidas y 429 indica otra inferencia en curso. No hay cola persistente ni autenticación para exposición pública.

## Datos y repositorio

Solo los ejemplos sintéticos de `alertas.json` se publican. Introduce alertas reales en la interfaz, no en ese archivo. Entornos virtuales, caché, resultados, registros y formatos habituales de credenciales están excluidos mediante `.gitignore`. Revisa siempre los archivos preparados antes de hacer un commit: ignorar nombres de archivo no detecta secretos incrustados en código o documentación.

## Ejecutar

```bash
.venv/bin/python evaluar.py --offline
.venv/bin/python evaluar.py --offline --caso agente_sin_datos
```

Tras completar la primera descarga, `--offline` utiliza el modelo de `.cache/huggingface` sin acceder a Internet. Cada ejecución guarda un JSON nuevo en `resultados/`, con entradas, preguntas, respuestas completas, versiones y tiempos. La carga del modelo se mide separadamente de las predicciones. La primera predicción puede incluir calentamiento.

## Qué estamos probando

1. `alertas.json`: datos que recibe el modelo en `state` y respuestas esperadas que solo usa el evaluador. Las respuestas esperadas nunca se envían al modelo.
2. `preguntas.json`: categorías (`choice`), escala de gravedad (`score`) y probabilidad de impacto explícitamente confirmado (`noul`).
3. `evaluar.py`: carga únicamente el modelo multilingüe, usa CPU con dos hilos y evalúa cada alerta.

La gravedad va de 0 a 3 en una escala propia del laboratorio; no es la escala nativa de severidades de Zabbix. Puede ser decimal. El umbral 0.5 para impacto es ilustrativo: no está calibrado para producción. “Sin impacto confirmado” incluye información insuficiente; no demuestra que el servicio esté sano. El campo `action` de la respuesta del paquete es metadato: este script no lo ejecuta ni lo trata como autorización.

## Primera ejecución: 24 de septiembre de 2026

Informe local: `resultados/20260924T132609904509Z.json` (excluido del repositorio; el resumen sintético se conserva aquí).

| Caso | Categoría devuelta | P(impacto confirmado) | Evaluación |
|---|---|---|---|
| Host de producción caído | red | 0.997 | Categoría distinta de la esperada: disponibilidad |
| Disco lleno, escrituras fallando | almacenamiento | 0.978 | Ambas correctas |
| CPU alta, tarea normal sin afectación | recursos | 0.820 | Falso positivo de impacto |
| Pérdida de paquetes con cortes | red | 0.978 | Ambas correctas |
| Agente sin datos, servicio desconocido | disponibilidad | 0.968 | Categoría e impacto incorrectos |
| Memoria agotada, errores a clientes | recursos | 0.944 | Ambas correctas |
| Disco al 82%, servicio normal | almacenamiento | 0.068 | Ambas correctas |
| Host de pruebas en mantenimiento | disponibilidad | 0.973 | Falso positivo de impacto |

Resultado: categoría 6/8; impacto 5/8; total 11/16 comprobaciones. La gravedad se registra pero no se incluye en ese total. Tiempos: 0.96–1.17 segundos por alerta, con tres preguntas. Equipo: Intel i3-8100T, 4 GB RAM, CPU. Carga inicial incluida la descarga: 18.9 segundos, aparte del tiempo de importación.

Es una prueba exploratoria pequeña con ejemplos seleccionados, no una estimación de precisión en alertas reales. La clasificación de ICMP puede solaparse entre red y disponibilidad según la taxonomía elegida. Los falsos positivos de impacto muestran un problema más claro: probabilidades altas no garantizan acierto.

## Siguiente experimento

Comparar los mismos casos con preguntas más breves y atómicas, conservando este resultado como referencia. Después validar la configuración elegida con casos nuevos. El mantenimiento, entorno y estado de recuperación deberían tratarse como campos explícitos y reglas de la aplicación cuando estén disponibles, y medir el resultado del modelo por separado del de esas reglas.

## Dependencias y licencia

Las dependencias principales están fijadas en `requirements.txt`; no es un bloqueo completo de todas las dependencias transitivas. Las instrucciones anteriores corresponden al entorno Linux/CPU probado. Otros sistemas o versiones de Python pueden necesitar una selección diferente de PyTorch.

El código original de este laboratorio se distribuye bajo la [licencia MIT](LICENSE). Las dependencias y los pesos de Laya mantienen sus propias licencias; esta licencia no los relicencia. Este repositorio no incluye los pesos del modelo ni el código fuente de esas dependencias.

Fuentes: [repositorio de Laya](https://github.com/NandhaKishorM/laya), [documentación](https://nandhakishorm.github.io/laya/).
