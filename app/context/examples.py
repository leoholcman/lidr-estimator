"""Datos estáticos que se inyectan en el prompt (CAG).

Estimaciones históricas (ficticias) que el modelo usa como few-shot examples.
Tiempos de desarrollo asistido por IA y tarifas en USD. Todas siguen el mismo formato y la misma tarifa para que el output sea consistente.
"""

ESTIMATION_EXAMPLES = [
    {
        "meeting_summary": """\
Distribuidora de material eléctrico con 3 almacenes. Hoy controlan el stock en \
hojas de Excel compartidas y pierden ventas por roturas de stock. Piden una \
plataforma web para gestionar el inventario de los 3 almacenes: alta y baja de \
productos, entradas y salidas de mercancía, y traspasos entre almacenes. \
Necesitan 3 roles (administrador, jefe de almacén y operario), un dashboard con \
el stock valorizado y los productos de mayor rotación, y avisos por email cuando \
un producto baja del stock mínimo. Unas 15 personas lo usarán desde el ordenador \
de la oficina. No necesitan app móvil por ahora.""",
        "estimation": """\
## Estimación: Plataforma de Gestión de Inventario

### Desglose de tareas
| # | Tarea | Horas |
|---|-------|-------|
| 1 | Discovery y diseño UI/UX | 8 |
| 2 | Backend API (CRUD de productos, movimientos y traspasos) | 16 |
| 3 | Autenticación y roles (admin, jefe de almacén, operario) | 6 |
| 4 | Dashboard con métricas (stock valorizado, rotación) | 10 |
| 5 | Alertas de stock mínimo por email | 4 |
| 6 | Testing y QA | 10 |
| 7 | Infraestructura y despliegue | 4 |

**Subtotal: 58 horas**
**Contingencia (15%): 9 horas**
**Total estimado: 67 horas — USD 2.345 (tarifa media USD 35/h)**

**Equipo recomendado:** 1 desarrollador full-stack
**Duración estimada:** 2-3 semanas

### Supuestos
- Desarrollo asistido por IA: el ahorro está en escribir código; discovery, QA y despliegue no se aceleran igual.
- Carga inicial de productos desde los Excel actuales, provistos por el cliente en un formato único.
- Uso solo desde escritorio (diseño responsive básico, sin app móvil).

### Fuera de alcance
- Integración con el ERP o el software de facturación.
- Lectura de códigos de barras.""",
    },
    {
        "meeting_summary": """\
Cadena de 5 gimnasios boutique que gestiona las reservas de clases por WhatsApp \
y una planilla. Quieren una app móvil (iOS y Android) para que los socios vean \
el horario de clases, reserven y cancelen plaza, y compren bonos o suscripciones \
mensuales con tarjeta. También necesitan un panel web para que los recepcionistas \
gestionen clases, aforos y socios, y notificaciones push para recordatorios y \
liberación de plazas en lista de espera. Tienen unos 2.000 socios activos. \
Quieren lanzar antes del inicio de temporada, en unos 3 meses.""",
        "estimation": """\
## Estimación: App de Reservas para Cadena de Gimnasios

### Desglose de tareas
| # | Tarea | Horas |
|---|-------|-------|
| 1 | Discovery y diseño UI/UX (app y panel) | 16 |
| 2 | App móvil multiplataforma (horarios, reservas, lista de espera, perfil) | 50 |
| 3 | Backend API y panel web de administración | 30 |
| 4 | Integración de pagos con Stripe (bonos y suscripciones) | 14 |
| 5 | Notificaciones push | 6 |
| 6 | Testing y QA | 16 |
| 7 | Publicación en stores e infraestructura | 8 |

**Subtotal: 140 horas**
**Contingencia (20%): 28 horas**
**Total estimado: 168 horas — USD 5.880 (tarifa media USD 35/h)**

**Equipo recomendado:** 1 desarrollador mobile/full-stack + 1 diseñador UX (part-time)
**Duración estimada:** 5-6 semanas (incluye revisión de las stores)

### Supuestos
- Desarrollo asistido por IA: el ahorro está en escribir código; diseño, QA y la revisión de las stores no se aceleran igual.
- El cliente gestiona las cuentas de Apple Developer, Google Play y Stripe.
- La contingencia sube al 20% por las integraciones con terceros y la revisión de las stores.

### Fuera de alcance
- Control de acceso físico (tornos o lectores de QR).
- Migración del historial de socios anterior a la app.""",
    },
    {
        "meeting_summary": """\
Mayorista de alimentación que recibe unos 150 pedidos diarios de sus clientes \
por email, en archivos CSV y Excel con formatos distintos. Dos administrativos \
los cargan a mano en Odoo y cometen errores frecuentes. Quieren automatizar la \
importación: leer los archivos adjuntos, validar productos y cantidades, y crear \
los pedidos en Odoo. Los pedidos con errores deben quedar en un panel simple para \
que un administrativo los revise y corrija antes de enviarlos. Es una \
herramienta interna, sin requisitos de diseño especiales.""",
        "estimation": """\
## Estimación: Automatización de Importación de Pedidos a Odoo

### Desglose de tareas
| # | Tarea | Horas |
|---|-------|-------|
| 1 | Análisis de Odoo y mapeo de formatos de pedido | 4 |
| 2 | Lectura del buzón y parser de CSV/Excel con validaciones | 8 |
| 3 | Integración con la API de Odoo (creación de pedidos) | 10 |
| 4 | Panel de revisión y corrección de pedidos con errores | 6 |
| 5 | Testing con pedidos reales | 6 |
| 6 | Despliegue y documentación | 2 |

**Subtotal: 36 horas**
**Contingencia (15%): 5 horas**
**Total estimado: 41 horas — USD 1.435 (tarifa media USD 35/h)**

**Equipo recomendado:** 1 desarrollador backend
**Duración estimada:** 1-2 semanas

### Supuestos
- Desarrollo asistido por IA: el ahorro está en el parser y la integración; el testing con datos reales no se acelera igual.
- Hay como máximo 5 formatos de archivo distintos; cada formato nuevo se estima aparte.
- Odoo tiene la API habilitada y existe un entorno de pruebas.

### Fuera de alcance
- Lectura de pedidos en PDF o en el cuerpo del email.
- Cambios en la configuración de Odoo.""",
    },
]
