"""Conversaciones sintéticas para estresar la memoria del estimador.

Cada escenario es una lista de turnos `(turn_index, transcript, fact)`. El
`fact` (o None) es un texto corto y literal que los turnos posteriores
deberían seguir recordando; `MemoryDriftMetric` lo busca tal cual en el resumen,
las anclas y el metadata. `stale` lista hechos que a partir de cierto turno
deberían haber DESAPARECIDO (porque el cliente los cambió).

Para medir N turnos se corre el escenario de 20 y se mira el turno N.
"""

from dataclasses import dataclass, field


@dataclass
class Turn:
    turn_index: int
    transcript: str
    fact: str | None = None


@dataclass
class Scenario:
    name: str
    project_type: str
    project_name: str
    turns: list[Turn]
    stale: list[tuple[int, str]] = field(default_factory=list)  # (desde qué turno, hecho)


def _turns(items: list[tuple[str, str | None]]) -> list[Turn]:
    return [Turn(i, text, fact) for i, (text, fact) in enumerate(items, start=1)]


# 1. Proyecto que crece: cada turno suma un requisito coherente.
GROWING = Scenario(
    name="growing",
    project_type="web_saas",
    project_name="Nimbus",
    turns=_turns([
        ("Reunión inicial. El proyecto se llama Nimbus: una plataforma web para que consultoras gestionen sus proyectos y horas. Empezamos con alta de proyectos, tareas y carga de horas.", "Nimbus"),
        ("Para el login quieren SSO con Keycloak, nada de usuarios y contraseñas propios.", "Keycloak"),
        ("Tiene que ser multi-tenant: cada consultora ve solo sus datos.", "multi-tenant"),
        ("Suman un audit log: quién cambió qué y cuándo, consultable por el administrador.", "audit log"),
        ("Necesitan exportar las horas a CSV para pasarlas a facturación.", "CSV"),
        ("La facturación la quieren integrada con Holded, que es lo que usan hoy.", "Holded"),
        ("Agregan notificaciones por email cuando una tarea se pasa de las horas estimadas.", None),
        ("Quieren un panel de reportes embebido hecho con Metabase.", "Metabase"),
        ("Piden una API pública con rate limiting para que sus clientes consulten el avance.", "rate limiting"),
        ("La interfaz tiene que estar en español y en portugués.", "portugués"),
        ("Suman un tablero kanban para las tareas, con arrastrar y soltar.", None),
        ("Necesitan importar proyectos existentes desde Jira.", "Jira"),
        ("Quieren adjuntar archivos a las tareas, guardados en S3.", "S3"),
        ("Agregan aprobación de horas por parte del jefe de proyecto antes de facturar.", None),
        ("Piden una app móvil sencilla solo para cargar horas, hecha con React Native.", "React Native"),
        ("Quieren recordatorios semanales por Slack a quien no cargó horas.", "Slack"),
        ("Suman plantillas de proyecto para no arrancar de cero cada vez.", None),
        ("Necesitan un calendario de vacaciones que descuente capacidad del equipo.", None),
        ("Piden búsqueda global con Elasticsearch sobre proyectos, tareas y comentarios.", "Elasticsearch"),
        ("Último ajuste: recalculá la estimación completa con todo lo que fuimos sumando y decime el total.", None),
    ]),
)

