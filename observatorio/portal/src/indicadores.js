// Marco de medicion del Observatorio. Reproduce el instrumento de diagnostico de preparacion (documento F1)
// y el sistema de indicadores por dimension (documento F10), y calcula lo que ya puede calcularse con los
// conjuntos de datos recolectados de las aplicaciones. Lo que aun no tiene fuente se muestra como pendiente.

// ---- Escala unificada de cinco niveles (F1, Tabla 5; F10, capitulo 6) ----
export const NIVELES = [
  { n: 1, nombre: 'Inicial', desde: 1.0, hasta: 1.79, mmcyti: 'Nivel 1. Sin evidencia de adelantos', ruta: 'Fortalecimiento' },
  { n: 2, nombre: 'Gestionado', desde: 1.8, hasta: 2.59, mmcyti: 'Nivel 2. Necesidad identificada', ruta: 'Fortalecimiento' },
  { n: 3, nombre: 'Definido', desde: 2.6, hasta: 3.39, mmcyti: 'Nivel 3. Capacidad en nivel básico', ruta: 'Pilotaje' },
  { n: 4, nombre: 'Avanzado', desde: 3.4, hasta: 4.19, mmcyti: 'Nivel 4. Capacidad en nivel intermedio', ruta: 'Escalamiento' },
  { n: 5, nombre: 'Optimizado', desde: 4.2, hasta: 5.0, mmcyti: 'Nivel 5. Capacidad en actualización constante', ruta: 'Escalamiento' },
];
export function nivelDe(puntaje) {
  if (puntaje == null || Number.isNaN(puntaje)) return null;
  return NIVELES.find((n) => puntaje >= n.desde && puntaje <= n.hasta + 0.0001) || (puntaje > 5 ? NIVELES[4] : NIVELES[0]);
}

