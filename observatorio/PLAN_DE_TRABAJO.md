# Plan de trabajo para el portal unificado del Observatorio Nacional de Inteligencia Artificial

Proyecto IA para el Estado. Universidad de Cartagena. Versión 0.1 para discusión, septiembre de 2026.

## 1. Propósito y alcance

El presente plan describe la ruta para construir un único portal que sirva como sistema de información del Observatorio Nacional de Inteligencia Artificial y que reúna, bajo una misma cuenta de usuario, las aplicaciones que hoy operan de forma independiente dentro del proyecto IA para el Estado. El alcance comprende la unificación de las cuentas de la Solución Automatizada, el Catálogo de IA, el Gestor de Proyectos y el Gestor Documental, la incorporación de esas cuatro aplicaciones a una navegación común, y el desarrollo de tres módulos nuevos que responden a las necesidades de vigilancia tecnológica del Observatorio. Esos módulos son el editor y aplicador de cuestionarios, el cuadro de mando de entidades y la herramienta de costo-beneficio con sesión propia para cada entidad.

Queda fuera del alcance la aplicación de teclados, que se mantiene como un producto separado con su propio ciclo de vida. También queda fuera cualquier modificación sobre los servidores actuales durante la etapa de diseño, de modo que el prototipo navegable que acompaña este plan funciona sin conexión a bases de datos ni a servicios del proyecto y puede compartirse con terceros sin riesgo operativo.

## 2. Situación de partida y problema que se resuelve

Las cuatro aplicaciones existentes fueron construidas en momentos distintos del proyecto, con esquemas de usuarios propios y sin un identificador común de entidad. Un funcionario que participa en el diagnóstico debe hoy recordar hasta cuatro credenciales, transcribir a mano los resultados de una aplicación en otra y cargar los mismos documentos en más de un sitio. Para el equipo del Observatorio, esa dispersión impide consolidar información por entidad y obliga a construir los informes con cruces manuales en hojas de cálculo, con el costo en tiempo y en errores que ello supone.

El portal resuelve ese problema con tres decisiones de diseño. La primera consiste en que exista una sola identidad por persona, vinculada a una o varias entidades y con permisos declarados por aplicación. La segunda consiste en que la entidad pública, identificada por su NIT, sea la llave común de todos los datos, de manera que cuestionarios, proyectos, documentos y evaluaciones cuelguen de una misma ficha. La tercera consiste en que los módulos se comuniquen mediante eventos, de forma que el cierre de un cuestionario actualice el cuadro de mando, genere el informe en el Gestor Documental y active la recomendación automática sin intervención humana.

## 3. Principios que orientan la construcción

La integración se hace sin reescribir las aplicaciones existentes. Cada una se adapta para aceptar la sesión del portal y para consumir el registro maestro de entidades, y se conserva su lógica de negocio mientras se estabiliza la plataforma. Esta decisión reduce el riesgo del proyecto y permite que las entidades sigan trabajando durante la transición, a cambio de mantener durante algunos meses bases de datos heredadas que se sincronizan por identificador de entidad.

Los módulos nuevos se construyen directamente sobre la capa común de servicios, sin tablas de usuarios propias ni copias locales de la ficha de entidad. El diseño visual y los componentes de interfaz se comparten entre todos los módulos, lo que da al usuario la percepción de un solo sistema y reduce el esfuerzo de mantenimiento. Toda funcionalidad que produzca un documento institucional lo deposita en el Gestor Documental con control de versiones, en lugar de generar archivos dispersos.

El portal debe crecer por módulos sin intervenir el código de los servicios ya desplegados. Para ello la capa común incluye un registro de módulos desde el cual la administración declara cada servicio con su nombre, su descripción, su grupo de navegación, su dirección, su tipo (interno o aplicación externa que recibe la sesión del portal) y los roles con acceso. Un módulo registrado aparece en la navegación y en el escritorio de los usuarios autorizados, recibe la identidad del usuario, la entidad activa y el rol vigente, y puede consumir los servicios comunes mediante los contratos de datos publicados. Este mecanismo es el que permitirá incorporar futuras herramientas del Observatorio, o aplicaciones de terceros, con un costo de integración acotado y previsible.

