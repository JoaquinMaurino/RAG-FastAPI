# Agent Improvement Roadmap

## Propósito de este documento

Este es el roadmap unificado para todo lo relacionado a mejorar el endpoint `/agent` y la calidad general del sistema RAG — **sin** incluir despliegue a GCP/MLOps, que queda en su propio documento separado (`MLOPS_DEPLOYMENT_PLAN.md` o el nombre que le hayas dado).

Cubre, en orden de ejecución recomendado:

- **Fase 1 — Core Agent Consistency:** estabilidad y consistencia arquitectónica del agente (provider abstraction, guardrails, error handling, memoria).
- **Fase 2 — Retrieval Pipeline Quality:** mejoras al pipeline de recuperación de información (query rewriting, hybrid search, filtering, re-ranking, compression).
- **Fase 3 — Response Quality & Traceability:** citas de fuentes y streaming.
- **Fase 4 — Evaluation Framework:** medición objetiva de calidad del RAG.
- **Fase 5 — Observability:** trazabilidad completa de lo que hace el sistema.
- **Fase 6 — Cost & Performance Monitoring:** métricas de tokens, latencia y costo.
- **Fase 7 — LLM Optimization:** model routing, prompt versioning, semantic cache.
- **Fase 8 — Testing Integral:** tests de routing del agente y de calidad del pipeline.

**Regla general para el agente ejecutor:** no avanzar a la fase N+1 sin que la fase N pase sus criterios de aceptación. Si una tarea requiere una decisión de diseño no especificada acá, preferir la opción más simple, consistente con el resto del código del proyecto, y documentarla en el propio código — no expandir el alcance inventando funcionalidad no pedida.

---

# FASE 1 — Core Agent Consistency

## Contexto

El endpoint `/agent` ya tiene la integración RAG correcta (`search_documents` reutiliza `search_service.search_chunks`, el mismo flujo que `/chat`). Lo que falta es que el resto de la implementación esté al mismo nivel de calidad que el resto del proyecto: hoy el agente instancia el LLM de forma hardcodeada, no tiene límites de ejecución, no maneja errores, y no está conectado a la memoria conversacional. Esta fase es la base — todo lo que sigue (evaluación, observabilidad, optimización) asume un agente estable.

---

## Phase 1.1 — Provider Abstraction Alignment

**Objetivo:** que el agente construya su LLM a través de la misma abstracción de provider (Gemini/Ollama vía env var) que usa `/chat`, en vez de instanciar `ChatGoogleGenerativeAI` directamente.

**Por qué importa:** Tener dos formas distintas de construir el LLM en el mismo proyecto es una inconsistencia arquitectónica que salta a la vista en un code review. Además, sin esto no se puede testear el agente localmente con Ollama sin gastar cuota de la API de Gemini. Es también un talking point de entrevista: "un único punto de construcción del LLM, intercambiable por config".

**Tareas:**
1. Ubicar la función/factory de provider que ya usa `/chat`.
2. Reemplazar la instanciación directa de `ChatGoogleGenerativeAI` en el agente por una llamada a esa factory.
3. Si la factory actual está atada a un contexto específico de `/chat`, extraer la parte de construcción pura del LLM a una función compartida, sin romper el uso existente en `/chat`.
4. `temperature=0.0` debe seguir aplicándose para el caso del agente (parametrizable en la factory).

**Archivos afectados:** `app/agents/*.py`, el módulo de provider/LLM compartido.

**Criterios de aceptación:**
- [x] No queda ninguna instanciación directa de `ChatGoogleGenerativeAI` dentro del módulo del agente.
- [ ] Cambiando la env var de provider a Ollama, `/agent` sigue funcionando end-to-end contra un modelo local.
- [x] `/chat` sigue funcionando sin cambios de comportamiento (regression check).
- [ ] `pytest tests/ -k "agent and provider" -v` confirma que el agente usa la factory compartida.

---

## Phase 1.2 — Execution Guardrails

**Objetivo:** evitar loops descontrolados o ejecuciones colgadas del `AgentExecutor`.

**Por qué importa:** Sin `max_iterations` ni `max_execution_time`, un agente con tool-calling mal formado puede iterar indefinidamente, generando costo de API sin control. Requisito básico de cualquier agente "production-grade".

**Tareas:**
1. Configurar `AgentExecutor` con `max_iterations=5`, `max_execution_time=30`, `handle_parsing_errors=True`, `early_stopping_method="generate"`.
2. Verificar en logs que, al forzar un límite artificialmente bajo en un test, el executor corta la ejecución de forma controlada.

**Archivos afectados:** módulo de construcción del `AgentExecutor`.

**Criterios de aceptación:**
- [x] `AgentExecutor` tiene los 4 parámetros de guardrail configurados.
- [ ] Test con `max_iterations=1` y una query que fuerce múltiples tool calls: corta sin excepción no controlada.
- [ ] `pytest tests/ -k "agent and guardrail" -v` pasa.

---

## Phase 1.3 — Error Handling

**Objetivo:** que fallos de la API del LLM, timeouts, o excepciones dentro de una tool no propaguen como error 500 sin contexto.

**Por qué importa:** En producción, la API de Gemini puede devolver rate limits, timeouts o errores transitorios. El endpoint debe degradarse de forma controlada.

