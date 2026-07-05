---
name: implement-agent-roadmap-phase
description: Use this skill when the user asks to implement, work on, continue, or advance the agent improvement roadmap — e.g. "implementá la siguiente fase del roadmap del agente", "seguí con el retrieval pipeline", "avanzá con hybrid search", "trabajá en el eval framework", "agregá observabilidad con LangSmith", "implementá model routing", "continuá con AGENT_IMPROVEMENT_ROADMAP". Also matches requests referencing query rewriting, BM25, re-ranking, context compression, RAGAS/DeepEval, token tracking, semantic cache, or prompt versioning when tied to this project's roadmap.
---

# Implement Agent Roadmap Phase

Este skill ejecuta, de forma autónoma, la siguiente fase pendiente definida en `context/AGENT_IMPROVEMENT_ROADMAP.md`.

## Flujo de ejecución

1. **Leer el roadmap completo.** Abrir `context/AGENT_IMPROVEMENT_ROADMAP.md` en su totalidad antes de tocar código. No asumir el contenido de una fase por su título — los detalles de tareas y criterios de aceptación están en el cuerpo de cada sección.

2. **Determinar el estado actual del proyecto.** Recorrer las fases en el orden recomendado al final del documento (Fase 1 → 8) y, para cada sub-fase, verificar si sus criterios de aceptación ya están satisfechos inspeccionando el código real, no confiando en checkboxes desactualizados. La primera sub-fase con al menos un criterio no cumplido es la que corresponde ejecutar.

3. **Respetar las dependencias explícitas:**
   - Fase 1.4 (memoria conversacional) está bloqueada hasta que la estrategia base de `context/MEMORY_LAYER_PLAN.md` esté implementada. Si se detecta el bloqueo, reportarlo y pasar a la siguiente sub-fase no bloqueada, o preguntar al usuario cómo priorizar.
   - Fase 2 (retrieval pipeline) asume que Fase 1 completa está resuelta — no construir sobre un agente sin guardrails ni error handling.
   - Fase 4.1 (golden dataset + eval framework) puede adelantarse antes de Fase 2 si el usuario lo pide explícitamente, tal como sugiere la nota final del documento, para poder medir el baseline antes de las mejoras de retrieval.
   - Fase 7 (optimización: model routing, prompt versioning, semantic cache) asume que Fase 4 (evaluación) y Fase 6 (costo/performance) ya están en pie, porque cada optimización de esta fase debe validarse con datos, no por intuición. Si se pide ejecutar Fase 7 sin esa base, advertir al usuario antes de proceder.

4. **Implementar únicamente el alcance de la sub-fase identificada.** No adelantar tareas de fases posteriores. Ante una decisión de diseño no especificada, tomar la opción más simple y consistente con el resto del proyecto, dejando constancia en un comentario o docstring — no expandir el alcance para "mejorar" algo no pedido.

5. **Escribir los tests de la sub-fase junto con su implementación**, no posponerlos a la Fase 8. El documento aclara esto explícitamente: Fase 8 es un resumen organizativo, no un bloque de trabajo aislado al final.

6. **Seguir los patrones ya establecidos en el proyecto**, según `AGENTS.md`: composición sobre herencia, estrategias con passthrough seguro, abstracción de provider vía env var, y separación entre `context/` (specs activas) y `docs/` (referencia).

7. **Cuando la sub-fase introduzca una decisión técnica con alternativas explícitas en el documento** (por ejemplo: `rank_bm25` vs. full-text search de Postgres en Fase 2.2, o LangSmith vs. Langfuse en Fase 5.1), seguir la recomendación indicada en el propio documento salvo que el usuario pida explícitamente la alternativa.

8. **Validar contra los criterios de aceptación de la sub-fase**, ejecutando los comandos de test indicados (`pytest tests/ -k "..."`). Si un criterio requiere medición externa (ej. comparar métricas de eval antes/después, o revisar un trace en LangSmith), dejarlo señalado como pendiente de verificación manual en el reporte, no marcarlo como cumplido sin evidencia.

9. **Actualizar los checkboxes de la sub-fase completada** en `context/AGENT_IMPROVEMENT_ROADMAP.md`, sin modificar el resto del documento.

10. **Reportar al final de la ejecución:**
    - Qué sub-fase se implementó.
    - Qué archivos se crearon o modificaron.
    - Qué criterios de aceptación pasaron, con el output relevante del comando de verificación.
    - Qué queda pendiente de verificación manual, si aplica.
    - Cuál es la siguiente sub-fase a ejecutar.

## Qué NO hacer

- No ejecutar más de una sub-fase por invocación del skill, salvo que el usuario lo pida explícitamente.
- No instalar ni activar dependencias externas con costo (Cohere Rerank, LangSmith de pago, etc.) sin confirmar con el usuario — preferir siempre la alternativa gratuita/local indicada en el documento (ej. `sentence-transformers` CrossEncoder en vez de Cohere Rerank) salvo pedido explícito.
- No introducir Grafana/Prometheus u otra infraestructura de monitoreo pesada en Fase 6.3 sin que el usuario lo pida — el documento sugiere explícitamente empezar con algo simple.
- No reordenar ni reescribir fases del roadmap; el documento es la fuente de verdad y solo se actualiza para marcar progreso.
