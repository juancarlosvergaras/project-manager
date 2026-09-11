import { test } from 'node:test';
import assert from 'node:assert/strict';
import { calcularIndicadores, compararVersiones, nivelMadurez, cmpNumeral } from '../server/scoring.js';

const items = [
  { id: 'a', codigo: 'ISO-001', capitulo: 4, capitulo_nombre: 'Contexto', numeral: '4.1', pregunta: 'P1', responsable_sugerido: 'Calidad', orden: 1 },
  { id: 'b', codigo: 'ISO-002', capitulo: 4, capitulo_nombre: 'Contexto', numeral: '4.2', pregunta: 'P2', responsable_sugerido: 'Calidad', orden: 2 },
  { id: 'c', codigo: 'ISO-003', capitulo: 5, capitulo_nombre: 'Liderazgo', numeral: '5.1.1', pregunta: 'P3', responsable_sugerido: 'Gerencia', orden: 3 },
  { id: 'd', codigo: 'ISO-004', capitulo: 5, capitulo_nombre: 'Liderazgo', numeral: '5.1.2', pregunta: 'P4', responsable_sugerido: 'Gerencia', orden: 4 },
];

test('pondera cumple=1, parcial=0.5, no cumple y sin evidencia=0', () => {
  const r = new Map([['a', { valoracion: 'cumple' }], ['b', { valoracion: 'cumple_parcial' }], ['c', { valoracion: 'no_cumple' }], ['d', { valoracion: 'sin_evidencia' }]]);
  const ind = calcularIndicadores(items, r);
  assert.equal(ind.cumplimiento, 37.5);
  assert.equal(ind.brecha_total, 62.5);
  assert.equal(ind.avance_diligenciamiento, 100);
  assert.equal(ind.items_para_cumplir, 3);
  assert.deepEqual(ind.por_capitulo.map(c => c.cumplimiento), [75, 0]);
  assert.equal(ind.capitulo_critico.capitulo, 5);
  assert.equal(ind.nivel.nombre, 'Básico');
});

test('las preguntas sin valorar cuentan como brecha y reducen el avance', () => {
  const ind = calcularIndicadores(items, new Map([['a', { valoracion: 'cumple' }]]));
  assert.equal(ind.conteo.sin_valorar, 3);
  assert.equal(ind.avance_diligenciamiento, 25);
  assert.equal(ind.cumplimiento, 25);
  assert.equal(ind.brecha.filter(b => b.prioridad === 'alta').length, 3);
});

test('prioriza brecha alta antes que media y respeta el orden de numerales', () => {
  const r = new Map([['a', { valoracion: 'cumple_parcial' }], ['b', { valoracion: 'no_cumple' }], ['c', { valoracion: 'cumple' }], ['d', { valoracion: 'cumple_parcial' }]]);
  const ind = calcularIndicadores(items, r);
  assert.deepEqual(ind.brecha.map(b => b.codigo), ['ISO-002', 'ISO-001', 'ISO-004']);
});

test('niveles de madurez', () => {
  assert.equal(nivelMadurez(0).nombre, 'Inicial');
  assert.equal(nivelMadurez(50).nombre, 'En desarrollo');
  assert.equal(nivelMadurez(90).nombre, 'Listo para certificación');
});

test('comparación entre versiones calcula deltas', () => {
  const a = calcularIndicadores(items, new Map([['a', { valoracion: 'no_cumple' }]]));
  const b = calcularIndicadores(items, new Map([['a', { valoracion: 'cumple' }], ['b', { valoracion: 'cumple' }]]));
  const c = compararVersiones(a, b);
  assert.equal(c.cumplimiento.delta, 50);
  assert.equal(c.por_capitulo[0].delta, 100);
});

test('orden natural de numerales ISO', () => {
  assert.deepEqual(['8.5.1', '8.2.3.1', '10.1', '8.10', '8.2'].sort(cmpNumeral), ['8.2', '8.2.3.1', '8.5.1', '8.10', '10.1']);
});