**Tareas:**
1. Envolver `_agent_executor.ainvoke(...)` con `try/except`, capturando excepciones del provider y errores de parsing/tool no absorbidos por `handle_parsing_errors`.
2. Loguear el error con `loguru` incluyendo la query original (nunca la API key).
3. Reutilizar el formato de error consistente que ya exista en el resto de la API.
4. Mapear excepciones a códigos HTTP apropiados (503 provider, 422 input inválido, etc.) en la capa de ruta.

**Archivos afectados:** `app/agents/*.py` (`run_agent`), `app/api/routes/agent.py`.

**Criterios de aceptación:**
- [x] `run_agent` nunca deja propagar una excepción no controlada hacia la ruta HTTP.
- [ ] Test que mockea el LLM para lanzar rate limit: el endpoint responde con código de error apropiado y JSON informativo.
- [x] Los logs muestran query + tipo de error, no el traceback crudo expuesto al cliente.
- [ ] `pytest tests/ -k "agent and error" -v` pasa.

---

## Phase 1.4 — Conversational Memory Integration

**Objetivo:** conectar el agente con la capa de memoria (`MEMORY_LAYER_PLAN.md`), para que `/agent` tenga historial conversacional igual que `/chat`.

**Prerrequisito:** depende de que al menos `HybridMemory`/`NoMemory` esté implementado. Si no lo está, esta fase queda bloqueada — no improvisar una integración paralela.

**Por qué importa:** Hoy cada llamada a `/agent` es stateless. Conectar memoria es lo que lo hace utilizable en una conversación real.

**Tareas:**
1. Agregar `MessagesPlaceholder(variable_name="chat_history")` al prompt del agente.
2. Antes de invocar `ainvoke`, obtener el historial desde la estrategia de memoria configurada.
3. Persistir el turno (query + output) en el storage de memoria, igual que `/chat`.
4. Adaptar formatos si es necesario (`HumanMessage`/`AIMessage`).

**Archivos afectados:** módulo del agente, `app/services/memory_service.py`.

**Criterios de aceptación:**
- [ ] Conversación de 2 turnos con referencia implícita al primero se responde correctamente.
- [x] El historial persistido es consistente con el modelo de datos de `/chat`.
- [x] Con `MEMORY_STRATEGY=none`, el agente sigue funcionando sin historial.
- [ ] `pytest tests/ -k "agent and memory" -v` pasa.

---

# FASE 2 — Retrieval Pipeline Quality

## Contexto

El pipeline actual es: pregunta → embedding → búsqueda en pgvector → top-K → prompt → LLM. Es funcional, pero en producción este pipeline evoluciona bastante porque la búsqueda vectorial pura tiene puntos ciegos conocidos: falla con nombres propios, códigos de error, IDs o términos exactos, y no siempre trae los documentos más útiles en el orden correcto. Esta fase mejora la *precisión* de lo que se recupera antes de siquiera llegar al LLM — que es, en la mayoría de los sistemas RAG reales, donde está el mayor margen de mejora (más que en el prompt o el modelo).

---

## Phase 2.1 — Query Rewriting

**Objetivo:** reformular la pregunta del usuario con un LLM antes de buscar, para maximizar la relevancia de la recuperación.

**Por qué importa:** Las preguntas de usuarios reales suelen ser ambiguas, coloquiales, o depender de contexto conversacional ("¿y ese?"). Un rewriter convierte eso en una query autocontenida y explícita, mejor para embeddings y para búsqueda léxica.

**Tareas:**
1. Nueva función `rewrite_query(query: str, chat_history: list) -> str` que invoca al LLM (provider ya abstraído en Fase 1.1) con un prompt corto de reformulación.
2. Integrarla como paso previo a `search_service.search_chunks`, tanto en `/chat` como en la tool `search_documents` del agente.
3. Loguear la query original y la reformulada, para poder auditar el impacto.
4. Guardrail: si el rewriter falla o devuelve algo vacío, hacer fallback a la query original (nunca bloquear el flujo por esto).

**Archivos afectados:** nuevo módulo `app/services/query_rewriter.py`, `search_service`, `app/agents/tools.py`.

**Criterios de aceptación:**
- [ ] Una query ambigua con contexto previo ("¿y las conclusiones?") se reformula a una query autocontenida antes de buscar.
- [x] Si el rewriter lanza una excepción, la búsqueda sigue funcionando con la query original (test de fallback).
- [ ] `pytest tests/ -k "query_rewriter" -v` pasa.

---

## Phase 2.1b — Multi-Query Retrieval

**Objetivo:** a partir de la pregunta del usuario, generar N reformulaciones distintas (no una sola, como en 2.1) y buscar con cada una, para maximizar aún más el recall.

**Por qué importa:** El query rewriting simple (2.1) reformula la pregunta *una vez* a la mejor versión posible. El multi-query va un paso más allá: genera varias variantes con distinto enfoque/vocabulario de la misma pregunta, porque distintas formulaciones recuperan distintos chunks relevantes por similitud semántica. Es el patrón que LangChain ya implementa como `MultiQueryRetriever`. Es especialmente útil cuando la pregunta admite más de un ángulo semántico razonable (ej. "¿cómo funciona la autenticación?" puede formularse también como "flujo de login", "manejo de tokens", "seguridad de acceso").

