# Stress test del CAG: dónde rompe

Corrida del 17/11 contra el servicio real (`gpt-4o-mini`, OpenAI, sin fallback), con `MAX_TURNS=6`, anclas por regex, resumen acumulativo, caché exacta y caché semántica (umbral 0,92). 200 filas en `results.csv`; costó USD 0,21 en total.

```bash
uv run python -m evals.stress.run --http http://localhost:8000 \
    --scenarios growing,pivot,contradiction --attachment-sizes 0,5,20,50,100 \
    --repeats 3 --output evals/stress/results.csv
uv run python -m evals.stress.report evals/stress/results.csv   # estas tablas
```

**Cómo medí.** Cada escenario es una conversación de 20 turnos; N ∈ {1, 3, 6, 10, 20} se lee en esos cortes, así una sesión da las cinco mediciones. Cada repetición lleva una marca distinta en el texto para que la caché exacta no conteste por ella. El `turn_observed` lo leo de `GET /sessions/{id}` (va embebido en la respuesta) en lugar de parsear logs: es la misma información y el runner no depende de Docker. Las métricas nuevas viven en `evals/stress/metrics.py` y no en `evals/metrics.py` porque evalúan otra cosa (la observación de un turno o el snapshot de la sesión, no el texto de una estimación contra un caso golden); comparten `MetricResult`.

**Presupuestos** (fijados antes de medir): latencia 10.000 ms por turno, coste USD 0,003 por turno.

**Recall.** Para cada hecho declarado en el turno k miro en el turno N si el modelo todavía lo puede ver: o el turno k sigue en la ventana (textual), o el hecho aparece literal en el resumen, las anclas o el metadata (`MemoryDriftMetric`). "Recall solo memoria" cuenta solo lo segundo.

## Tabla resumen

Latencias sobre turnos en frío (sin acierto de caché). El recall de las filas `attachment` es la fracción de los 3 requisitos plantados en el PDF (al 5%, 50% y 95% del texto) que aparecen en la respuesta.

| Escenario | Adjunto (KB) | Turnos | P50 latencia (ms) | P95 latencia (ms) | Coste total (USD) | Caché exacta | Caché semántica | Recall medio |
|---|---|---|---|---|---|---|---|---|
| growing | 0 | 60 | 8690 | 12347 | 0.0594 | 0% | 3% | 0.94 |
| contradiction | 0 | 60 | 8687 | 13672 | 0.0686 | 0% | 3% | 1.00 |
| pivot | 0 | 60 | 10514 | 14273 | 0.0730 | 0% | 3% | 1.00 |
| attachment | 0 | 3 | 5784 | 5784 | 0.0005 | 67% | 0% | n/a |
| attachment | 5 | 3 | 7876 | 7876 | 0.0010 | 67% | 0% | 0.67 |
| attachment | 20 | 3 | 6226 | 6226 | 0.0011 | 67% | 0% | 0.67 |
| attachment | 50 | 3 | 407 | 2633 | 0.0008 | 0% | 100% | 0.67 |
| attachment | 100 | 3 | 418 | 2553 | 0.0008 | 0% | 100% | 0.67 |
| attachment_cold | 0 | 1 | 5322 | 5322 | 0.0005 | 0% | 0% | n/a |
| attachment_cold | 5 | 1 | 7273 | 7273 | 0.0009 | 0% | 0% | 0.67 |
| attachment_cold | 20 | 1 | 7231 | 7231 | 0.0013 | 0% | 0% | 0.67 |
| attachment_cold | 50 | 1 | 7438 | 7438 | 0.0015 | 0% | 0% | 0.33 |
| attachment_cold | 100 | 1 | 5300 | 5300 | 0.0017 | 0% | 0% | 0.33 |

## Curva 1: latencia vs tokens

| tokens_in del turno | Turnos | Latencia media (ms) | P95 (ms) | tokens_out medio |
|---|---|---|---|---|
| 0k a 3k | 8 | 5062 | 5784 | 333 |
| 3k a 4k | 26 | 5195 | 5829 | 393 |
| 4k a 5k | 18 | 6366 | 8343 | 480 |
| 5k a 6k | 54 | 8936 | 11703 | 628 |
| 6k a 8k | 61 | 10865 | 15530 | 825 |
| más de 8k | 15 | 11115 | 17402 | 922 |

## Curva 2: coste acumulado vs turno

Media de las 3 repeticiones.

