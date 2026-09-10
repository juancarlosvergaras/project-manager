// Generador de códigos QR sin dependencias (modo bytes, corrección M por omisión, versiones 1 a 40, elección
// automática de máscara). Devuelve la matriz de módulos o directamente un SVG. Basado en el algoritmo de
// referencia de la especificación ISO/IEC 18004 (estructura similar a la biblioteca "qrcodegen" de Project Nayuki).

const NIVELES = { L: [1, 0], M: [0, 1], Q: [3, 2], H: [2, 3] }; // [bits de formato, índice de tabla]
const ECC_POR_BLOQUE = [
  [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
  [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
];
const BLOQUES = [
  [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
  [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
  [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68],
  [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81],
];

function modulosDeDatosCrudos(version) {
  let r = (16 * version + 128) * version + 64;
  if (version >= 2) { const n = Math.floor(version / 7) + 2; r -= (25 * n - 10) * n - 55; if (version >= 7) r -= 36; }
  return r;
}
const bytesDeDatos = (version, ec) => Math.floor(modulosDeDatosCrudos(version) / 8) - ECC_POR_BLOQUE[ec][version] * BLOQUES[ec][version];

// ---------------------------------------------------------------- Reed-Solomon en GF(256)
function multiplicar(x, y) { let z = 0; for (let i = 7; i >= 0; i--) { z = (z << 1) ^ ((z >>> 7) * 0x11d); z ^= ((y >>> i) & 1) * x; } return z & 0xff; }
function divisorRs(grado) {
  const r = new Array(grado).fill(0); r[grado - 1] = 1;
  let raiz = 1;
  for (let i = 0; i < grado; i++) { for (let j = 0; j < grado; j++) { r[j] = multiplicar(r[j], raiz); if (j + 1 < grado) r[j] ^= r[j + 1]; } raiz = multiplicar(raiz, 2); }
  return r;
}
function restoRs(datos, divisor) {
  const r = new Array(divisor.length).fill(0);
  for (const b of datos) { const f = b ^ r.shift(); r.push(0); divisor.forEach((c, i) => { r[i] ^= multiplicar(c, f); }); }
  return r;
}

// ---------------------------------------------------------------- codificación
function codificarDatos(bytes, version, ec) {
  const bits = [];
  const poner = (v, n) => { for (let i = n - 1; i >= 0; i--) bits.push((v >>> i) & 1); };
  poner(4, 4); // modo bytes
  poner(bytes.length, version < 10 ? 8 : 16);
  for (const b of bytes) poner(b, 8);
  const capacidad = bytesDeDatos(version, ec) * 8;
  poner(0, Math.min(4, capacidad - bits.length));
  while (bits.length % 8) bits.push(0);
  for (let pad = 0xec; bits.length < capacidad; pad ^= 0xec ^ 0x11) poner(pad, 8);
  const datos = [];
  for (let i = 0; i < bits.length; i += 8) datos.push(parseInt(bits.slice(i, i + 8).join(''), 2));
  // División en bloques con corrección de errores e intercalado.
  const numBloques = BLOQUES[ec][version], eccLen = ECC_POR_BLOQUE[ec][version];
  const totalCodewords = Math.floor(modulosDeDatosCrudos(version) / 8);
  const bloquesCortos = numBloques - (totalCodewords % numBloques), largoCorto = Math.floor(totalCodewords / numBloques) - eccLen;
  const bloques = []; const divisor = divisorRs(eccLen);
  for (let i = 0, k = 0; i < numBloques; i++) { const n = largoCorto + (i < bloquesCortos ? 0 : 1); const dat = datos.slice(k, k + n); k += n; const ecc = restoRs(dat, divisor); if (i < bloquesCortos) dat.push(0); bloques.push(dat.concat(ecc)); }
  const salida = [];
  for (let i = 0; i < bloques[0].length; i++) bloques.forEach((b, j) => { if (i !== largoCorto || j >= bloquesCortos) salida.push(b[i]); });
  return salida;
}

// ---------------------------------------------------------------- matriz
function posicionesAlineacion(version) {
  if (version === 1) return [];
  const n = Math.floor(version / 7) + 2, tam = version * 4 + 17;
  const paso = version === 32 ? 26 : Math.ceil((version * 4 + 4) / (n * 2 - 2)) * 2;
  const out = [6];
  for (let p = tam - 7; out.length < n; p -= paso) out.splice(1, 0, p);
  return out;
}

export function generarQr(texto, nivel = 'M') {
  const bytes = [...Buffer.from(String(texto), 'utf8')];
  const [bitsFormato, ec] = NIVELES[nivel] || NIVELES.M;
  let version = 1;
  while (version < 40 && bytesDeDatos(version, ec) < bytes.length + (version < 10 ? 2 : 3)) version++;
  if (bytesDeDatos(version, ec) < bytes.length + (version < 10 ? 2 : 3)) throw new Error('El texto es demasiado largo para un código QR.');
  const tam = version * 4 + 17;
  const modulos = Array.from({ length: tam }, () => new Array(tam).fill(false));
  const funcion = Array.from({ length: tam }, () => new Array(tam).fill(false));
  const poner = (x, y, v) => { modulos[y][x] = v; funcion[y][x] = true; };
  // Patrones de temporización, buscadores, alineación.
  for (let i = 0; i < tam; i++) { poner(6, i, i % 2 === 0); poner(i, 6, i % 2 === 0); }
  const buscador = (cx, cy) => { for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) { const x = cx + dx, y = cy + dy; if (x >= 0 && x < tam && y >= 0 && y < tam) { const d = Math.max(Math.abs(dx), Math.abs(dy)); poner(x, y, d !== 2 && d !== 4); } } };
  buscador(3, 3); buscador(tam - 4, 3); buscador(3, tam - 4);
  const al = posicionesAlineacion(version);
  for (let i = 0; i < al.length; i++) for (let j = 0; j < al.length; j++) {
    if ((i === 0 && j === 0) || (i === 0 && j === al.length - 1) || (i === al.length - 1 && j === 0)) continue;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) poner(al[i] + dx, al[j] + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
  }
  // Reserva de formato y versión (se escriben después de elegir la máscara).
  const ponerFormato = (mascara) => {
    const datos = (bitsFormato << 3) | mascara;
    let r = datos; for (let i = 0; i < 10; i++) r = (r << 1) ^ ((r >>> 9) * 0x537);
    const bits = ((datos << 10) | r) ^ 0x5412;
    const b = (i) => ((bits >>> i) & 1) === 1;
    for (let i = 0; i <= 5; i++) poner(8, i, b(i));
    poner(8, 7, b(6)); poner(8, 8, b(7)); poner(7, 8, b(8));
    for (let i = 9; i < 15; i++) poner(14 - i, 8, b(i));
    for (let i = 0; i < 8; i++) poner(tam - 1 - i, 8, b(i));
    for (let i = 8; i < 15; i++) poner(8, tam - 15 + i, b(i));
    poner(8, tam - 8, true);
  };
  ponerFormato(0);
  if (version >= 7) {
    let r = version; for (let i = 0; i < 12; i++) r = (r << 1) ^ ((r >>> 11) * 0x1f25);
    const bits = (version << 12) | r;
    for (let i = 0; i < 18; i++) { const b = ((bits >>> i) & 1) === 1; const a = tam - 11 + (i % 3), c = Math.floor(i / 3); poner(a, c, b); poner(c, a, b); }
  }
  // Colocación de los datos en zigzag.
  const codewords = codificarDatos(bytes, version, ec);
  let i = 0;
  for (let derecha = tam - 1; derecha >= 1; derecha -= 2) {
    if (derecha === 6) derecha = 5;
    for (let vert = 0; vert < tam; vert++) for (let j = 0; j < 2; j++) {
      const x = derecha - j, arriba = ((derecha + 1) & 2) === 0, y = arriba ? tam - 1 - vert : vert;
      if (!funcion[y][x] && i < codewords.length * 8) { modulos[y][x] = ((codewords[i >>> 3] >>> (7 - (i & 7))) & 1) === 1; i++; }
    }
  }
  // Máscaras: se aplican las ocho y se elige la de menor penalización.
  const aplicarMascara = (m) => { for (let y = 0; y < tam; y++) for (let x = 0; x < tam; x++) { if (funcion[y][x]) continue; let inv; switch (m) { case 0: inv = (x + y) % 2 === 0; break; case 1: inv = y % 2 === 0; break; case 2: inv = x % 3 === 0; break; case 3: inv = (x + y) % 3 === 0; break; case 4: inv = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break; case 5: inv = (x * y) % 2 + (x * y) % 3 === 0; break; case 6: inv = ((x * y) % 2 + (x * y) % 3) % 2 === 0; break; default: inv = ((x + y) % 2 + (x * y) % 3) % 2 === 0; } if (inv) modulos[y][x] = !modulos[y][x]; } };
  const penalizacion = () => {
    let p = 0;
    for (let y = 0; y < tam; y++) { let color = false, largo = 0; for (let x = 0; x < tam; x++) { if (modulos[y][x] === color) { largo++; if (largo === 5) p += 3; else if (largo > 5) p++; } else { color = modulos[y][x]; largo = 1; } } }
    for (let x = 0; x < tam; x++) { let color = false, largo = 0; for (let y = 0; y < tam; y++) { if (modulos[y][x] === color) { largo++; if (largo === 5) p += 3; else if (largo > 5) p++; } else { color = modulos[y][x]; largo = 1; } } }
    for (let y = 0; y < tam - 1; y++) for (let x = 0; x < tam - 1; x++) { const c = modulos[y][x]; if (c === modulos[y][x + 1] && c === modulos[y + 1][x] && c === modulos[y + 1][x + 1]) p += 3; }
    // Patrón 1:1:3:1:1 con zona clara (simplificado: se busca la secuencia en filas y columnas).
    const patron = [true, false, true, true, true, false, true];
    for (let y = 0; y < tam; y++) for (let x = 0; x <= tam - 11; x++) {
      const filaH = patron.every((v, k) => modulos[y][x + 4 + k] === v) && (Array.from({ length: 4 }, (_, k) => modulos[y][x + k]).every((v) => !v) || Array.from({ length: 4 }, (_, k) => modulos[y][x + 7 + k]).every((v) => !v));
      if (filaH) p += 40;
    }
    for (let x = 0; x < tam; x++) for (let y = 0; y <= tam - 11; y++) {
      const colV = patron.every((v, k) => modulos[y + 4 + k][x] === v) && (Array.from({ length: 4 }, (_, k) => modulos[y + k][x]).every((v) => !v) || Array.from({ length: 4 }, (_, k) => modulos[y + 7 + k][x]).every((v) => !v));
      if (colV) p += 40;
    }
    let oscuros = 0; for (const fila of modulos) for (const v of fila) if (v) oscuros++;
    const total = tam * tam; const k = Math.ceil(Math.abs(oscuros * 20 - total * 10) / total) - 1; p += k * 10;
    return p;
  };
  let mejor = 0, mejorP = Infinity;
  for (let m = 0; m < 8; m++) { aplicarMascara(m); ponerFormato(m); const p = penalizacion(); if (p < mejorP) { mejorP = p; mejor = m; } aplicarMascara(m); }
  aplicarMascara(mejor); ponerFormato(mejor);
  return { tam, version, modulos };
}

// SVG del código, con margen de 4 módulos, y opcionalmente un texto debajo.
export function svgQr(texto, { nivel = 'M', escala = 6, margen = 4, pie = '' } = {}) {
  const { tam, modulos } = generarQr(texto, nivel);
  const ancho = (tam + margen * 2) * escala, altoPie = pie ? escala * 5 : 0;
  let d = '';
  for (let y = 0; y < tam; y++) for (let x = 0; x < tam; x++) if (modulos[y][x]) d += `M${(x + margen) * escala},${(y + margen) * escala}h${escala}v${escala}h-${escala}z`;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${ancho} ${ancho + altoPie}" width="${ancho}" height="${ancho + altoPie}" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/><path d="${d}" fill="#0d3272"/>${pie ? `<text x="${ancho / 2}" y="${ancho + escala * 3}" text-anchor="middle" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="${escala * 2.2}" fill="#1a2540">${esc(pie)}</text>` : ''}</svg>`;
}