**Tareas:**
1. Extender (o complementar) `query_rewriter.py` de la Fase 2.1 con una función `generate_query_variants(query: str, n: int = 3) -> list[str]` que invoca al LLM pidiendo N reformulaciones distintas de la misma pregunta.
2. Evaluar usar directamente `MultiQueryRetriever` de LangChain sobre el retriever ya existente, en vez de reimplementar la lógica a mano — es la opción más simple dado que ya se está en el ecosistema LangChain.
3. Ejecutar la búsqueda (semantic/hybrid, según qué tan avanzada esté la Fase 2.2) con cada variante en paralelo, y deduplicar los chunks resultantes por `chunk_id` antes de pasar al paso de re-ranking (Fase 2.4).
4. Hacerlo configurable (`MULTI_QUERY_ENABLED`, `MULTI_QUERY_N`), dado que agrega latencia y llamadas extra al LLM — medir el trade-off con el eval framework (Fase 4) y con las métricas de costo (Fase 6).
5. Definir cómo convive con el query rewriting simple de 2.1: la recomendación es que 2.1 siga aplicándose primero para normalizar la pregunta (resolver referencias del historial conversacional), y que el multi-query genere sus N variantes a partir de esa versión ya normalizada, no de la pregunta cruda del usuario.

**Archivos afectados:** `app/services/query_rewriter.py` (o nuevo módulo `app/services/multi_query.py`), `search_service.py`.

**Criterios de aceptación:**
- [x] Con `MULTI_QUERY_ENABLED=true`, una pregunta genera N variantes verificables en los logs/traces.
- [x] Los chunks recuperados por las distintas variantes se deduplican correctamente antes del re-ranking (ningún chunk repetido llega dos veces al Cross-Encoder).
- [ ] El recall (medible con Context Recall del eval framework, Fase 4) mejora respecto a usar solo el query rewriting simple de 2.1, para al menos un caso de prueba con vocabulario no literal (ej. sinónimos del término buscado).
- [x] Con `MULTI_QUERY_ENABLED=false`, el comportamiento es idéntico al de la Fase 2.1 (regression check).
- [ ] `pytest tests/ -k "multi_query" -v` pasa.

---

## Phase 2.2 — Hybrid Search (Semantic + BM25)

**Objetivo:** combinar búsqueda semántica (embeddings, ya implementada) con búsqueda léxica BM25.

**Por qué importa:** La búsqueda vectorial funciona muy bien para *significado*, pero falla sistemáticamente con coincidencias exactas: nombres propios, códigos de error, IDs, nombres de funciones/variables. BM25 (ranking basado en frecuencia de términos) encuentra exactamente esas coincidencias. Combinar ambos es el patrón estándar en sistemas RAG production-grade.

**Tareas:**
1. Evaluar implementación: `rank_bm25` (liviano, en memoria) vs. el soporte de full-text search nativo de Postgres (`tsvector`/`ts_rank`, más escalable y ya estás en Postgres). Se recomienda la opción de Postgres si el volumen de documentos lo justifica, para no mantener un índice BM25 separado en memoria.
2. Ejecutar ambas búsquedas en paralelo (semántica + léxica) para la misma query.
3. Combinar resultados con una estrategia simple de fusión (ej. Reciprocal Rank Fusion — sumar `1/(k + rank)` de cada lista y reordenar).
4. Exponer el modo (`hybrid`, `semantic_only`, `lexical_only`) como parámetro configurable, con `hybrid` como default.

**Archivos afectados:** `search_service.py`, posible migración para índice de full-text search en Postgres.

**Criterios de aceptación:**
- [ ] Una query conteniendo un identificador exacto (ej. un código o nombre propio presente literalmente en un documento) lo recupera correctamente, incluso si antes el modo semántico puro no lo priorizaba.
- [x] Una query puramente conceptual (sin términos exactos) sigue funcionando igual o mejor que antes.
- [ ] `pytest tests/ -k "hybrid_search" -v` pasa, comparando resultados de los 3 modos sobre un mismo dataset de prueba.

---

## Phase 2.3 — Metadata Filtering

**Objetivo:** permitir limitar la búsqueda por documento, idioma, categoría, fecha u otro atributo.

**Por qué importa:** No toda búsqueda debe barrer todo el corpus. Filtrar por metadata reduce ruido y es imprescindible en cualquier sistema con más de un puñado de documentos o con documentos de distintas fuentes/categorías.

**Tareas:**
1. Confirmar qué metadata ya se persiste por chunk/documento (filename, fecha de carga, etc.) y ampliar el modelo si falta algo relevante (ej. `category`, `language`).
2. Extender `search_chunks` para aceptar filtros opcionales (`document_id`, `category`, `date_range`, etc.) que se traduzcan en cláusulas `WHERE` sobre la tabla de chunks antes o después de la búsqueda vectorial (pre-filtering es preferible cuando el filtro es muy selectivo).
3. Exponer los filtros como parámetros opcionales en `/chat` y en la tool `search_documents` del agente (el LLM puede decidir pasar un filtro si el usuario lo pide explícitamente, ej. "buscá solo en el manual de X").

**Archivos afectados:** `search_service.py`, `app/agents/tools.py`, schema de metadata de documentos.

**Criterios de aceptación:**
- [ ] Una búsqueda con filtro por `document_id` solo devuelve chunks de ese documento.
- [ ] Sin filtros, el comportamiento es idéntico al actual (regression check).
- [ ] `pytest tests/ -k "metadata_filter" -v` pasa.

---

## Phase 2.4 — Re-ranking con Cross-Encoder

**Objetivo:** re-ordenar los candidatos recuperados usando un Cross-Encoder antes de construir el prompt final.

