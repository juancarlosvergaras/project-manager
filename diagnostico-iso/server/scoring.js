// Cálculo de indicadores del diagnóstico y de la brecha frente a ISO 9001.
import { VALORACIONES } from './db.js';

export const NIVELES = [
  { min: 90, nombre: 'Listo para certificación', descripcion: 'El sistema cumple de forma sustancial los requisitos. Procede auditoría interna completa y revisión por la dirección previa a la auditoría de certificación.' },
  { min: 75, nombre: 'Avanzado', descripcion: 'Requisitos mayoritariamente cumplidos. Quedan brechas puntuales que deben cerrarse con acciones de corto plazo.' },
  { min: 50, nombre: 'En desarrollo', descripcion: 'Existe una base documental y operativa, con vacíos relevantes en varios capítulos de la norma.' },
  { min: 25, nombre: 'Básico', descripcion: 'Cumplimiento fragmentado. Se requiere un plan de implementación estructurado con responsables y plazos.' },
  { min: 0,  nombre: 'Inicial', descripcion: 'El sistema de gestión de la calidad no está implementado o carece de evidencia verificable.' },
];

export function nivelMadurez(pct) {
  return NIVELES.find(n => pct >= n.min) ?? NIVELES[NIVELES.length - 1];
}

/**
 * items: [{id, codigo, capitulo, capitulo_nombre, numeral, pregunta, responsable_sugerido, orden}]
 * respuestas: Map itemId -> {valoracion, evidencia, observaciones, responsable, estado_origen}
 */
export function calcularIndicadores(items, respuestas) {
  const conteo = { cumple: 0, cumple_parcial: 0, no_cumple: 0, no_aplica: 0, sin_valorar: 0 };
  const capitulos = new Map();
  const numerales = new Map();
  const responsables = new Map();
  let puntos = 0, aplicables = 0;
  const brecha = [];

  for (const it of items) {
    const r = respuestas.get(it.id) ?? {};
    const v = r.valoracion && VALORACIONES[r.valoracion] ? r.valoracion : null;
    const aplica = !v || VALORACIONES[v].aplica;       // "no aplica" sale del denominador
    const peso = v ? VALORACIONES[v].peso : 0;
    if (v) conteo[v]++; else conteo.sin_valorar++;
    if (aplica) { puntos += peso; aplicables++; }

    const cap = capitulos.get(it.capitulo) ?? { capitulo: it.capitulo, nombre: it.capitulo_nombre, total: 0, aplicables: 0, puntos: 0, cumple: 0, cumple_parcial: 0, no_cumple: 0, no_aplica: 0, sin_valorar: 0 };
    cap.total++; cap[v ?? 'sin_valorar']++; if (aplica) { cap.puntos += peso; cap.aplicables++; }
    capitulos.set(it.capitulo, cap);

    const num = numerales.get(it.numeral) ?? { numeral: it.numeral, capitulo: it.capitulo, total: 0, aplicables: 0, puntos: 0, cumple: 0, cumple_parcial: 0, no_cumple: 0, no_aplica: 0, sin_valorar: 0 };
    num.total++; num[v ?? 'sin_valorar']++; if (aplica) { num.puntos += peso; num.aplicables++; }
    numerales.set(it.numeral, num);

    const resp = (r.responsable || it.responsable_sugerido || 'Sin asignar').trim();
    const rs = responsables.get(resp) ?? { responsable: resp, total: 0, aplicables: 0, puntos: 0, pendientes: 0 };
    rs.total++; if (aplica) { rs.puntos += peso; rs.aplicables++; if (peso < 1) rs.pendientes++; }
    responsables.set(resp, rs);

    if (aplica && peso < 1) {
      brecha.push({
        item_id: it.id, codigo: it.codigo, capitulo: it.capitulo, numeral: it.numeral, pregunta: it.pregunta,
        valoracion: v, etiqueta: v ? VALORACIONES[v].etiqueta : 'Sin valorar',
        prioridad: v === 'cumple_parcial' ? 'media' : 'alta',
        responsable: resp, observaciones: r.observaciones ?? '', evidencia: r.evidencia ?? '', estado_origen: r.estado_origen ?? null,
      });
    }
  }

  const total = items.length;
  const pct = aplicables ? round(100 * puntos / aplicables) : 0;
  const porCapitulo = [...capitulos.values()].sort((a, b) => a.capitulo - b.capitulo).map(c => ({ ...c, cumplimiento: c.aplicables ? round(100 * c.puntos / c.aplicables) : 0, brecha: c.aplicables ? round(100 - 100 * c.puntos / c.aplicables) : 0 }));
  const porNumeral = [...numerales.values()].sort((a, b) => cmpNumeral(a.numeral, b.numeral)).map(n => ({ ...n, cumplimiento: n.aplicables ? round(100 * n.puntos / n.aplicables) : 0 }));
  const porResponsable = [...responsables.values()].map(r => ({ ...r, cumplimiento: r.aplicables ? round(100 * r.puntos / r.aplicables) : 0 })).sort((a, b) => b.pendientes - a.pendientes);
  const valorados = total - conteo.sin_valorar;

  return {
    total_items: total,
    items_aplicables: aplicables,
    items_valorados: valorados,
    avance_diligenciamiento: total ? round(100 * valorados / total) : 0,
    cumplimiento: pct,
    brecha_total: round(100 - pct),
    nivel: nivelMadurez(pct),
    conteo,
    distribucion: Object.keys(VALORACIONES).map(k => ({ clave: k, etiqueta: VALORACIONES[k].etiqueta, cantidad: conteo[k], porcentaje: total ? round(100 * conteo[k] / total) : 0 })),
    por_capitulo: porCapitulo,
    por_numeral: porNumeral,
    por_responsable: porResponsable,
    capitulo_critico: porCapitulo.length ? porCapitulo.reduce((m, c) => c.cumplimiento < m.cumplimiento ? c : m) : null,
    brecha: brecha.sort((a, b) => (a.prioridad === b.prioridad ? 0 : a.prioridad === 'alta' ? -1 : 1) || a.capitulo - b.capitulo || cmpNumeral(a.numeral, b.numeral)),
    items_para_cumplir: brecha.length,
    puntos_faltantes: round(aplicables - puntos, 1),
  };
}

export function compararVersiones(indA, indB) {
  const caps = new Map(indA.por_capitulo.map(c => [c.capitulo, c]));
  return {
    cumplimiento: { antes: indA.cumplimiento, despues: indB.cumplimiento, delta: round(indB.cumplimiento - indA.cumplimiento) },
    por_capitulo: indB.por_capitulo.map(c => {
      const a = caps.get(c.capitulo);
      return { capitulo: c.capitulo, nombre: c.nombre, antes: a ? a.cumplimiento : null, despues: c.cumplimiento, delta: a ? round(c.cumplimiento - a.cumplimiento) : null };
    }),
    conteo: Object.keys(indB.conteo).map(k => ({ clave: k, antes: indA.conteo[k], despues: indB.conteo[k], delta: indB.conteo[k] - indA.conteo[k] })),
  };
}

function round(x, d = 1) { const f = 10 ** d; return Math.round(x * f) / f; }
export function cmpNumeral(a, b) {
  const pa = String(a).split('.').map(Number), pb = String(b).split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d) return d;
  }
  return 0;
}