// ---- F1. Instrumento de diagnostico de preparacion institucional para IA (Tabla 6): 6 ambitos x 4 criterios ----
export const F1 = {
  titulo: 'Diagnóstico de preparación institucional para IA',
  fuente: 'Kit de diagnóstico digital de preparación para IA. Universidad de Cartagena y MinTIC, 2026.',
  escala: '0 = No cuenta o no aplica (se excluye del cálculo) · 1 = Inicial · 2 = Gestionado · 3 = Definido · 4 = Avanzado · 5 = Optimizado',
  calculo: 'Promedio del ámbito = suma de criterios calificados ÷ número de criterios calificados. Promedio institucional = promedio de los seis ámbitos. Indicador de dispersión = promedio máximo menos promedio mínimo entre ámbitos.',
  ambitos: [
    { codigo: 'DG', nombre: 'Dirección y gobierno institucional', eje: 'Institucionalidad e innovación', criterios: [
      ['DG1', 'La entidad integra el uso de datos y la IA dentro de su planeación, arquitectura empresarial o portafolio de transformación digital.'],
      ['DG2', 'La entidad asigna responsables para liderazgo de datos, tecnología, seguridad y validación misional de las iniciativas.'],
      ['DG3', 'La entidad cuenta con una instancia que prioriza casos de uso, revisa avances y adopta acuerdos de seguimiento.'],
      ['DG4', 'La entidad aplica criterios para revisar riesgos, transparencia, supervisión humana e impactos del uso de IA.']] },
    { codigo: 'DA', nombre: 'Gestión de datos', eje: 'Analítica y gestión de los datos', criterios: [
      ['DA1', 'La entidad dispone de inventario, clasificación y responsables de los conjuntos de datos asociados a procesos prioritarios.'],
      ['DA2', 'La entidad aplica rutinas de calidad, actualización y control sobre los datos que prevé utilizar en analítica o IA.'],
      ['DA3', 'La entidad usa estándares, metadatos e intercambios que facilitan interoperabilidad y reutilización de la información.'],
      ['DA4', 'La entidad gestiona accesos y trazabilidad para consulta, uso, modificación y compartición de datos.']] },
    { codigo: 'TE', nombre: 'Base tecnológica', eje: 'Infraestructura digital e interoperabilidad. Tecnología y estándares', criterios: [
      ['TE1', 'La arquitectura tecnológica soporta integración entre sistemas, datos y herramientas analíticas.'],
      ['TE2', 'La entidad dispone de capacidad de almacenamiento y procesamiento acorde con sus casos de uso prioritarios.'],
      ['TE3', 'La entidad cuenta con herramientas para análisis, visualización, modelado o automatización con uso controlado.'],
      ['TE4', 'La entidad dispone de ambientes y soporte operativo para desarrollo, prueba, puesta en producción y mantenimiento.']] },
    { codigo: 'SP', nombre: 'Seguridad y privacidad', eje: 'Infraestructura digital e interoperabilidad', criterios: [
      ['SP1', 'La entidad aplica controles de seguridad y gestión de riesgos alineados con su marco institucional.'],
      ['SP2', 'La entidad gestiona datos personales e información sensible con criterios de privacidad, minimización y anonimización cuando corresponde.'],
      ['SP3', 'La entidad controla perfiles, accesos y monitoreo sobre los activos de información usados en analítica o IA.'],
      ['SP4', 'La entidad cuenta con medidas de continuidad, respaldo y respuesta a incidentes para servicios y datos críticos.']] },
    { codigo: 'TH', nombre: 'Capacidades del equipo humano', eje: 'Liderazgo y capital humano', criterios: [
      ['TH1', 'La entidad dispone de perfiles o roles asociados a datos, tecnología, seguridad y gestión misional del proyecto.'],
      ['TH2', 'La entidad desarrolla formación en datos, gobierno digital, seguridad e IA para los equipos involucrados.'],
      ['TH3', 'La entidad articula trabajo interdisciplinario entre áreas misionales, jurídicas, técnicas y directivas.'],
      ['TH4', 'La entidad conserva lecciones aprendidas y mecanismos de transferencia de conocimiento.']] },
    { codigo: 'PV', nombre: 'Procesos y valor público', eje: 'Transversal a los cinco ejes', criterios: [
      ['PV1', 'La entidad prioriza casos de uso con criterio de pertinencia, disponibilidad de datos y aporte a la misión institucional.'],
      ['PV2', 'Los procesos vinculados al caso de uso están descritos y cuentan con reglas de negocio suficientemente claras.'],
      ['PV3', 'La entidad define indicadores para medir beneficios, calidad del servicio, tiempos, cobertura o valor público.'],
      ['PV4', 'La entidad gestiona cambios organizacionales, comunicación y apropiación de los resultados por parte de usuarios internos o ciudadanía.']] },
  ],
};

// Calcula el diagnostico F1 de una entidad a partir de sus respuestas {DG1: 3, DG2: 0, ...}. Se usara cuando
// el modulo de cuestionarios aplique el instrumento. El 0 se excluye del calculo, como manda el documento.
export function calcularF1(respuestas) {
  const ambitos = F1.ambitos.map((a) => {
    const vals = a.criterios.map(([c]) => Number(respuestas[c])).filter((v) => v >= 1 && v <= 5);
    const prom = vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;
    return { codigo: a.codigo, nombre: a.nombre, promedio: prom, nivel: nivelDe(prom), calificados: vals.length };
  });
  const validos = ambitos.filter((a) => a.promedio != null);
  const global = validos.length ? validos.reduce((s, a) => s + a.promedio, 0) / validos.length : null;
  const dispersion = validos.length ? Math.max(...validos.map((a) => a.promedio)) - Math.min(...validos.map((a) => a.promedio)) : null;
  return { ambitos, global, nivel: nivelDe(global), dispersion, lecturaDispersion: dispersion == null ? '' : dispersion <= 1 ? 'Perfil relativamente equilibrado' : dispersion <= 2 ? 'Desbalances moderados' : 'Desbalances pronunciados que requieren intervención prioritaria' };
}