**Por qué importa:** La búsqueda vectorial (bi-encoder) compara embeddings precalculados de query y documento por separado — es rápida pero menos precisa. Un Cross-Encoder recibe la pregunta y cada documento *juntos* y calcula un score de relevancia mucho más preciso, a costa de ser más lento (por eso se aplica solo sobre un conjunto reducido de candidatos, no sobre todo el corpus).

**Tareas:**
1. Recuperar un conjunto más amplio de candidatos (ej. top-20) desde el paso de hybrid search.
2. Re-rankear con un Cross-Encoder — opciones: `sentence-transformers` `CrossEncoder` (local, gratis, ya estás usando HuggingFace embeddings así que encaja con el stack), Cohere Rerank (API paga), o Vertex AI Ranking API (si ya se integró Vertex AI en el otro roadmap).
3. Quedarse con el top-5 final tras el re-ranking para pasar al LLM.
4. Hacerlo configurable (`RERANKING_ENABLED`) para poder medir el impacto real en el framework de evaluación de la Fase 4.

**Archivos afectados:** nuevo módulo `app/services/reranker.py`, `search_service.py`.

**Criterios de aceptación:**
- [ ] Con `RERANKING_ENABLED=true`, el orden final de los top-5 documentos difiere (y mejora, verificable con el eval framework de Fase 4) respecto al orden puramente vectorial en al menos un caso de prueba diseñado para eso.
- [ ] La latencia agregada por el re-ranking queda documentada (medible con la instrumentación de Fase 6).
- [ ] `pytest tests/ -k "reranker" -v` pasa.

---

## Phase 2.5 — Context Compression

**Objetivo:** eliminar párrafos irrelevantes de los documentos recuperados antes de construir el prompt final.

**Por qué importa:** Incluso después de re-ranking, un chunk recuperado puede tener solo una oración realmente relevante entre varios párrafos de relleno. Comprimir el contexto reduce tokens (costo) y reduce la superficie donde el LLM puede "distraerse" con información irrelevante.

**Tareas:**
1. Integrar `ContextualCompressionRetriever` de LangChain (o una versión simplificada propia con un LLM barato/rápido que extraiga solo las oraciones relevantes de cada chunk dado la query).
2. Aplicarlo como paso final del pipeline, después del re-ranking, antes de construir el prompt.
3. Hacerlo configurable (`CONTEXT_COMPRESSION_ENABLED`), dado que agrega una llamada extra al LLM y por lo tanto latencia — medir el trade-off con el framework de eval y de costos.

**Archivos afectados:** `search_service.py` o un nuevo paso en el pipeline de construcción de contexto.

**Criterios de aceptación:**
- [ ] Con compresión activada, el tamaño total de tokens del contexto final es menor que sin ella, para un mismo set de documentos recuperados.
- [ ] Faithfulness/Answer Relevancy (Fase 4) no empeora al activar la compresión (idealmente mejora o se mantiene).
- [ ] `pytest tests/ -k "context_compression" -v` pasa.

---

# FASE 3 — Response Quality & Traceability

## Phase 3.1 — Structured Sources (Citations)

**Objetivo:** que `search_documents` devuelva metadata citable (filename, document_id) y que el endpoint exponga un campo `sources` separado del texto de la respuesta.

**Por qué importa:** Un RAG que no muestra de dónde salió la información es menos convincente y menos verificable que uno que sí. Muy valorado en sistemas RAG reales y muy efectivo en una demo.

**Tareas:**
1. Modificar `search_documents` para incluir `filename` y `document_id` de cada chunk en el bloque de contexto.
2. Definir schema Pydantic de respuesta con `answer: str` y `sources: list[SourceRef]`.
3. Adjuntar las fuentes efectivamente usadas a la respuesta final, independientemente de si el LLM las menciona textualmente.

**Archivos afectados:** `app/agents/tools.py`, schema de respuesta de `/agent`.

**Criterios de aceptación:**
- [ ] Una respuesta que usó `search_documents` incluye `sources` no vacío con `filename` y `document_id`.
- [ ] Una respuesta sin retrieval (saludo) devuelve `sources: []`.
- [ ] `pytest tests/ -k "agent and sources" -v` pasa.

---

## Phase 3.2 — Streaming Agent Responses

**Objetivo:** exponer `/agent` vía SSE igual que `/chat`, incluyendo eventos intermedios de tool-calling.

**Por qué importa:** UX consistente entre ambos endpoints, y exponer pasos intermedios del agente es una demo muy efectiva de "agentic workflow".

**Tareas:**
1. Reemplazar `ainvoke` por `astream_events` (API de eventos LangChain v2).
2. Mapear eventos: `on_tool_start` → `{"type": "tool_call", "tool": "..."}`; `on_chat_model_stream` → tokens de la respuesta final.
3. Adaptar el endpoint a `StreamingResponse` (`text/event-stream`), con fallback no-streaming.

**Archivos afectados:** módulo del agente, `app/api/routes/agent.py`.

**Criterios de aceptación:**
- [ ] Cliente SSE recibe eventos `tool_call` antes del evento de texto final.
- [ ] Modo no-streaming sigue funcionando igual.
- [ ] Test manual documentado con `curl -N`.

---

# FASE 4 — Evaluation Framework

## Contexto

Muy pocos proyectos personales evalúan objetivamente la calidad de un RAG — la mayoría se prueba "a ojo". En producción esto es indispensable, y es lo que permite validar objetivamente si las mejoras de la Fase 2 (hybrid search, re-ranking, compression) realmente mejoran algo, en vez de asumirlo.

