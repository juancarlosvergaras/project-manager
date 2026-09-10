// Lectura de hojas de cálculo sin dependencias: archivos .xlsx (la primera hoja) y .csv. Devuelve las filas como
// arreglos de textos. Sirve para importar las respuestas exportadas por los formularios anteriores del proyecto.
import zlib from 'node:zlib';

const decodificarXml = (s) => String(s).replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n))).replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16))).replace(/&amp;/g, '&');

// ---------------------------------------------------------------- zip
function entradasZip(buf) {
  const fin = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (fin < 0) throw new Error('El archivo no es un .xlsx válido.');
  const total = buf.readUInt16LE(fin + 10);
  let pos = buf.readUInt32LE(fin + 16);
  const out = {};
  for (let i = 0; i < total; i++) {
    if (buf.readUInt32LE(pos) !== 0x02014b50) break;
    const metodo = buf.readUInt16LE(pos + 10);
    const comprimido = buf.readUInt32LE(pos + 20);
    const tamano = buf.readUInt32LE(pos + 24);
    const nLargo = buf.readUInt16LE(pos + 28), eLargo = buf.readUInt16LE(pos + 30), cLargo = buf.readUInt16LE(pos + 32);
    const desplazamiento = buf.readUInt32LE(pos + 42);
    const nombre = buf.slice(pos + 46, pos + 46 + nLargo).toString('utf8');
    out[nombre] = { metodo, comprimido, tamano, desplazamiento };
    pos += 46 + nLargo + eLargo + cLargo;
  }
  return out;
}
function leerEntrada(buf, e) {
  const p = e.desplazamiento;
  if (buf.readUInt32LE(p) !== 0x04034b50) throw new Error('Entrada del zip dañada.');
  const nLargo = buf.readUInt16LE(p + 26), eLargo = buf.readUInt16LE(p + 28);
  const inicio = p + 30 + nLargo + eLargo;
  const datos = buf.slice(inicio, inicio + e.comprimido);
  if (e.metodo === 0) return datos;
  if (e.metodo === 8) return zlib.inflateRawSync(datos);
  throw new Error('Método de compresión no admitido en el .xlsx.');
}

// ---------------------------------------------------------------- xlsx
function columnaANumero(ref) {
  const letras = /^[A-Z]+/.exec(ref)[0];
  let n = 0;
  for (const ch of letras) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}
const fechaDeSerial = (n) => { const d = new Date(Date.UTC(1899, 11, 30) + Math.round(n * 86400000)); return d.toISOString().slice(0, 19).replace('T', ' '); };