La ayuda al usuario forma parte del producto y no de la capacitación posterior. Cada pantalla ofrece ayuda contextual con la guía paso a paso del servicio en uso, sus preguntas frecuentes y un acceso directo a soporte que registra desde qué pantalla se escribe. Un centro de ayuda reúne las guías de todos los servicios, un buscador por tarea, recorridos guiados que señalan los elementos de la interfaz en el orden en que se usan, atajos de teclado y el estado de la mesa de ayuda. El contenido de la ayuda se administra desde el mismo portal, de modo que un módulo nuevo incorpora su guía en el momento de registrarse y el equipo del Observatorio actualiza los textos sin desplegar código.

## 4. Arquitectura objetivo

La arquitectura se organiza en cuatro capas. La capa de presentación contiene el portal unificado, con escritorio, navegación, buscador transversal, selector de entidad y notificaciones, junto con la biblioteca de componentes compartidos. La capa de módulos funcionales agrupa los tres módulos nuevos y las cuatro aplicaciones adaptadas. La capa común de servicios provee la identidad y el control de acceso, el registro maestro de entidades, la interfaz de programación que define los contratos de datos entre módulos y el servicio único de almacenamiento de archivos. La capa de datos reúne la base de datos del portal, las bases de datos heredadas durante la transición y un almacén analítico con vistas consolidadas para el cuadro de mando y los informes.

La Tabla 1 resume los componentes de la capa común y su función dentro del conjunto.

| Componente | Función | Consumidores |
|---|---|---|
| Identidad y acceso | Cuenta única, inicio de sesión único, segundo factor, roles por aplicación y auditoría de accesos | Todos los módulos y aplicaciones |
| Registro maestro de entidades | Ficha única por entidad con NIT, nivel de gobierno, región, sector y responsables | Todos los módulos y aplicaciones |
| Registro de módulos | Declaración, activación y permisos de cada módulo, con generación de la navegación y del escritorio | Portal y administración |
| Centro de ayuda | Guías por servicio, ayuda contextual, recorridos guiados, buscador por tarea y enlace con soporte | Todos los módulos y aplicaciones |
| Interfaz de programación común | Contratos de datos, eventos entre módulos y notificaciones | Módulos nuevos y aplicaciones adaptadas |
| Almacenamiento de archivos | Servicio único de archivos con versiones y trazabilidad | Gestor Documental, Cuestionarios, Costo-beneficio, Gestor de Proyectos |
| Almacén analítico | Vistas consolidadas por entidad, región, sector y periodo | Cuadro de mando e informes del Observatorio |

Tabla 1. Componentes de la capa común de servicios. Fuente. Elaboración propia.

Sobre la tecnología concreta, la recomendación es reutilizar la pila con la que ya están construidas la mayoría de las aplicaciones del proyecto para reducir la curva de aprendizaje del equipo, y adoptar un proveedor de identidad de código abierto compatible con los estándares OpenID Connect y SAML, lo que deja abierta la puerta a la Autenticación Digital del Estado y a las cuentas institucionales de Google Workspace. La decisión final sobre la pila se toma en la fase 0, una vez concluido el inventario técnico.

## 5. Fases del plan

El plan se organiza en siete fases que suman doce meses. Las fases 2 a 5 se traslapan de forma deliberada porque tienen equipos y dependencias distintas, y la cuenta única se ubica al inicio porque todo lo demás depende de ella. La Tabla 2 presenta la secuencia, la duración estimada y el producto principal de cada fase.

| Fase | Nombre | Periodo | Producto principal |
|---|---|---|---|
| 0 | Levantamiento y diseño de la integración | Semanas 1 a 6 | Inventario técnico, registro maestro depurado, diseño detallado y prototipo validado |
| 1 | Cuenta única y portal base | Meses 2 a 4 | Servicio de identidad en producción y escritorio del portal operando |
| 2 | Adaptación de las aplicaciones existentes | Meses 4 a 7 | Cuatro aplicaciones aceptando la sesión única y el identificador común de entidad |
| 3 | Editor y aplicador de cuestionarios | Meses 5 a 7 | Módulo en producción con el instrumento de vigilancia tecnológica cargado |
| 4 | Cuadro de mando | Meses 7 a 9 | Indicadores, filtros, ficha por entidad, exportaciones e informes |
| 5 | Herramienta de costo-beneficio | Meses 8 a 10 | Sesiones por entidad, cálculo financiero e informe automático |
| 6 | Estabilización y transferencia | Meses 11 y 12 | Pruebas de carga y seguridad, manuales, capacitación y documentación técnica |