## Phase 4.1 — Golden Dataset + Métricas

**Objetivo:** armar un dataset de preguntas/respuestas conocidas y calcular métricas automáticas de calidad.

**Por qué importa:** Sin un dataset de referencia no hay forma objetiva de comparar "antes vs. después" de un cambio en el pipeline.

**Tareas:**
1. Armar un dataset de 15-30 pares pregunta/respuesta-esperada sobre los documentos de prueba del proyecto (`eval/golden_dataset.json` o similar), incluyendo casos que específicamente ejercitan hybrid search (IDs, nombres propios) y casos puramente semánticos.
2. Integrar **RAGAS** (o **DeepEval** como alternativa) para calcular: Faithfulness, Context Precision, Context Recall, Answer Relevancy, Hallucination Rate.
3. Script `eval/run_eval.py` que corre el dataset completo contra el pipeline actual y genera un reporte (JSON o markdown) con las métricas agregadas.

**Archivos afectados:** nuevo directorio `eval/`.

**Criterios de aceptación:**
- [ ] `python eval/run_eval.py` corre sin errores y genera un reporte con las 5 métricas.
- [ ] El reporte incluye desglose por pregunta, no solo el promedio agregado.
- [ ] El dataset dorado está versionado en el repo.

---

## Phase 4.2 — Evaluación como Gate de Cambios

**Objetivo:** que cada mejora de pipeline (Fase 2) se valide corriendo el eval framework antes/después, dejando registro del impacto.

**Por qué importa:** Esto es lo que convierte al eval framework en algo útil día a día, no solo un script que se corre una vez.

**Tareas:**
1. Guardar reportes de eval con timestamp/git-hash en `eval/reports/`.
2. Documentar en el README un flujo simple: "antes de mergear un cambio al pipeline de retrieval, correr `run_eval.py` y comparar contra el último reporte guardado".
3. Opcional: integrar el eval run como step de CI (no bloqueante al principio, solo informativo) en el pipeline de la Fase de MLOps.

**Archivos afectados:** `eval/`, documentación.

**Criterios de aceptación:**
- [ ] Existen al menos 2 reportes históricos comparables (baseline vs. post-Fase 2) en el repo.
- [ ] El README documenta el flujo de uso del eval framework como gate de calidad.

---

## Phase 4.3 — Endpoint Interno `/internal/evaluate` (Demo)

**Objetivo:** exponer el eval framework de 4.1 también como endpoint HTTP, además del script de CI, para poder mostrarlo corriendo en vivo (por ejemplo contra el deploy en Cloud Run) en una demo o entrevista.

**Por qué importa — contexto real vs. este proyecto:** En sistemas de producción reales, la evaluación de calidad casi nunca se expone como endpoint de la API pública. Ocurre en tres momentos distintos: (1) **evaluación offline en CI/CD**, corriendo el golden dataset como *step de pipeline* antes de mergear un cambio — esto es exactamente el script de 4.1/4.2; (2) **evaluación online continua en producción**, vía sampling de tráfico real evaluado de forma asíncrona (LLM-as-judge corriendo en background, no sincrónico con la respuesta al usuario), típicamente integrada con la plataforma de observabilidad (Fase 5) más que con un endpoint propio; (3) **debugging ad-hoc**, donde alguien del equipo quiere re-correr una query puntual con otra config — acá sí aparece un endpoint o herramienta interna, pero nunca en la API pública que consumen usuarios finales, porque mezclar `/chat`/`/agent` (para usuarios) con `/evaluate` (para el equipo de desarrollo) es una señal de diseño confusa, similar a exponer `/run-unit-tests` en producción.

Para este proyecto puntual, el objetivo es de **portfolio/demo**, no reproducir el patrón de producción al pie de la letra — por eso se agrega el endpoint, pero explícitamente separado y documentado como herramienta de desarrollo expuesta por conveniencia, no como el patrón recomendado para un sistema con usuarios reales. Esa aclaración en el README es en sí misma una señal de criterio técnico ante quien revise el proyecto.

**Tareas de implementación:**
1. Nueva ruta bajo un prefijo separado del resto de la API pública, ej. `app/api/routes/internal.py` montado en `/internal/evaluate` (no `/evaluate` a secas, para que quede claro por URL que es una herramienta interna).
2. El endpoint reutiliza la misma lógica de `eval/run_eval.py` (extraer la función core a un módulo compartido, ej. `eval/evaluator.py`, que tanto el script de CLI como el endpoint importan — no duplicar lógica).
3. Parámetros de request: opcionalmente aceptar un subconjunto del golden dataset (por `id` o por tag/categoría) para poder correr una evaluación rápida sobre 2-3 preguntas puntuales en vez del dataset completo, útil para debugging ad-hoc en la demo.
4. Response: JSON con las métricas agregadas (Faithfulness, Context Precision, Context Recall, Answer Relevancy, Hallucination Rate) y el desglose por pregunta, igual que el reporte del script.
5. Dado que correr el dataset completo contra RAGAS/DeepEval puede tardar bastante (son varias llamadas a LLM por pregunta), correrlo como `BackgroundTasks` de FastAPI si se expone la opción de "dataset completo", devolviendo un `job_id` y un endpoint de polling (`/internal/evaluate/{job_id}`) — o, más simple para el alcance de este proyecto, limitar el endpoint síncrono a un subconjunto chico de preguntas y dejar el dataset completo únicamente para el script de CI.