| Escenario | Turno | tokens_in | Coste del turno (USD) | vs turno 1 | Coste acumulado (USD) |
|---|---|---|---|---|---|
| growing | 1 | 1281 | 0.00023 | x1.0 | 0.0002 |
| growing | 3 | 3297 | 0.00063 | x2.7 | 0.0014 |
| growing | 6 | 4310 | 0.00077 | x3.3 | 0.0036 |
| growing | 10 | 5421 | 0.00107 | x4.6 | 0.0078 |
| growing | 20 | 6294 | 0.00156 | x6.7 | 0.0198 |
| contradiction | 1 | 1303 | 0.00024 | x1.0 | 0.0002 |
| contradiction | 3 | 3477 | 0.00065 | x2.8 | 0.0015 |
| contradiction | 6 | 4779 | 0.00094 | x4.0 | 0.0039 |
| contradiction | 10 | 6415 | 0.00130 | x5.5 | 0.0086 |
| contradiction | 20 | 7195 | 0.00152 | x6.4 | 0.0229 |
| pivot | 1 | 1330 | 0.00030 | x1.0 | 0.0003 |
| pivot | 3 | 3533 | 0.00071 | x2.4 | 0.0016 |
| pivot | 6 | 4783 | 0.00093 | x3.1 | 0.0042 |
| pivot | 10 | 6271 | 0.00135 | x4.5 | 0.0091 |
| pivot | 20 | 7737 | 0.00171 | x5.7 | 0.0243 |

## Curva 3: recall vs N

| Escenario | N (turnos) | Hechos declarados | Recall visible | Recall solo memoria | En resumen | En anclas | En metadata | Hechos viejos presentes | project_name ok |
|---|---|---|---|---|---|---|---|---|---|
| growing | 1 | 1 | 1.00 | 1.00 | 0.0 | 0.0 | 1.0 | 0.0 | 100% |
| growing | 3 | 3 | 1.00 | 0.89 | 0.0 | 0.0 | 2.7 | 0.0 | 100% |
| growing | 6 | 6 | 1.00 | 0.89 | 0.0 | 0.0 | 5.3 | 0.0 | 100% |
| growing | 10 | 9 | 0.96 | 0.85 | 2.7 | 0.0 | 6.7 | 0.0 | 100% |
| growing | 20 | 14 | 0.74 | 0.74 | 4.7 | 0.0 | 9.3 | 0.0 | 100% |
| contradiction | 1 | 1 | 1.00 | 1.00 | 0.0 | 0.0 | 1.0 | 0.0 | 100% |
| contradiction | 3 | 3 | 1.00 | 0.78 | 0.0 | 0.0 | 2.3 | 0.0 | 100% |
| contradiction | 6 | 3 | 1.00 | 0.78 | 0.0 | 0.0 | 2.3 | 0.0 | 100% |
| contradiction | 10 | 4 | 1.00 | 0.75 | 2.0 | 1.0 | 2.0 | 1.0 | 100% |
| contradiction | 20 | 6 | 1.00 | 1.00 | 1.7 | 2.0 | 4.0 | 1.0 | 100% |
| pivot | 1 | 1 | 1.00 | 1.00 | 0.0 | 0.0 | 1.0 | 0.0 | 100% |
| pivot | 3 | 3 | 1.00 | 1.00 | 0.0 | 0.0 | 3.0 | 0.0 | 100% |
| pivot | 6 | 4 | 1.00 | 1.00 | 0.0 | 0.0 | 4.0 | 1.0 | 100% |
| pivot | 10 | 6 | 1.00 | 1.00 | 2.7 | 0.0 | 6.0 | 1.0 | 100% |
| pivot | 20 | 7 | 1.00 | 1.00 | 5.0 | 0.0 | 6.7 | 1.0 | 100% |

## Adjuntos

`attachment` es la corrida original; `attachment_cold` repite un turno por tamaño con la caché semántica apagada (ver lectura).

| Corrida | Adjunto (KB) | Caracteres al prompt | tokens_in (en frío) | Latencia en frío (ms) | Coste en frío (USD) | Recall del adjunto | Truncado | Caché por repetición |
|---|---|---|---|---|---|---|---|---|
| attachment | 0 | 0 | 2661 | 5784 | 0.00048 | n/a | no | none, exact, exact |
| attachment | 5 | 5018 | 4964 | 7876 | 0.00099 | 0.67 | no | none, exact, exact |
| attachment | 20 | 20000 | 10751 | 6226 | 0.00112 | 0.67 | sí | none, exact, exact |
| attachment | 50 | 20000 | 4702 | 2633 | 0.00076 | 0.67 | sí | semantic, semantic, semantic |
| attachment | 100 | 20000 | 4702 | 2553 | 0.00076 | 0.67 | sí | semantic, semantic, semantic |
| attachment_cold | 0 | 0 | 2651 | 5322 | 0.00048 | n/a | no | none |
| attachment_cold | 5 | 5018 | 4984 | 7273 | 0.00085 | 0.67 | no | none |
| attachment_cold | 20 | 20000 | 10962 | 7231 | 0.00127 | 0.67 | sí | none |
| attachment_cold | 50 | 20000 | 10915 | 7438 | 0.00155 | 0.33 | sí | none |
| attachment_cold | 100 | 20000 | 10709 | 5300 | 0.00171 | 0.33 | sí | none |

