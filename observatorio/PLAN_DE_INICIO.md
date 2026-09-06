# Plan de inicio del portal del Observatorio sin afectar las aplicaciones existentes

Proyecto IA para el Estado. Universidad de Cartagena. Versión 0.1 para discusión, septiembre de 2026.

## 1. Objeto del documento

Este documento complementa el plan de trabajo general y responde a una sola pregunta. Cómo se empieza a construir el portal del Observatorio Nacional de Inteligencia Artificial de manera que la Solución Automatizada, el Catálogo de IA, el Gestor de Proyectos y el Gestor Documental sigan operando exactamente como hoy, con sus usuarios, sus contraseñas, sus datos y sus servidores intactos, durante todo el periodo en que el portal se diseña, se construye y se pone a prueba. La regla que gobierna las primeras etapas es que ningún componente nuevo escribe en las bases de datos existentes, ningún archivo de las aplicaciones actuales se modifica y ninguna dirección que los usuarios usan hoy cambia de comportamiento sin un aviso previo y una vía de retorno probada.

La estrategia consiste en levantar el portal como un sistema nuevo y separado, que al comienzo solo enlaza hacia las aplicaciones actuales y solo lee copias de sus datos, y que va asumiendo funciones de integración una aplicación a la vez, cada una con su interruptor de activación y su procedimiento de reversa. Con este enfoque, el portal puede mostrarse a las entidades y al Observatorio desde el primer trimestre con sus tres módulos nuevos operando sobre datos reales de solo lectura, mientras las aplicaciones existentes no perciben cambio alguno.

## 2. Reglas de no afectación

Las reglas siguientes se aplican sin excepción durante las fases de inicio y se levantan una por una, con acta, cuando cada aplicación entre en su ventana de integración.

| Regla | Alcance | Cómo se verifica |
|---|---|---|
| Sin escritura en bases de datos existentes | El portal y sus módulos usan bases de datos propias. Toda lectura de datos actuales se hace sobre copias o con un usuario de base de datos que solo tiene permiso de consulta | Revisión de privilegios del usuario de conexión y registro de auditoría del motor de base de datos |
| Sin cambios de código en las aplicaciones actuales | Las adaptaciones necesarias viven en el portal, en adaptadores o en un servidor intermedio, nunca dentro del código de la aplicación existente | Comparación de la huella de los archivos desplegados antes y después de cada entrega |
| Sin cambios de dirección ni de acceso | Las direcciones actuales, las pantallas de ingreso y las contraseñas de cada aplicación siguen funcionando igual | Prueba de ingreso manual en las cuatro aplicaciones al cierre de cada entrega |
| Infraestructura separada | El portal se despliega en un servidor o contenedor distinto, con su propio dominio o subdominio, su propia base de datos y sus propias copias de seguridad | Inventario de infraestructura firmado por el responsable técnico |
| Copias de seguridad antes de tocar cualquier cosa | Ninguna acción sobre una aplicación existente, incluso una lectura masiva, se hace sin copia de seguridad reciente y verificada | Bitácora de respaldos con fecha, tamaño y prueba de restauración |
| Reversa probada antes de activar | Cada cambio que en el futuro sí toque una aplicación existente se activa con un interruptor y se prueba primero su desactivación en el entorno de pruebas | Acta de prueba de reversa firmada antes del despliegue |

Tabla 1. Reglas de no afectación durante las fases de inicio. Fuente. Elaboración propia.

## 3. Cómo se aísla el portal de las aplicaciones actuales

El aislamiento se consigue con cuatro decisiones de infraestructura que se toman en las primeras dos semanas. La primera es un subdominio propio para el portal, por ejemplo observatorio bajo el dominio del proyecto, que apunta a un servidor o contenedor nuevo. Las aplicaciones actuales conservan sus direcciones y nada en el servidor que las aloja cambia. La segunda es una base de datos propia para el portal, con su esquema de usuarios, entidades, cuestionarios, respuestas, evaluaciones y módulos, sin ninguna tabla compartida con las aplicaciones existentes. La tercera es un entorno de pruebas que reproduce las cuatro aplicaciones a partir de copias de sus bases de datos y de sus archivos, de modo que toda prueba de integración se ejecute contra réplicas y nunca contra producción. La cuarta es una cuenta de base de datos de solo lectura por cada aplicación, creada por el administrador actual de cada una, que es el único canal por el que el portal obtiene datos reales en las primeras fases.