**Consideraciones de seguridad (teoría — aplicar según el alcance real del proyecto):**

Como cualquier endpoint que expone lógica interna/de desarrollo en un servicio público, el patrón recomendado en un sistema real sería:
- **Autenticación separada de la de usuarios finales**: una API key distinta (ej. `INTERNAL_API_KEY`) exigida vía header, para que las credenciales de un usuario normal (si el proyecto llegara a tenerlas) no habiliten acceso a esta ruta, y viceversa.
- **Namespace/prefijo separado** (`/internal/*`) para poder aplicar reglas de red distintas más adelante (ej. bloquear el prefijo completo a nivel de load balancer o Cloud Run/Cloud Armor, dejándolo accesible solo desde IPs conocidas).
- **Rate limiting propio**, más agresivo que el de la API pública, dado que cada llamada a este endpoint dispara múltiples llamadas a LLM (costo real por request).
- **No loguear el contenido del golden dataset ni las respuestas evaluadas en logs compartidos** con el resto de la aplicación, si el dataset llegara a contener información sensible (no es el caso acá, pero es la práctica correcta).

**Para el alcance de este proyecto:** dado que hoy no hay un segundo mecanismo de auth implementado, es razonable no implementar API key separada ni rate limiting dedicado para esta demo puntual — el criterio más simple y suficiente es dejar el endpoint bajo el prefijo `/internal/` y documentar explícitamente en el README que en un despliegue real este namespace debería protegerse con las medidas de arriba antes de exponerlo públicamente. Si en algún momento se implementa autenticación real para el proyecto (por ejemplo al conectar un frontend), extender esa misma auth a este prefijo es la primera mejora de seguridad a aplicar, antes que cualquier otra.

**Archivos afectados:** `app/api/routes/internal.py` (nuevo), `eval/evaluator.py` (extraído de `eval/run_eval.py`), documentación.

**Criterios de aceptación:**
- [ ] `POST /internal/evaluate` con un subconjunto de preguntas devuelve las métricas en el mismo formato que el reporte del script.
- [ ] `eval/run_eval.py` (CLI) y el endpoint comparten la misma función core de evaluación, sin lógica duplicada.
- [ ] El README documenta explícitamente: (a) que este endpoint es una conveniencia de demo/portfolio, (b) cuál sería el patrón real en producción (evaluación offline en CI + sampling online vía observabilidad), y (c) qué medidas de seguridad de la lista de arriba faltan deliberadamente para el alcance actual del proyecto.
- [ ] `pytest tests/ -k "evaluate_endpoint" -v` pasa.

---

# FASE 5 — Observability

## Contexto

En un sistema real no alcanza con `print`/logs sueltos — hace falta poder inspeccionar exactamente qué hizo el sistema para responder una pregunta puntual: qué se recuperó, qué prompt se envió, cuánto tardó cada etapa, qué tools se llamaron.

## Phase 5.1 — Integración con LangSmith (o Langfuse)

**Objetivo:** trazar automáticamente cada ejecución del agente y del pipeline RAG.

**Por qué importa:** LangSmith (de LangChain, más simple de integrar dado el stack actual) registra automáticamente prompts, documentos recuperados, tiempos, tokens, costo estimado, tool calls y errores, sin instrumentación manual extensa. **Langfuse** es la alternativa open-source si se prefiere no depender de un servicio propietario o se quiere self-host.

**Tareas:**
1. Configurar variables de entorno de LangSmith (`LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`).
2. Confirmar que tanto `/chat` como `/agent` (incluyendo los nuevos pasos de la Fase 2: rewriter, hybrid search, reranker, compression) aparecen trazados como un run jerárquico único por request, no como llamadas sueltas desconectadas.
3. Documentar en el README cómo acceder a las trazas (con capturas de pantalla — buen material para portfolio).
4. Evaluar Langfuse como alternativa si se prioriza self-hosting; no es necesario implementar ambos, elegir uno.

**Archivos afectados:** configuración (env vars), sin necesariamente tocar lógica de negocio si LangChain instrumenta automáticamente.

**Criterios de aceptación:**
- [ ] Una request a `/agent` genera un trace visible en LangSmith/Langfuse con todas las etapas del pipeline desglosadas (rewriter → hybrid search → rerank → compression → LLM final).
- [ ] Los tool calls del agente aparecen claramente identificados dentro del trace.
- [ ] README actualizado con instrucciones de acceso a las trazas.

---

# FASE 6 — Cost & Performance Monitoring

## Contexto

Sin medir tokens, latencia y costo por request, es imposible responder preguntas operativas básicas: ¿cuánto cuesta en promedio una conversación?, ¿qué tan rápido responde el sistema?, ¿qué etapa del pipeline es el cuello de botella? Esta fase se apoya en la instrumentación de Fase 5, pero agrega registro persistente y consultable, no solo trazas efímeras.

## Phase 6.1 — Registro de Tokens y Costo por Request

**Objetivo:** registrar, para cada conversación/request, modelo usado, tokens de entrada, tokens de salida, y costo estimado.

**Por qué importa:** Es la base de cualquier decisión de optimización de costo (incluida la Fase 7, model routing). Sin esto, "optimizar costos" es una afirmación sin datos.

**Tareas:**
1. Extraer el conteo de tokens de la respuesta del provider (Gemini expone `usage_metadata`; para Ollama puede requerir un tokenizer local aproximado).
2. Persistir por request: `model`, `input_tokens`, `output_tokens`, `estimated_cost_usd`, `endpoint` (`/chat` o `/agent`), timestamp.
3. Tabla nueva (`request_metrics` o similar) vía migración, o reutilizar la tabla de historial de conversación si ya existe un lugar natural para adjuntar esta metadata.