# 2. Proyecto que pivota: en el turno 5 cambia el stack de React a Flutter.
PIVOT = Scenario(
    name="pivot",
    project_type="mobile_app",
    project_name="Rumbo",
    turns=_turns([
        ("Reunión inicial. El proyecto se llama Rumbo: una app para que repartidores vean sus rutas del día y marquen entregas. La idea es hacerla como web app con React.", "Rumbo"),
        ("El backend lo quieren en Node.js con PostgreSQL.", "PostgreSQL"),
        ("Necesitan mapas con las rutas, usando Mapbox.", "Mapbox"),
        ("Cada entrega se confirma con una foto y la firma del cliente.", None),
        ("Cambio importante: descartamos React. Los repartidores necesitan modo offline y GPS en segundo plano, así que la app se hace nativa con Flutter.", "Flutter"),
        ("Con el cambio, las fotos se guardan en el teléfono y se sincronizan cuando hay señal.", None),
        ("Suman notificaciones push cuando se reasigna una ruta.", None),
        ("Quieren un panel web para el coordinador, con las rutas en tiempo real.", None),
        ("El panel tiene que exportar el reporte diario a Excel.", "Excel"),
        ("Necesitan login con número de teléfono y código por SMS, con Twilio.", "Twilio"),
        ("Agregan optimización del orden de las paradas.", None),
        ("Quieren que el cliente final reciba un link para seguir su entrega.", None),
        ("Suman un chat simple entre repartidor y coordinador.", None),
        ("Piden registrar incidencias: cliente ausente, dirección incorrecta, paquete dañado.", None),
        ("Necesitan integrarse con el sistema de pedidos que ya tienen en SAP.", "SAP"),
        ("Quieren métricas por repartidor: entregas por hora y porcentaje de incidencias.", None),
        ("Agregan soporte para tablets además de teléfonos.", None),
        ("Piden un modo de entrenamiento con datos de prueba para repartidores nuevos.", None),
        ("Suman lectura de códigos de barras para confirmar el paquete.", None),
        ("Último ajuste: recalculá la estimación completa con el stack actual y decime el total.", None),
    ]),
    stale=[(5, "React")],
)

# 3. Proyecto que se contradice: presupuesto 30.000 EUR en el turno 3, 80.000 EUR en el 8.
CONTRADICTION = Scenario(
    name="contradiction",
    project_type="internal_tool",
    project_name="Atlas",
    turns=_turns([
        ("Reunión inicial. El proyecto se llama Atlas: una herramienta interna para que el equipo de compras gestione proveedores y órdenes de compra.", "Atlas"),
        ("Tiene que integrarse con el ERP actual, que es Odoo.", "Odoo"),
        ("Dato clave: el presupuesto queda cerrado en 30.000 EUR, no hay más.", "30.000 EUR"),
        ("Necesitan un flujo de aprobación de órdenes según el monto.", None),
        ("Suman un catálogo de proveedores con su documentación y vencimientos.", None),
        ("Quieren alertas cuando un contrato con un proveedor está por vencer.", None),
        ("Piden comparar cotizaciones de varios proveedores lado a lado.", None),
        ("Novedad: dirección amplió el proyecto. El presupuesto aprobado pasa a 80.000 EUR.", "80.000 EUR"),
        ("Con el presupuesto nuevo suman un portal para que los proveedores carguen sus facturas.", None),
        ("Quieren lectura automática de facturas en PDF.", None),
        ("Necesitan un tablero con el gasto por categoría y por proveedor.", None),
        ("Agregan evaluación de proveedores con puntajes por entrega y calidad.", None),
        ("Piden firma electrónica de las órdenes de compra con DocuSign.", "DocuSign"),
        ("Suman gestión de presupuestos por área, con bloqueo si se excede.", None),
        ("Quieren exportar todo a Power BI.", "Power BI"),
        ("Necesitan roles: comprador, aprobador, auditor y administrador.", None),
        ("Agregan historial completo de cambios para auditoría.", None),
        ("Piden una app móvil solo para aprobar órdenes.", None),
        ("Suman recordatorios automáticos a los aprobadores que demoran.", None),
        ("Último ajuste: recalculá la estimación completa y decime el total y si entra en el presupuesto vigente.", None),
    ]),
    stale=[(8, "30.000 EUR")],
)

SCENARIOS = {s.name: s for s in (GROWING, PIVOT, CONTRADICTION)}
CHECKPOINTS = (1, 3, 6, 10, 20)