Con esas cuatro decisiones, el portal puede fallar, reiniciarse, borrarse y volverse a desplegar sin que las aplicaciones actuales lo noten. El único punto de contacto es la lectura, que se hace en horarios de baja carga y con límites de consulta acordados con cada administrador.

## 4. Etapas de inicio

Las etapas siguientes cubren los primeros seis meses y se ordenan de menor a mayor contacto con las aplicaciones existentes. Cada una tiene una condición de salida que debe cumplirse antes de pasar a la siguiente.

### Etapa 1. Conocer sin tocar (semanas 1 a 3)

El equipo levanta el inventario técnico de las cuatro aplicaciones con acceso de lectura al código fuente y a copias de las bases de datos. Se documenta para cada una la tecnología, la versión, el proveedor de alojamiento, el esquema de usuarios, el número de cuentas activas, las tablas que identifican a la entidad y la forma en que hoy se autentican los usuarios. En paralelo se solicita a cada administrador una copia completa de la base de datos y de los archivos, con la que se levanta el entorno de pruebas. Nada de esto requiere cambios en producción, y el único favor que se pide a los administradores actuales es una copia y una cuenta de consulta.

La condición de salida es un documento de inventario aprobado, un entorno de pruebas con las cuatro aplicaciones reproducidas y una tabla de correspondencia preliminar entre usuarios y entidades de las cuatro fuentes.

### Etapa 2. Levantar el portal vacío (semanas 3 a 6)

Se despliega el servidor del portal con su subdominio, su base de datos, su proveedor de identidad y su certificado. Se instala el esqueleto de la aplicación con el escritorio, la navegación generada desde el registro de módulos, el centro de ayuda y la cuenta única. En esta etapa el portal no tiene usuarios reales ni datos reales. Sirve para validar la infraestructura, las copias de seguridad, el monitoreo y el procedimiento de despliegue. El prototipo navegable se usa como referencia visual y funcional para el equipo de desarrollo.

La condición de salida es un portal accesible en su subdominio, con ingreso mediante la cuenta única para el equipo del proyecto, con copias de seguridad automáticas verificadas y con el procedimiento de despliegue documentado y ejecutado al menos tres veces sin intervención manual.

### Etapa 3. Los módulos nuevos sobre datos propios (semanas 6 a 14)

Se construyen los tres módulos nuevos, que no dependen de las aplicaciones existentes. El editor y aplicador de cuestionarios se carga con el instrumento de vigilancia tecnológica vigente y se prueba con dos entidades piloto que responden en el portal. La herramienta de costo-beneficio opera desde el primer día con sesiones propias por entidad. El cuadro de mando arranca alimentado por los cuestionarios respondidos en el portal y por el registro maestro de entidades que se construyó en la etapa 1. En esta etapa el escritorio del portal muestra las cuatro aplicaciones actuales como tarjetas que abren cada aplicación en una pestaña nueva, con su ingreso de siempre. El usuario ya percibe un punto único de entrada, aunque todavía deba ingresar por separado en cada aplicación.

La condición de salida es el instrumento respondido por las dos entidades piloto de principio a fin, el índice calculado y verificado a mano por el equipo del Observatorio, y al menos cinco evaluaciones de costo-beneficio registradas por usuarios reales.

### Etapa 4. Leer las aplicaciones actuales sin escribir en ellas (semanas 10 a 18)

Con las cuentas de solo lectura, el portal empieza a traer datos de las cuatro aplicaciones hacia el almacén analítico del cuadro de mando. La lectura se hace con un proceso programado que corre en horario nocturno, extrae únicamente las tablas acordadas y las carga en el almacén del portal, donde se homologa el identificador de entidad. Si una aplicación no admite conexión directa, se usa la exportación que ya ofrezca o un archivo entregado por su administrador. El cuadro de mando muestra entonces, por entidad, sus proyectos, sus documentos, sus recomendaciones y las herramientas del catálogo que usa, todo en consulta. En esta misma etapa el asistente de vinculación de cuentas permite que cada persona asocie sus usuarios antiguos a su cuenta del portal, sin que las aplicaciones cambien nada. La vinculación se verifica pidiéndole a la persona que demuestre que controla el correo registrado en la aplicación antigua, o que ingrese una vez en ella desde un enlace generado por el portal.