## Presupuestos

| Escenario | Turnos en frío | Dentro de latencia | Dentro de coste | Primer turno fuera de latencia |
|---|---|---|---|---|
| growing | 58 | 79% | 100% | 11 |
| contradiction | 58 | 78% | 100% | 10 |
| pivot | 58 | 48% | 100% | 9 |
| attachment | 3 | 100% | 100% | ninguno |
| attachment_cold | 5 | 100% | 100% | ninguno |

## Dónde empieza a romperse mi CAG y por qué

Lo primero que rompe es la **latencia**, no el coste ni la memoria. El turno 1 tarda unos 5,3 s y el turno 20 entre 8,4 y 15,5 s; el SLA de 10 s se rompe por primera vez entre los turnos 9 y 11 según el escenario, y en `pivot` solo el 48% de los turnos queda dentro. La curva 1 muestra que la latencia sube con los tokens de entrada (5,2 s por debajo de 4k, 12,2 s por encima de 8k), pero el que la empuja es la salida: con cada requisito nuevo la estimación es más larga (de 327 a 1.012 tokens de salida), y en este modelo generar cuesta mucho más tiempo que leer. El **coste**, en cambio, no es problema a esta escala: el turno 20 cuesta entre 5,7 y 6,7 veces el turno 1, pero son USD 0,0017 y nunca pasó el presupuesto; la ventana funciona, porque entre el turno 10 y el 20 los tokens de entrada crecen solo entre un 12% y un 23% en lugar de duplicarse. La **memoria** degrada en silencio, sin ningún error: en `growing` el recall de hechos visibles baja a 0,96 en N=10 y a 0,74 en N=20 (en promedio se pierden casi 4 de 14 requisitos), y ningún test se pone rojo. El nombre del proyecto no se perdió nunca porque vive en el metadata. Y los hechos viejos tampoco se van cuando deberían: en `pivot`, "React" sigue en la memoria del turno 6 al 20 después del cambio a Flutter, porque las tecnologías se acumulan; en `contradiction` los dos presupuestos (30.000 y 80.000 EUR) quedan promovidos a anclas y conviven hasta el final, y es el prompt el que tiene que decidir cuál vale.

Lo que más me sorprendió fueron los **adjuntos**. Más allá de 20.000 caracteres el extractor trunca y nada lo avisa salvo un flag: el PDF de 50 KB pierde el 60% del texto y el de 100 KB el 80%, y por eso el requisito plantado al 95% del documento no aparece nunca (recall 0,33 en 50 y 100 KB). El del medio (SEPA) tampoco aparece en ningún tamaño, ni siquiera con el texto completo de 5 KB: el modelo recoge el principio y el final del documento y pierde el medio. Peor: en la corrida original los PDF de 50 y 100 KB salieron de la **caché semántica** con la respuesta del de 20 KB, porque después de truncar los tres prompts quedan casi iguales (similitud por encima de 0,92 y mismo bucket). Es un falso acierto silencioso: el usuario recibe la estimación de otro documento. Por eso repetí esos tamaños con la caché semántica apagada (`attachment_cold`). Para mí el caso que justifica pasar a RAG es este: documentación de más de 20.000 caracteres (unas 3.000 palabras, 8 páginas), o proyectos que acumulan más de 10 requisitos en la conversación. En los dos casos el CAG no falla duro, recorta: o trunca el adjunto o resume requisitos hasta perderlos. RAG permitiría traer solo los fragmentos relevantes del documento completo en lugar de los primeros 20.000 caracteres.

## Limitaciones de la medición

- 3 repeticiones por escenario: los P95 salen de pocas muestras.
- El recall es por match literal, a propósito: si el resumen reescribe "Keycloak" como "SSO", cuenta como pérdida.
- El primer turno de las repeticiones 2 y 3 salió de la caché semántica (el texto cambia solo en la marca de repetición); esos turnos no entran en las latencias en frío.
- No medí si la respuesta final de `contradiction` usa el presupuesto correcto: solo qué hechos quedan en la memoria.