Tabla 2. Fases del plan de trabajo. Fuente. Elaboración propia.

### Fase 0. Levantamiento y diseño de la integración

Esta fase produce el conocimiento necesario para tomar las decisiones técnicas con evidencia. El equipo inventaría las cuatro aplicaciones existentes con sus tecnologías, versiones, bases de datos, esquemas de usuarios, volúmenes de registros y dependencias externas. En paralelo, cruza las tablas de usuarios de las cuatro aplicaciones para identificar personas repetidas, cuentas huérfanas y entidades registradas con nombres distintos, y construye a partir de ese cruce la primera versión del registro maestro de personas y de entidades, con el NIT como llave.

Con esa base se elabora el diseño detallado de la arquitectura, el modelo de roles por aplicación y los contratos de datos entre módulos. El prototipo navegable que acompaña este plan se ajusta con las observaciones del equipo del Observatorio y se valida con dos entidades piloto, una municipal y una nacional, para confirmar que la propuesta de navegación y el flujo de cuestionarios se entienden sin capacitación previa. La fase termina con un documento de arquitectura aprobado y con la pila tecnológica decidida.

### Fase 1. Cuenta única y portal base

Se despliega el servicio de identidad con inicio de sesión único, segundo factor, recuperación de acceso, políticas de contraseña y auditoría. Se construye el escritorio del portal con la navegación generada desde el registro de módulos, el selector de entidad, el buscador transversal, el centro de ayuda con su panel contextual y sus recorridos guiados, y la biblioteca de componentes compartidos que usarán todos los módulos. El asistente de vinculación de cuentas heredadas permite que cada persona asocie una sola vez sus credenciales anteriores a la nueva cuenta, y se acompaña de una campaña de comunicación con las entidades para que la migración se complete antes de que las aplicaciones adaptadas entren en producción.

### Fase 2. Adaptación de las aplicaciones existentes

Cada aplicación se modifica para delegar la autenticación en el servicio de identidad y para tomar la ficha de entidad del registro maestro. Las tablas de usuarios locales se sustituyen por referencias a la cuenta única y se homologa el identificador de entidad en todas las tablas que lo requieran. Se abren los enlaces entre aplicaciones que hoy no existen, de modo que una recomendación de la Solución Automatizada pueda convertirse en un proyecto del Gestor de Proyectos y que las evidencias de un proyecto se guarden en el Gestor Documental sin cargarlas de nuevo. La Solución Automatizada, además, deja de pedir el diagnóstico a mano y lo toma del cuestionario cerrado más reciente de la entidad, lo que exige coordinar esta fase con la fase 3.

### Fase 3. Editor y aplicador de cuestionarios

El editor permite construir instrumentos con secciones, tipos de pregunta (escala de uno a cinco, opción única, opción múltiple, numérica y abierta), pesos por pregunta, dimensión asociada y versionado del instrumento. El aplicador asigna el instrumento a las entidades, guarda cada respuesta en el momento en que se registra, muestra el avance por sección, envía recordatorios y permite el cierre por parte del responsable de la entidad. El motor de cálculo del índice de madurez toma los pesos declarados y produce el puntaje por dimensión y el índice global, con lo que genera el informe individual de la entidad y lo deposita en el Gestor Documental. El instrumento de vigilancia tecnológica vigente se carga como primer contenido del módulo.

### Fase 4. Cuadro de mando

Se construye el almacén analítico alimentado por cuestionarios, proyectos, documentos y evaluaciones, y sobre él el cuadro de mando con indicadores de cobertura, índice de madurez, distribución por niveles, puntaje por dimensión y sector, evolución por cortes y una ficha por entidad que reúne todo lo que el ecosistema sabe de ella. Los filtros por región, nivel de gobierno, sector y periodo, junto con las exportaciones a hoja de cálculo y la generación de informes con la plantilla institucional del proyecto, sustituyen el trabajo manual de consolidación que hoy realiza el equipo del Observatorio.