La condición de salida es el almacén analítico actualizado cada noche durante cuatro semanas sin incidentes, un cuadro de mando con datos consolidados de las cuatro fuentes, y al menos la mitad de las cuentas activas vinculadas.

### Etapa 5. Primera aplicación con ingreso único (semanas 18 a 26)

Solo después de las cuatro etapas anteriores se toca por primera vez una aplicación existente, y se elige la de menor riesgo. El criterio recomendado es empezar por la aplicación con menos usuarios activos, menos escritura de datos y un código más sencillo, que según el inventario preliminar sería el Catálogo de IA. La adaptación se hace primero en el entorno de pruebas, sobre la réplica, y consiste en agregar a la pantalla de ingreso una opción de entrar con la cuenta del Observatorio, manteniendo el ingreso tradicional. La opción se controla con un interruptor de configuración, de modo que apagarlo devuelve la aplicación a su estado exacto anterior sin redesplegar código. La tabla de usuarios de la aplicación no se modifica. Lo que se agrega es una tabla de correspondencia entre la cuenta del portal y el usuario local, que se llena con las vinculaciones hechas en la etapa 4.

La activación en producción se hace en una ventana de mantenimiento anunciada, con copia de seguridad previa, con el interruptor apagado durante el despliegue y encendido solo cuando el equipo verifica en producción que el ingreso tradicional sigue funcionando. Se observa durante dos semanas. Si se presenta cualquier incidente que no se resuelva en una hora, se apaga el interruptor y se analiza en el entorno de pruebas. Cumplidas las dos semanas sin incidentes, se documenta el procedimiento y se repite con la siguiente aplicación.

La condición de salida es el Catálogo de IA aceptando ambos ingresos durante dos semanas sin incidentes, el procedimiento de adaptación documentado y el orden de las tres aplicaciones restantes acordado con sus administradores.

## 5. Calendario de los primeros noventa días

| Semana | Actividad principal | Contacto con aplicaciones actuales | Entregable |
|---|---|---|---|
| 1 | Reunión de arranque, acuerdos de acceso de lectura, solicitud de copias | Ninguno | Acta de arranque y lista de accesos |
| 2 | Inventario técnico de las cuatro aplicaciones | Lectura de código y copias | Fichas técnicas por aplicación |
| 3 | Entorno de pruebas con réplicas, cruce preliminar de usuarios y entidades | Ninguno, se trabaja sobre copias | Entorno de pruebas operativo y tabla de correspondencia |
| 4 | Aprovisionamiento del servidor del portal, subdominio, certificado, base de datos | Ninguno | Infraestructura del portal disponible |
| 5 | Proveedor de identidad, cuenta única, esqueleto del portal | Ninguno | Ingreso al portal para el equipo del proyecto |
| 6 | Registro de módulos, escritorio, centro de ayuda, procedimiento de despliegue | Ninguno | Portal vacío en su subdominio con despliegue automatizado |
| 7 a 9 | Editor y aplicador de cuestionarios con el instrumento vigente | Ninguno | Módulo de cuestionarios en pruebas con dos entidades piloto |
| 10 a 11 | Herramienta de costo-beneficio y registro maestro de entidades | Ninguno | Módulo de costo-beneficio operativo |
| 12 a 13 | Cuadro de mando con datos del portal y tarjetas de acceso a las aplicaciones actuales | Enlaces salientes, sin integración | Escritorio con punto único de entrada |
| 13 | Presentación del portal al Observatorio y a las entidades piloto | Ninguno | Acta de validación de la etapa 3 |

Tabla 2. Calendario de los primeros noventa días. Fuente. Elaboración propia.

Al cierre de los noventa días, el portal existe, funciona con usuarios reales en sus tres módulos nuevos y ofrece un punto único de entrada al ecosistema, sin que ninguna aplicación existente haya recibido un solo cambio.

## 6. Qué se necesita para empezar

El arranque depende de un conjunto reducido de insumos que el equipo del proyecto puede reunir en la primera semana. La Tabla 3 los enumera con el responsable sugerido.