**Archivos afectados:** capa de servicio compartida entre `/chat` y `/agent`, nueva migración.

**Criterios de aceptación:**
- [ ] Cada request a `/chat` o `/agent` persiste sus métricas de tokens/costo correctamente.
- [ ] Es posible calcular el costo promedio por conversación con una query simple sobre la tabla.
- [ ] `pytest tests/ -k "token_tracking" -v` pasa.

---

## Phase 6.2 — Latencia Desglosada por Etapa

**Objetivo:** medir tiempo hasta el primer token (TTFT), latencia total, y tiempo por etapa del pipeline (embedding, hybrid search, rerank, compression, LLM call).

**Por qué importa:** Permite identificar cuellos de botella reales en vez de asumirlos. Por ejemplo, confirmar si el re-ranking de la Fase 2.4 agrega latencia significativa respecto al beneficio de calidad que aporta.

**Tareas:**
1. Instrumentar cada etapa del pipeline con timers simples (o aprovechar los spans que ya expone LangSmith de la Fase 5, si el desglose que da es suficiente).
2. Persistir junto con el registro de tokens de Fase 6.1, o exponerlo únicamente vía las trazas de LangSmith si se considera redundante mantenerlo en dos lugares.
3. Documentar cuál de las dos fuentes (tabla propia vs. LangSmith) es la fuente de verdad para evitar duplicación de esfuerzo.

**Archivos afectados:** pipeline de `search_service`, capa compartida de request handling.

**Criterios de aceptación:**
- [ ] Es posible obtener, para una request dada, el tiempo consumido en cada etapa del pipeline.
- [ ] El TTFT se mide específicamente para el modo streaming (`/chat`, y `/agent` tras Fase 3.2).

---

## Phase 6.3 — Reporte / Dashboard Simple

**Objetivo:** poder responder preguntas agregadas: costo promedio por conversación, tiempo promedio de retrieval, latencia comparada entre modelos.

**Por qué importa:** Convierte los datos crudos de 6.1/6.2 en algo accionable y presentable — buen material visual para portfolio.

**Tareas:**
1. Endpoint interno simple (`/metrics/summary`) o un notebook/script que agregue la tabla de `request_metrics` en estadísticas básicas (promedio, p95, por modelo, por endpoint).
2. Opcional: visualización simple (un notebook con matplotlib, o un dashboard liviano) — no es necesario Grafana/Prometheus completo para un proyecto de este tamaño, salvo que se quiera explícitamente esa experiencia.

**Archivos afectados:** nuevo endpoint o script de análisis.

**Criterios de aceptación:**
- [ ] Es posible obtener costo promedio, latencia promedio y P95 de latencia con una sola llamada/script.
- [ ] El reporte diferencia por modelo y por endpoint.

---

# FASE 7 — LLM Optimization

## Contexto

Con evaluación (Fase 4), observabilidad (Fase 5) y métricas de costo/latencia (Fase 6) ya en pie, esta fase usa esos datos para optimizar el sistema con evidencia, no por intuición.

## Phase 7.1 — Model Routing

**Objetivo:** usar un modelo más barato/rápido (ej. Gemini Flash) para preguntas simples, y reservar el modelo más caro (ej. Gemini Pro) para consultas que requieren razonamiento complejo.

**Por qué importa:** Reduce costo significativamente sin sacrificar calidad en la mayoría de las queries, que suelen ser simples. Es una optimización estándar en sistemas LLM de producción.

**Tareas:**
1. Definir un criterio de enrutamiento: puede ser heurístico simple (longitud de la query, presencia de palabras clave de razonamiento) o un clasificador barato (un LLM chico decidiendo "simple" vs "complejo").
2. Integrar el router en la factory de provider de la Fase 1.1, de forma que sea transparente para el resto del sistema.
3. Medir el impacto en costo (Fase 6.1) y en calidad (Fase 4) antes/después de activar el routing — el objetivo es reducir costo sin degradar Faithfulness/Answer Relevancy de forma significativa.

**Archivos afectados:** módulo de provider/LLM, posible nuevo módulo `app/services/model_router.py`.

**Criterios de aceptación:**
- [ ] Queries simples (saludo, pregunta de conteo) se enrutan al modelo más barato, verificable en los logs/traces.
- [ ] Queries complejas se enrutan al modelo más capaz.
- [ ] El eval framework (Fase 4) confirma que la calidad no se degrada significativamente tras activar el routing.
- [ ] El costo promedio por conversación (Fase 6.1) baja de forma medible.

---

## Phase 7.2 — Prompt Versioning

**Objetivo:** versionar los prompts del sistema (system prompts de `/chat` y `/agent`, prompt del rewriter, etc.) y poder comparar variantes.

**Por qué importa:** Los prompts evolucionan constantemente en producción. Sin versionado, es imposible saber qué versión de prompt generó qué resultado, ni comparar objetivamente si un cambio de prompt mejoró o empeoró la calidad.

**Tareas:**
1. Extraer todos los prompts hardcodeados a un módulo/config versionado (`app/prompts/` con un identificador de versión por prompt, ej. `agent_system_v1`, `agent_system_v2`).
2. Registrar en las métricas/traces qué versión de prompt se usó en cada request.
3. Correr el eval framework (Fase 4) comparando versiones de prompt sobre el mismo golden dataset antes de promover una nueva versión a default.

