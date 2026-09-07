# Protocolo del conector entre el portal del Observatorio y las aplicaciones

Versión 1.0. Septiembre de 2026.

## 1. Qué es el conector y qué no es

El conector es un único archivo que se agrega a cada aplicación del proyecto para que el portal del Observatorio pueda hacer tres cosas. Verificar que un usuario y una clave son válidos en esa aplicación, abrir en ella una sesión ya iniciada cuando el usuario llega desde el portal, y entregar conjuntos de datos de solo lectura para el cuadro de mando. El archivo se escribe en el mismo lenguaje de la aplicación, no modifica ningún archivo existente ni el esquema de su base de datos, y permanece apagado hasta que el administrador lo activa con una variable de configuración. Con el conector apagado la aplicación responde a sus usuarios exactamente igual que antes, y retirarlo consiste en dejar de montarlo o borrarlo.

El conector no reemplaza la pantalla de ingreso de la aplicación, que sigue funcionando para quien entre directamente por su dirección. Tampoco guarda claves ni crea usuarios. Cuando el portal pide verificar una clave, la aplicación usa su propia rutina de comprobación y responde si es válida. Cuando el portal pide abrir una sesión, la aplicación usa la misma rutina con la que crea sesiones en su ingreso normal.

## 2. Seguridad

Todas las llamadas del portal al conector viajan por HTTPS y van firmadas con HMAC-SHA256 usando un secreto compartido distinto por aplicación, de al menos 64 caracteres, que se guarda en la configuración de ambos lados y nunca en el código. La firma cubre el método, la acción, una marca de tiempo, un valor de un solo uso y el cuerpo de la petición, de modo que una petición capturada no puede repetirse ni alterarse. El conector rechaza marcas de tiempo con más de cinco minutos de diferencia y valores de un solo uso ya vistos.

La apertura de sesión usa un token firmado por el portal con vigencia de sesenta segundos y un identificador único que el conector acepta una sola vez. El token declara el identificador del usuario en esa aplicación y su correo. El conector busca el usuario por esos datos en su propia base y solo entonces crea la sesión local. Un token vencido, repetido o con firma incorrecta produce un error y ninguna sesión.

La verificación de credenciales recibe la clave en el cuerpo de una petición firmada sobre HTTPS, la entrega a la rutina de comprobación de la aplicación y la descarta. El portal tampoco la conserva. Se recomienda que la aplicación registre en su propia bitácora cada llamada al conector con la acción, el resultado y la dirección de origen.

## 3. Acciones

Las acciones firmadas se envían con el método POST al archivo del conector, con el cuerpo en JSON y las cabeceras X-Obs-Timestamp, X-Obs-Nonce, X-Obs-Signature y X-Obs-Portal. La cadena que se firma es la concatenación con saltos de línea de POST, la acción, la marca de tiempo, el valor de un solo uso y el cuerpo exacto de la petición.

| Acción | Petición | Respuesta |
|---|---|---|
| estado | `{"accion":"estado"}` | `{"ok":true,"version":"1.0","conjuntos":["usuarios","actividad"],"hora":"..."}` |
| verificar | `{"accion":"verificar","usuario":"...","clave":"..."}` | `{"ok":true,"id":"12","usuario":"jmartinez","correo":"...","nombre":"...","rol":"..."}` o `{"ok":false}` |
| exportar | `{"accion":"exportar","conjunto":"usuarios","desde":null}` | `{"ok":true,"conjunto":"usuarios","descripcion":"...","filas":[{...}]}` |

Tabla 1. Acciones firmadas del conector. Fuente. Elaboración propia.

La apertura de sesión es una petición GET que hace el navegador del usuario a la dirección del conector con los parámetros accion igual a sso y token. El token tiene dos partes separadas por un punto. La primera es el contenido en base64url de un JSON con los campos app, correo, id_externo, usuario_externo, jti, exp y portal. La segunda es la firma HMAC-SHA256 de la cadena formada por la palabra SSO, un salto de línea y la primera parte. Tras validar el token y crear la sesión, el conector redirige al usuario a la página de inicio de la aplicación.

## 4. Conjuntos de datos para el cuadro de mando

Cada aplicación decide qué conjuntos expone y con qué columnas. La regla es que sean consultas de solo lectura, sin datos personales innecesarios y con una columna de fecha cuando la haya, porque el portal la usa para construir las series mensuales. Los conjuntos iniciales sugeridos son los que muestra la Tabla 2. Sus nombres y columnas se acuerdan con el equipo del Observatorio una vez conocido el esquema real de cada aplicación.

| Aplicación | Conjunto | Columnas sugeridas |
|---|---|---|
| Solución Automatizada | usuarios | id, entidad, rol, fecha (registro), ultimo_acceso |
| Solución Automatizada | diagnosticos | id, entidad, fecha, estado, puntaje |
| Solución Automatizada | recomendaciones | id, diagnostico_id, categoria, fecha, aceptada |
| Catálogo de IA | usuarios | id, entidad, rol, fecha (registro) |
| Catálogo de IA | fichas | id, tipo, categoria, estado, fecha, entidad_proponente |
| Catálogo de IA | consultas | fecha, ficha_id, entidad (agregado por día) |

Tabla 2. Conjuntos de datos iniciales propuestos. Fuente. Elaboración propia.

Ya implementados en el Catálogo de IA, a partir de su esquema real, son cinco. Fichas del Catálogo Único de Oferta IA, herramientas publicadas, casos de éxito, usuarios del panel y consultas, estas últimas como visitas públicas agregadas por día y sección, sin direcciones IP ni agentes de navegador. Sus columnas exactas están en `catalogoia/servidor_observatorio.py`.

## 5. Implementación en cada aplicación

La implementación depende del lenguaje de la aplicación. La carpeta referencia-node contiene una versión completa para aplicaciones en Node.js que se conecta con cinco funciones que la aplicación provee. Buscar un usuario por su nombre o correo, verificar una clave con la rutina propia, buscar un usuario por identificador o correo, iniciar la sesión local y las consultas de cada conjunto. Para aplicaciones en otros lenguajes se escribe el equivalente siguiendo este documento, con la misma cadena de firma y las mismas respuestas, lo que se decide cuando se conozca la tecnología de cada aplicación.

La activación se controla con dos variables de configuración. OBS_CONECTOR_ACTIVO, que vale 1 para encender el conector y cualquier otra cosa para mantenerlo apagado, y OBS_CONECTOR_SECRETO, con el secreto compartido de esa aplicación. Con la variable de activación apagada el conector responde 404 a cualquier petición, lo que equivale a que no exista.

## 6. Procedimiento de instalación sin afectar la aplicación

La instalación se hace primero en una copia de la aplicación en el entorno de pruebas y solo después en el servidor real. En el servidor real el orden es copiar el archivo del conector sin montarlo, montarlo con la variable de activación apagada y comprobar que la aplicación responde igual que antes, definir el secreto, encender la variable de activación y comprobar desde el portal la acción de estado. Si en cualquier punto la aplicación deja de responder como antes, se apaga la variable de activación, con lo que el conector desaparece, y se revisa el caso en el entorno de pruebas. Nada de este procedimiento toca la base de datos de la aplicación ni sus archivos existentes.