export function leerXlsx(buf) {
  const entradas = entradasZip(buf);
  const texto = (nombre) => (entradas[nombre] ? leerEntrada(buf, entradas[nombre]).toString('utf8') : '');
  // Primera hoja según el libro.
  const libro = texto('xl/workbook.xml');
  const rels = texto('xl/_rels/workbook.xml.rels');
  let hoja = 'xl/worksheets/sheet1.xml';
  const primera = /<sheet [^>]*r:id="([^"]+)"/.exec(libro);
  if (primera) { const rel = new RegExp(`<Relationship [^>]*Id="${primera[1]}"[^>]*Target="([^"]+)"`).exec(rels) || new RegExp(`Target="([^"]+)"[^>]*Id="${primera[1]}"`).exec(rels); if (rel) hoja = 'xl/' + rel[1].replace(/^\/?xl\//, '').replace(/^\//, ''); }
  const compartidas = [];
  const ss = texto('xl/sharedStrings.xml');
  for (const m of ss.matchAll(/<si>([\s\S]*?)<\/si>/g)) compartidas.push(decodificarXml([...m[1].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map((x) => x[1]).join('')));
  const estilos = texto('xl/styles.xml');
  // Estilos de celda que son fechas: numFmtId de fecha (14-22, 45-47) o formatos propios con d/m/y.
  const propios = new Set([...estilos.matchAll(/<numFmt [^>]*numFmtId="(\d+)"[^>]*formatCode="([^"]*)"/g)].filter((m) => /[dmyh]/i.test(m[2].replace(/\[[^\]]*\]/g, '').replace(/"[^"]*"/g, '')) && !/#|0\.0/.test(m[2])).map((m) => Number(m[1])));
  const xfs = (estilos.split('<cellXfs')[1] || '').split('</cellXfs>')[0];
  const esFecha = [...xfs.matchAll(/<xf [^>]*numFmtId="(\d+)"/g)].map((m) => { const id = Number(m[1]); return (id >= 14 && id <= 22) || (id >= 45 && id <= 47) || propios.has(id); });
  const xml = texto(hoja);
  if (!xml) throw new Error('No se encontró la hoja de datos dentro del archivo.');
  const filas = [];
  for (const f of xml.matchAll(/<row[^>]*>([\s\S]*?)<\/row>/g)) {
    const fila = [];
    for (const c of f[1].matchAll(/<c r="([A-Z]+\d+)"([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
      const col = columnaANumero(c[1]);
      const attrs = c[2] || '';
      const cuerpo = c[3] || '';
      const tipo = (/t="([^"]+)"/.exec(attrs) || [])[1];
      const estilo = Number((/s="(\d+)"/.exec(attrs) || [, -1])[1]);
      let v = '';
      if (tipo === 's') v = compartidas[Number((/<v>([\s\S]*?)<\/v>/.exec(cuerpo) || [, ''])[1])] ?? '';
      else if (tipo === 'inlineStr') v = decodificarXml([...cuerpo.matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map((x) => x[1]).join(''));
      else if (tipo === 'b') v = (/<v>1<\/v>/.test(cuerpo) ? 'Sí' : 'No');
      else {
        const crudo = decodificarXml((/<v>([\s\S]*?)<\/v>/.exec(cuerpo) || [, ''])[1]);
        v = crudo;
        if (crudo !== '' && tipo !== 'str' && estilo >= 0 && esFecha[estilo] && !Number.isNaN(Number(crudo))) v = fechaDeSerial(Number(crudo));
      }
      fila[col] = String(v).trim();
    }
    for (let i = 0; i < fila.length; i++) if (fila[i] === undefined) fila[i] = '';
    filas.push(fila);
  }
  return filas;
}

// ---------------------------------------------------------------- csv
export function leerCsv(texto) {
  let t = String(texto);
  if (t.charCodeAt(0) === 0xfeff) t = t.slice(1);
  const primera = t.split(/\r?\n/)[0] || '';
  const sep = (primera.match(/;/g) || []).length >= (primera.match(/,/g) || []).length ? ';' : (primera.includes('\t') ? '\t' : ',');
  const filas = []; let fila = [], campo = '', comillas = false;
  for (let i = 0; i < t.length; i++) {
    const ch = t[i];
    if (comillas) { if (ch === '"') { if (t[i + 1] === '"') { campo += '"'; i++; } else comillas = false; } else campo += ch; continue; }
    if (ch === '"') comillas = true;
    else if (ch === sep) { fila.push(campo.trim()); campo = ''; }
    else if (ch === '\n') { fila.push(campo.trim()); campo = ''; if (fila.some((x) => x !== '')) filas.push(fila); fila = []; }
    else if (ch !== '\r') campo += ch;
  }
  fila.push(campo.trim());
  if (fila.some((x) => x !== '')) filas.push(fila);
  return filas;
}

// Devuelve {columnas, filas} a partir del archivo, detectando la fila de encabezados (la primera con más de una celda con texto).
export function leerHoja(buf, nombreArchivo = '') {
  const filas = /\.xlsx$/i.test(nombreArchivo) || (buf.length > 4 && buf.readUInt32LE(0) === 0x04034b50) ? leerXlsx(buf) : leerCsv(buf.toString('utf8'));
  const iCab = filas.findIndex((f) => f.filter((x) => x !== '').length > 1);
  if (iCab < 0) return { columnas: [], filas: [] };
  const columnas = filas[iCab].map((x) => String(x).trim());
  const ancho = columnas.length;
  const datos = filas.slice(iCab + 1).map((f) => { const out = f.slice(0, ancho); while (out.length < ancho) out.push(''); return out; }).filter((f) => f.some((x) => x !== ''));
  return { columnas, filas: datos };
}