// ---- F10. Sistema de indicadores por dimension (Tablas 3 a 8) ----
export const F10 = {
  titulo: 'Sistema de indicadores de adopción y uso de IA en el sector público',
  fuente: 'Sistema de indicadores y modelo de seguimiento a la madurez en IA. Universidad de Cartagena y MinTIC, 2026.',
  indice: 'Índice de Adopción de IA en el Sector Público (IASP). Índice compuesto en escala de 0 a 100 que agrega las seis dimensiones. Se publica solo cuando la cobertura y la calidad superan los umbrales aprobados, acompañado de las condiciones críticas, los datos faltantes y el número de sistemas registrados.',
  instrumentos: 'Encuesta Nacional de Adopción de IA en el Sector Público (ENAIASP), que incorpora el diagnóstico de preparación, y Registro Nacional de Sistemas de IA en el Sector Público (RNAIASP). Las fuentes automáticas, incluida la Solución Automatizada de la Resolución 1519, se usan como evidencia complementaria.',
  dimensiones: [
    { codigo: 'D1', nombre: 'Estrategia y gobernanza', pregunta: '¿La entidad dirige y controla la IA con responsabilidades y decisiones formales?', unidad: 'Entidad', indicadores: [
      { codigo: 'D1.1', nombre: 'Entidades con instancia formal de gobierno de IA', formula: 'Entidades con acto o función formal / entidades medidas × 100', fuente: 'ENAIASP y evidencia documental', frecuencia: 'Anual', desagregacion: 'Orden, sector, territorio' },
      { codigo: 'D1.2', nombre: 'Casos de uso con dueño y decisión documentada', formula: 'Casos con dueño y acta / casos activos × 100', fuente: 'RNAIASP', frecuencia: 'Semestral', desagregacion: 'Entidad, nivel de riesgo' },
      { codigo: 'D1.3', nombre: 'Cumplimiento de hitos de gobierno del ciclo de vida', formula: 'Hitos cumplidos / hitos aplicables × 100', fuente: 'Expedientes de control de caso', frecuencia: 'Semestral', desagregacion: 'Entidad, etapa' }] },
    { codigo: 'D2', nombre: 'Talento y capacidades', pregunta: '¿Dispone de equipos, formación y uso competente?', unidad: 'Entidad y persona', indicadores: [
      { codigo: 'D2.1', nombre: 'Cobertura de formación por rol', formula: 'Personas formadas / personas objetivo × 100', fuente: 'Registros de formación', frecuencia: 'Semestral', desagregacion: 'Rol, entidad, territorio' },
      { codigo: 'D2.2', nombre: 'Apropiación demostrada', formula: 'Participantes que superan el ejercicio / participantes evaluados × 100', fuente: 'Evaluación práctica', frecuencia: 'Por cohorte', desagregacion: 'Rol y modalidad' },
      { codigo: 'D2.3', nombre: 'Disponibilidad de roles críticos', formula: 'Roles cubiertos / roles requeridos × 100', fuente: 'ENAIASP y estructura del proyecto', frecuencia: 'Anual', desagregacion: 'Entidad y tipo de caso' }] },
    { codigo: 'D3', nombre: 'Datos e infraestructura', pregunta: '¿Cuenta con datos, arquitectura, seguridad y capacidad operativa?', unidad: 'Entidad y activo', indicadores: [
      { codigo: 'D3.1', nombre: 'Fuentes de IA con responsable y ficha de calidad', formula: 'Fuentes completas / fuentes usadas × 100', fuente: 'Catálogo y perfilamiento', frecuencia: 'Trimestral', desagregacion: 'Entidad, sistema' },
      { codigo: 'D3.2', nombre: 'Disponibilidad de servicios de IA', formula: 'Minutos disponibles / minutos programados × 100', fuente: 'Monitoreo', frecuencia: 'Mensual', desagregacion: 'Sistema, ambiente' },
      { codigo: 'D3.3', nombre: 'Casos con arquitectura y plan de continuidad aprobados', formula: 'Casos conformes / casos activos × 100', fuente: 'Expediente técnico', frecuencia: 'Semestral', desagregacion: 'Entidad, riesgo' },
      { codigo: 'D3.4', nombre: 'Tiempo medio de recuperación', formula: 'Suma de horas de recuperación / incidentes cerrados', fuente: 'Gestión de incidentes', frecuencia: 'Mensual', desagregacion: 'Sistema, severidad' }] },
    { codigo: 'D4', nombre: 'Implementación y adopción', pregunta: '¿Existen soluciones en uso y con qué cobertura?', unidad: 'Sistema o caso de uso', indicadores: [
      { codigo: 'D4.1', nombre: 'Casos de uso por etapa', formula: 'Conteo por identificación, piloto, producción, suspendido o retirado', fuente: 'RNAIASP', frecuencia: 'Trimestral', desagregacion: 'Entidad, sector, territorio' },
      { codigo: 'D4.2', nombre: 'Tasa de paso de piloto a producción', formula: 'Pilotos en producción / pilotos cerrados × 100', fuente: 'RNAIASP', frecuencia: 'Anual', desagregacion: 'Tipo y riesgo' },
      { codigo: 'D4.3', nombre: 'Uso activo', formula: 'Usuarios activos / usuarios habilitados × 100', fuente: 'Analítica de servicio', frecuencia: 'Mensual', desagregacion: 'Sistema, rol, territorio' },
      { codigo: 'D4.4', nombre: 'Cobertura del proceso', formula: 'Transacciones apoyadas / transacciones elegibles × 100', fuente: 'Sistema misional', frecuencia: 'Mensual', desagregacion: 'Servicio y canal' }] },
    { codigo: 'D5', nombre: 'Ética, riesgos y derechos', pregunta: '¿Los riesgos se identifican, tratan y monitorean?', unidad: 'Sistema y entidad', indicadores: [
      { codigo: 'D5.1', nombre: 'Casos con evaluación de riesgo vigente', formula: 'Casos con evaluación vigente / casos activos × 100', fuente: 'Expediente de riesgo', frecuencia: 'Trimestral', desagregacion: 'Riesgo, entidad' },
      { codigo: 'D5.2', nombre: 'Controles críticos probados', formula: 'Controles aprobados / controles críticos aplicables × 100', fuente: 'Plan de pruebas', frecuencia: 'Por versión', desagregacion: 'Sistema y control' },
      { codigo: 'D5.3', nombre: 'Tasa de incidentes relevantes', formula: 'Incidentes relevantes / 10.000 transacciones', fuente: 'Incidentes y operación', frecuencia: 'Mensual', desagregacion: 'Tipo, severidad' },
      { codigo: 'D5.4', nombre: 'Brecha máxima de desempeño entre grupos', formula: 'Máximo absoluto de diferencia de la métrica acordada', fuente: 'Informe de evaluación', frecuencia: 'Por versión', desagregacion: 'Sistema y grupo protegido' },
      { codigo: 'D5.5', nombre: 'Reclamaciones resueltas dentro del plazo', formula: 'Reclamaciones oportunas / reclamaciones cerradas × 100', fuente: 'Servicio al ciudadano', frecuencia: 'Trimestral', desagregacion: 'Sistema y resultado' }] },
    { codigo: 'D6', nombre: 'Impacto y valor público', pregunta: '¿Las soluciones mejoran resultados y para quién?', unidad: 'Sistema y servicio', indicadores: [
      { codigo: 'D6.1', nombre: 'Variación del tiempo del proceso', formula: '(Tiempo base − tiempo actual) / tiempo base × 100', fuente: 'Sistema misional', frecuencia: 'Trimestral', desagregacion: 'Servicio, entidad' },
      { codigo: 'D6.2', nombre: 'Variación del error del proceso', formula: '(Error base − error actual) / error base × 100', fuente: 'Control de calidad', frecuencia: 'Trimestral', desagregacion: 'Servicio, tipo de error' },
      { codigo: 'D6.3', nombre: 'Beneficio neto estimado', formula: 'Beneficios monetizados − costo total', fuente: 'Evaluación económica', frecuencia: 'Anual', desagregacion: 'Sistema' },
      { codigo: 'D6.4', nombre: 'Satisfacción de usuarios', formula: 'Respuestas favorables / respuestas válidas × 100', fuente: 'Encuesta con ficha', frecuencia: 'Semestral', desagregacion: 'Usuario, canal' },
      { codigo: 'D6.5', nombre: 'Casos con evaluación de resultado', formula: 'Casos evaluados / casos productivos con antigüedad mínima × 100', fuente: 'RNAIASP e informes', frecuencia: 'Anual', desagregacion: 'Entidad y sector' }] },
  ],
};