### Fase 5. Herramienta de costo-beneficio

La herramienta ofrece a cada entidad un formulario guiado para capturar la inversión inicial, los costos de operación, la capacitación, los beneficios cuantificables por ahorro de horas, reducción de errores y otros conceptos, el horizonte de evaluación y la tasa de descuento. Con esos datos calcula el valor presente neto, la relación beneficio costo, la tasa interna de retorno y el periodo de recuperación, y muestra el flujo acumulado por año. Cada entidad trabaja en su propia sesión, puede guardar varias evaluaciones y compararlas, y el Observatorio consulta el agregado nacional sin acceder al detalle de cada entidad salvo autorización. El informe de cada evaluación se genera en el Gestor Documental y la evaluación puede convertirse en un proyecto del Gestor de Proyectos.

### Fase 6. Estabilización y transferencia

Se ejecutan pruebas de carga con los volúmenes esperados para el cierre de un corte semestral, pruebas de seguridad sobre el servicio de identidad y las interfaces de programación, y se corrigen las incidencias encontradas. Los accesos antiguos a las aplicaciones se apagan de forma gradual una vez que la migración de cuentas supera el umbral acordado. Se entregan los manuales de usuario por rol, se capacita al equipo del Observatorio y a los responsables de las entidades, y se documenta la arquitectura, el despliegue y la operación para que la Universidad pueda sostener la plataforma.

## 6. Estrategia de unificación de cuentas

La unificación de cuentas es el punto de mayor riesgo del plan porque afecta a todos los usuarios activos y porque las cuatro aplicaciones identifican a las personas de maneras distintas. La estrategia propuesta se apoya en el correo institucional como criterio principal de coincidencia y en el NIT de la entidad como criterio secundario, con revisión manual de los casos en que una misma persona aparezca con correos distintos o en que un mismo correo aparezca asociado a varias entidades.

La migración se hace por vinculación y no por sustitución. Cada persona conserva sus credenciales antiguas hasta que crea la cuenta única y las asocia mediante el asistente de vinculación, que verifica la propiedad de cada cuenta heredada solicitando el inicio de sesión en la aplicación correspondiente. Durante el periodo de convivencia, las aplicaciones aceptan tanto la sesión del portal como las credenciales antiguas, y el apagado de estas últimas se programa cuando la vinculación supere el ochenta por ciento de las cuentas activas, con comunicación previa a las entidades rezagadas. La Tabla 3 resume el modelo de roles propuesto, que reemplaza los permisos dispersos de cada aplicación.

| Rol | Alcance | Permisos característicos |
|---|---|---|
| Funcionario de entidad | Su entidad | Responde cuestionarios, crea evaluaciones y proyectos, carga evidencias, consulta su ficha en el cuadro de mando |
| Directivo de entidad | Su entidad | Consulta todo lo anterior, aprueba cierres de cuestionario y evaluaciones, no edita instrumentos |
| Analista del Observatorio | Todas las entidades | Consulta y edita el cuadro de mando, revisa el Catálogo y la Solución Automatizada, publica entregables |
| Editor de instrumentos | Instrumentos | Crea, versiona y publica cuestionarios, sin acceso a evaluaciones de las entidades |
| Administrador | Plataforma | Gestiona usuarios, roles, entidades, parámetros y auditoría |

Tabla 3. Modelo de roles unificado. Fuente. Elaboración propia.

## 7. Equipo y esfuerzo estimado

El equipo mínimo para ejecutar el plan en doce meses está compuesto por una persona que coordine el proyecto y sostenga la relación con el Observatorio y con las entidades, un arquitecto de software con dedicación parcial durante toda la ejecución y total durante la fase 0, dos desarrolladores de tiempo completo, un desarrollador con perfil de interfaz de usuario y experiencia de usuario, un analista de datos que construya el almacén analítico y los indicadores, y un perfil de pruebas y seguridad con dedicación parcial que se intensifica en la fase 6. El equipo del Observatorio participa como dueño del producto, define los instrumentos, valida los indicadores y aprueba cada fase.

La estimación de esfuerzo se expresa en meses persona y se presenta en la Tabla 4. Se trata de una estimación de orden de magnitud que se afina al cierre de la fase 0, cuando el inventario técnico permita conocer el estado real de las aplicaciones.