| Insumo | Responsable sugerido | Uso |
|---|---|---|
| Acceso de lectura al código fuente de las cuatro aplicaciones | Responsable técnico de cada aplicación | Inventario técnico y entorno de pruebas |
| Copia completa de la base de datos y de los archivos de cada aplicación | Administrador de cada aplicación | Réplicas en el entorno de pruebas y cruce de usuarios |
| Cuenta de base de datos de solo lectura por aplicación, o un mecanismo de exportación | Administrador de cada aplicación | Carga nocturna del almacén analítico en la etapa 4 |
| Datos del alojamiento actual y del dominio del proyecto | Coordinación del proyecto | Subdominio y servidor del portal |
| Servidor o contenedor nuevo para el portal, con copias de seguridad | Infraestructura de la Universidad | Despliegue aislado |
| Instrumento de vigilancia tecnológica vigente con sus pesos | Equipo del Observatorio | Primer contenido del módulo de cuestionarios |
| Dos entidades piloto dispuestas a responder el cuestionario en el portal | Coordinación del proyecto con las entidades | Validación de la etapa 3 |
| Listado de usuarios activos por aplicación con correo institucional | Administrador de cada aplicación | Registro maestro de personas y vinculación de cuentas |

Tabla 3. Insumos necesarios para el arranque. Fuente. Elaboración propia.

## 7. Cómo se revierte cada paso

La reversibilidad se diseña antes de cada acción y se registra en la Tabla 4. Durante las etapas 1 a 4 la reversa es trivial porque nada cambió en las aplicaciones existentes. A partir de la etapa 5, cada adaptación lleva un interruptor y una copia de seguridad previa.

| Acción | Efecto sobre aplicaciones actuales | Procedimiento de reversa | Tiempo estimado |
|---|---|---|---|
| Desplegar o rehacer el portal | Ninguno | Apagar el servidor del portal | Minutos |
| Lectura nocturna del almacén analítico | Carga de consulta en horario nocturno | Desactivar la tarea programada y revocar la cuenta de lectura | Minutos |
| Vinculación de cuentas | Ninguno, la correspondencia vive en el portal | Borrar la correspondencia en el portal | Minutos |
| Ingreso único en una aplicación | Opción adicional en la pantalla de ingreso | Apagar el interruptor de configuración | Menos de una hora |
| Sustitución de la tabla de usuarios local (fase posterior) | Cambio de esquema | Restaurar la copia de seguridad tomada en la ventana de mantenimiento | Menos de una jornada |

Tabla 4. Procedimientos de reversa por acción. Fuente. Elaboración propia.

## 8. Puertas de decisión

El paso de una etapa a la siguiente no ocurre por calendario sino por cumplimiento de la condición de salida, revisada en el comité mensual del proyecto. La primera puerta, al cierre de la semana 3, decide la pila tecnológica y confirma que el entorno de pruebas reproduce las cuatro aplicaciones. La segunda, al cierre de la semana 6, confirma que la infraestructura del portal cumple con copias de seguridad, monitoreo y despliegue automatizado. La tercera, al cierre de la semana 13, valida con el Observatorio y las entidades piloto que los módulos nuevos hacen lo que deben hacer. La cuarta, hacia la semana 18, autoriza la primera adaptación de una aplicación existente con base en las cuatro semanas de lectura nocturna sin incidentes y en el porcentaje de cuentas vinculadas. Ninguna aplicación existente se toca antes de esa cuarta puerta.

## 9. Recomendación sobre el orden de integración

La secuencia propuesta para la etapa 5 y las posteriores parte del riesgo y del beneficio de cada aplicación. El Catálogo de IA va primero porque es de consulta, tiene pocos flujos de escritura y su interrupción no detiene el trabajo de ninguna entidad. El Gestor Documental sigue porque comparte con el portal el servicio de archivos y porque su integración permite que los informes de cuestionarios y evaluaciones lleguen a él de forma automática, lo que se convierte en el primer beneficio visible para las entidades. El Gestor de Proyectos va en tercer lugar, cuando ya el ingreso único y el servicio de archivos están probados. La Solución Automatizada se deja para el final porque su integración es la más profunda, pues implica que tome el diagnóstico del módulo de cuestionarios en lugar de pedirlo a mano, y conviene hacerlo cuando el instrumento y el cálculo del índice lleven varios meses estables.

Este orden se revisa al terminar el inventario de la etapa 1, porque el estado real del código y de las bases de datos puede cambiar la apreciación del riesgo de cada aplicación.