// ---- Calculo con los datos ya recolectados ----
// `resumen` es la salida de resumenTablero(): [{app, conjuntos:[{conjunto, filas, muestra, ...}]}]. Para calcular
// hace falta el detalle completo de filas, que llega en `datos` como {app: {conjunto: [filas]}}.
export function calcularIndicadores(datos) {
  const cat = datos.catalogo || {};
  const sol = datos.solucion || {};
  const fichas = cat.fichas || [];
  const casos = cat.casos || [];
  const herramientas = cat.herramientas || [];
  const entidades = sol.entidades || [];
  const evaluaciones = sol.evaluaciones || [];
  const consolidaciones = sol.consolidaciones || [];

  const valores = {};
  // D4.1 Casos de uso por etapa. Fuente disponible: fichas del Catalogo Unico de Oferta IA por estado.
  if (fichas.length) {
    const porEstado = {};
    for (const f of fichas) { const e = String(f.estado || 'sin estado'); porEstado[e] = (porEstado[e] || 0) + 1; }
    valores['D4.1'] = { valor: fichas.length, unidad: 'fichas', detalle: porEstado, fuente: 'Catálogo de IA · fichas', nota: 'Conteo de fichas del Catálogo por estado. El RNAIASP sustituirá esta fuente cuando entre en operación.' };
  }
  // D6.5 aproximacion: casos de exito documentados sobre fichas.
  if (fichas.length && casos.length) {
    valores['D6.5'] = { valor: Math.round(casos.length / fichas.length * 1000) / 10, unidad: '%', detalle: { casos_documentados: casos.length, fichas: fichas.length }, fuente: 'Catálogo de IA · casos y fichas', nota: 'Aproximación. Casos de éxito documentados sobre fichas publicadas, a falta de la evaluación formal de resultado.' };
  }
  // Evidencia complementaria de la Resolucion 1519 (F10, capitulo 8): cobertura y puntaje de cumplimiento web.
  let r1519 = null;
  if (entidades.length || evaluaciones.length) {
    const conEval = new Set(evaluaciones.map((e) => e.entidad_id));
    const punt = evaluaciones.map((e) => Number(e.puntaje)).filter((p) => !Number.isNaN(p));
    const prom = punt.length ? punt.reduce((s, p) => s + p, 0) / punt.length : null;
    const porDepto = {};
    for (const e of entidades) { const d = e.departamento || 'Sin departamento'; porDepto[d] = porDepto[d] || { entidades: 0, evaluadas: 0 }; porDepto[d].entidades++; if (conEval.has(e.id)) porDepto[d].evaluadas++; }
    r1519 = { entidades: entidades.length, evaluadas: conEval.size, evaluaciones: evaluaciones.length, promedio: prom == null ? null : Math.round(prom * 1000) / 10, consolidaciones: consolidaciones.length, porDepto };
  }
  const herramientasPorCategoria = {};
  for (const h of herramientas) { const c = h.categoria || 'Sin categoría'; herramientasPorCategoria[c] = (herramientasPorCategoria[c] || 0) + 1; }

  const total = F10.dimensiones.reduce((s, d) => s + d.indicadores.length, 0);
  return { valores, conDatos: Object.keys(valores).length, total, r1519, herramientasPorCategoria, herramientas: herramientas.length, fichas: fichas.length, casos: casos.length };
}