| Fase | Meses persona | Perfiles principales |
|---|---|---|
| 0 | 4 | Coordinación, arquitectura, experiencia de usuario |
| 1 | 9 | Arquitectura, dos desarrolladores, interfaz |
| 2 | 10 | Dos desarrolladores, arquitectura parcial |
| 3 | 8 | Un desarrollador, interfaz, analista de datos parcial |
| 4 | 8 | Analista de datos, un desarrollador, interfaz |
| 5 | 6 | Un desarrollador, interfaz, analista de datos parcial |
| 6 | 6 | Pruebas y seguridad, coordinación, todo el equipo parcial |
| Total | 51 | |

Tabla 4. Esfuerzo estimado por fase. Fuente. Elaboración propia.

## 8. Riesgos y medidas de control

| Riesgo | Efecto | Medida de control |
|---|---|---|
| Cuentas duplicadas o inconsistentes entre aplicaciones | Personas con acceso incorrecto o pérdida de historial | Cruce automático en la fase 0 con revisión manual de casos ambiguos y vinculación verificada por inicio de sesión |
| Aplicaciones existentes con código difícil de modificar | Retraso de la fase 2 y acoplamiento débil | Inventario técnico temprano, adaptación mediante capa intermedia cuando el código no admita cambios directos |
| Baja adopción de la cuenta única por parte de las entidades | Convivencia prolongada de accesos antiguos | Campaña de comunicación, asistente de vinculación en un solo paso y apagado escalonado con aviso previo |
| Instrumento de cuestionario que cambia durante el desarrollo | Reelaboración del motor de cálculo | Versionado de instrumentos desde el diseño y pesos configurables sin cambios de código |
| Datos financieros sensibles en la herramienta de costo-beneficio | Reticencia de las entidades a registrar cifras | Sesiones privadas por entidad, agregación anónima para el Observatorio y política de acceso publicada |
| Rotación del equipo de desarrollo | Pérdida de conocimiento | Documentación continua, revisión de código por pares y transferencia formal en la fase 6 |

Tabla 5. Riesgos principales y medidas de control. Fuente. Elaboración propia.

## 9. Gobierno del proyecto e indicadores de seguimiento

El proyecto se gobierna con un comité mensual en el que participan la dirección del Observatorio, la coordinación del proyecto y la arquitectura, y con revisiones quincenales de avance con el equipo de desarrollo. Cada fase se cierra con una demostración funcional sobre datos reales anonimizados y con la aprobación formal del Observatorio, de manera que ningún módulo pasa a producción sin haber sido probado por quienes lo usarán.

El avance se mide con indicadores que se publican en el propio cuadro de mando una vez que este exista. Los indicadores propuestos son el porcentaje de cuentas activas vinculadas a la cuenta única, el número de aplicaciones que operan con la sesión del portal, el porcentaje de entidades que completan el cuestionario dentro del plazo del corte, el tiempo que tarda el Observatorio en producir el informe consolidado de un corte, el número de evaluaciones de costo-beneficio registradas y la proporción de incidencias resueltas dentro del acuerdo de servicio. La línea base de cada indicador se levanta en la fase 0 para que la mejora sea verificable.

## 10. Supuestos y decisiones pendientes

El plan asume que las cuatro aplicaciones existentes se encuentran bajo control técnico del proyecto, con acceso al código fuente y a las bases de datos, y que la Universidad de Cartagena dispone o puede disponer de la infraestructura para alojar el servicio de identidad y el portal. Asume también que la Solución Automatizada funciona como recomendador de soluciones a partir del diagnóstico de la entidad, interpretación que debe confirmarse con el equipo responsable de esa aplicación.

Quedan pendientes de decisión el proveedor de identidad y la pila tecnológica definitiva, la conveniencia de integrar la Autenticación Digital del Estado desde la primera fase o en una fase posterior, la política de acceso del Observatorio a las cifras individuales de costo-beneficio de cada entidad, y la selección de las dos entidades piloto que validarán el prototipo en la fase 0. Estas decisiones se llevan al primer comité del proyecto con las alternativas y sus implicaciones documentadas.
