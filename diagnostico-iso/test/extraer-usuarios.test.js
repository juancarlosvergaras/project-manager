import { test } from 'node:test';
import assert from 'node:assert/strict';
process.env.SESSION_SECRET = 'x';
const { extraerUsuarios } = await import('../server/auth.js');

test('lista simple', () => { assert.equal(extraerUsuarios([{ usuario: 'a', rol: 'admin' }, { usuario: 'b', nombre: 'B' }]).length, 2); });
test('objeto con lista', () => { assert.equal(extraerUsuarios({ version: 1, usuarios: [{ correo: 'a@x', rol: 'admin' }] }).length, 1); });
test('objeto con diccionario de usuarios', () => {
  const l = extraerUsuarios({ proyecto: { nombre: 'Proyecto IA para el Estado', anio: 2026 }, usuarios: { 'admin@mintic1519.local': { nombre: 'Admin', rol: 'admin', clave_hash: 'x' }, 'ana@x': { nombre: 'Ana', rol: 'consulta', clave_hash: 'y' } } });
  assert.equal(l.length, 2); assert.equal(l[0].usuario, 'admin@mintic1519.local'); assert.equal(l[1].nombre, 'Ana');
});
test('diccionario en la raíz e ignora registros que no son usuarios', () => {
  const l = extraerUsuarios({ 'admin@x': { nombre: 'A', rol: 'admin', salt: 's', hash: 'h' }, 'luis@x': { nombre: 'L', rol: 'gestor', salt: 's', hash: 'h' }, config: { tema: 'oscuro' } });
  assert.equal(l.length, 2);
});
test('anidado en cuentas', () => { assert.equal(extraerUsuarios({ datos: { cuentas: [{ login: 'u1', password_hash: 'p' }] } }).length, 1); });