**Archivos afectados:** nuevo módulo `app/prompts/`, integración con Fase 4 y Fase 5.

**Criterios de aceptación:**
- [ ] Existen al menos 2 versiones registradas de al menos un prompt (ej. system prompt del agente).
- [ ] El eval framework puede correrse contra ambas versiones y comparar métricas.
- [ ] Las trazas de LangSmith muestran qué versión de prompt se usó por request.

---

## Phase 7.3 — Semantic Cache

**Objetivo:** cachear respuestas basándose en similitud semántica de la query, no solo en coincidencia exacta.

**Por qué importa:** Reduce costo y latencia para preguntas parecidas (no idénticas) a otras ya respondidas — muy común en un chatbot donde distintos usuarios (o el mismo usuario) preguntan variantes de lo mismo.

**Tareas:**
1. Al recibir una query, generar su embedding y buscar en una tabla/índice de queries previas ya respondidas (puede reutilizar pgvector para esto, con una tabla separada `query_cache`).
2. Definir un umbral de similitud (ej. cosine similarity > 0.95) por debajo del cual no se considera cache hit.
3. Si hay hit, devolver la respuesta cacheada (marcándolo explícitamente en la respuesta o en logs, para transparencia) sin llamar al LLM. Si no hay hit, proceder normal y guardar la nueva query+respuesta en el cache.
4. Definir política de invalidación (TTL, o invalidar cuando se sube/borra un documento relevante — al menos documentar la limitación si no se implementa invalidación fina).

**Archivos afectados:** nuevo módulo `app/services/semantic_cache.py`, nueva tabla.

**Criterios de aceptación:**
- [ ] Dos queries semánticamente equivalentes pero con distinta redacción generan un cache hit en la segunda.
- [ ] Una query claramente distinta no genera un falso positivo de cache.
- [ ] El ahorro de costo/latencia por cache hits es medible vía Fase 6.
- [ ] `pytest tests/ -k "semantic_cache" -v` pasa.

---

# FASE 8 — Testing Integral

## Phase 8.1 — Agent Routing Tests

**Objetivo:** validar que el agente elige la tool correcta según el tipo de pregunta.

**Por qué importa:** La parte más difícil de testear en sistemas agenticos es la decisión, no la ejecución.

**Tareas:**
1. Tests que verifiquen: pregunta de contenido → `search_documents`; pregunta de cantidad → `count_documents`; saludo → ninguna tool.
2. Usar `return_intermediate_steps=True` en el executor de test.
3. Documentar en el README de tests que son tests de comportamiento, distintos de los funcionales.

**Archivos afectados:** `tests/test_agent.py`.

**Criterios de aceptación:**
- [ ] Al menos 3 tests cubriendo los 3 casos de routing.
- [ ] `pytest tests/test_agent.py -v` pasa consistentemente (no flaky).

---

## Phase 8.2 — Retrieval Pipeline Tests

**Objetivo:** validar cada etapa nueva del pipeline de retrieval (Fase 2) de forma aislada.

**Por qué importa:** Un pipeline con 5 etapas nuevas (rewriter, hybrid search, filtering, reranking, compression) necesita tests unitarios por etapa, no solo un test end-to-end, para poder aislar regresiones.

**Tareas:**
1. Test unitario por etapa, con inputs/outputs controlados (mockeando el LLM donde aplique).
2. Al menos un test end-to-end que verifique que el pipeline completo (todas las etapas encadenadas) produce un resultado razonable sobre el golden dataset de Fase 4.

**Archivos afectados:** `tests/test_retrieval_pipeline.py`.

**Criterios de aceptación:**
- [ ] Cada etapa de Fase 2 tiene al menos un test unitario.
- [ ] Existe un test end-to-end del pipeline completo.
- [ ] `pytest tests/test_retrieval_pipeline.py -v` pasa.

---

## Orden de ejecución recomendado

```
Fase 1 (estabilidad base):       1.1 → 1.2 → 1.3 → 1.4
Fase 2 (calidad de retrieval):   2.1 → 2.1b → 2.2 → 2.3 → 2.4 → 2.5
Fase 3 (calidad de respuesta):   3.1 → 3.2
Fase 4 (medición objetiva):      4.1 → 4.2 → 4.3
Fase 5 (observabilidad):         5.1
Fase 6 (costo/performance):      6.1 → 6.2 → 6.3
Fase 7 (optimización):           7.1 → 7.2 → 7.3
Fase 8 (testing integral):       8.1 → 8.2 (en paralelo con el resto, a medida que cada fase se completa)
```

**Nota sobre Fase 8:** en la práctica, los tests de cada fase (8.1, 8.2) deberían escribirse junto con cada fase correspondiente, no como un bloque final aislado. Se lista al final del documento por claridad organizativa, pero el agente ejecutor debe escribir los tests de cada etapa de Fase 2 en el momento de implementarla, no posponerlo.

**Nota sobre orden Fase 4 vs Fase 2:** el golden dataset y el framework de evaluación (Fase 4) pueden armarse en paralelo con Fase 2, o incluso antes — tener el framework de eval listo *antes* de las mejoras de retrieval permite medir el "baseline" real y cuantificar el impacto de cada cambio, en vez de evaluar todo retroactivamente. Si el tiempo lo permite, se recomienda adelantar 4.1 antes de arrancar Fase 2.
