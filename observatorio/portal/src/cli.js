// Utilidades de linea de comandos. Uso: node src/cli.js recolectar
import { config } from './config.js';
import { recolectarTodo } from './recolector.js';

const [, , orden] = process.argv;
if (orden === 'recolectar') {
  const r = await recolectarTodo();
  console.log(JSON.stringify(r, null, 2));
} else if (orden === 'apps') {
  console.log(config.apps.map((a) => ({ clave: a.clave, nombre: a.nombre, conector: a.conector })));
} else {
  console.log('Órdenes disponibles. recolectar, apps');
}
