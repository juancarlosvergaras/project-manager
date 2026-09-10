// Envío de correo por SMTP sin dependencias externas. Admite TLS directo (puerto 465), STARTTLS (587) o sin cifrado
// (solo para pruebas locales), y autenticación PLAIN o LOGIN. Cada mensaje abre y cierra su propia conexión.
import net from 'node:net';
import tls from 'node:tls';
import os from 'node:os';
import crypto from 'node:crypto';
import { config } from './config.js';

export function correoConfigurado() { return !!(config.smtp.host && config.smtp.desde); }

const b64 = (s) => Buffer.from(String(s), 'utf8').toString('base64');
const codificarCabecera = (s) => (/^[\x20-\x7e]*$/.test(String(s)) ? String(s) : `=?UTF-8?B?${b64(s)}?=`);
const partirBase64 = (s) => b64(s).replace(/(.{76})/g, '$1\r\n');

class Smtp {
  constructor(opciones) { this.o = opciones; this.buffer = ''; this.esperando = []; }

  conectar() {
    return new Promise((ok, fallo) => {
      const alConectar = () => { this.socket.setTimeout(this.o.plazoMs, () => this.fallar(new Error('El servidor de correo no respondió a tiempo'))); ok(); };
      this.socket = this.o.seguridad === 'tls'
        ? tls.connect({ host: this.o.host, port: this.o.puerto, servername: this.o.host, rejectUnauthorized: this.o.verificar }, alConectar)
        : net.connect({ host: this.o.host, port: this.o.puerto }, alConectar);
      this.engancharSocket(fallo);
    });
  }

  engancharSocket(fallo) {
    this.socket.on('data', (d) => this.recibir(d));
    this.socket.on('error', (e) => this.fallar(e, fallo));
    this.socket.on('close', () => this.fallar(new Error('El servidor de correo cerró la conexión')));
  }

  fallar(e, tambien) {
    this.error = this.error || e;
    if (tambien) tambien(e);
    for (const p of this.esperando.splice(0)) p.fallo(e);
  }

  recibir(d) {
    this.buffer += d.toString('utf8');
    let i;
    while ((i = this.buffer.indexOf('\r\n')) >= 0) {
      const linea = this.buffer.slice(0, i); this.buffer = this.buffer.slice(i + 2);
      const actual = this.esperando[0];
      if (!actual) continue;
      actual.lineas.push(linea);
      if (/^\d{3} /.test(linea)) { this.esperando.shift(); actual.ok({ codigo: Number(linea.slice(0, 3)), texto: actual.lineas.join('\n') }); }
    }
  }

  leer() { if (this.error) return Promise.reject(this.error); return new Promise((ok, fallo) => this.esperando.push({ ok, fallo, lineas: [] })); }

  async orden(texto, esperado) {
    const r = await (texto == null ? this.leer() : (this.socket.write(texto + '\r\n'), this.leer()));
    if (!esperado.includes(r.codigo)) throw new Error(`SMTP ${texto ? texto.split(' ')[0] : 'saludo'}: ${r.texto.split('\n').pop()}`);
    return r;
  }

  async starttls() {
    await this.orden('STARTTLS', [220]);
    const viejo = this.socket;
    viejo.removeAllListeners('data'); viejo.removeAllListeners('close'); viejo.removeAllListeners('error');
    await new Promise((ok, fallo) => {
      this.socket = tls.connect({ socket: viejo, servername: this.o.host, rejectUnauthorized: this.o.verificar }, ok);
      this.engancharSocket(fallo);
    });
  }

  cerrar() { try { this.socket.end('QUIT\r\n'); } catch {} }
}

// Envía un mensaje. Devuelve {id} con el identificador del mensaje; lanza un error descriptivo si algo falla.
export async function enviarCorreo({ para, nombrePara = '', asunto, html, texto = '', responderA = '' }) {
  const s = config.smtp;
  if (!correoConfigurado()) throw new Error('El servidor de correo no está configurado (SMTP_HOST y CORREO_DESDE).');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(para)) throw new Error(`Dirección no válida: ${para}`);
  const c = new Smtp({ host: s.host, puerto: s.puerto, seguridad: s.seguridad, verificar: s.verificar, plazoMs: s.plazoMs });
  await c.conectar();
  try {
    await c.orden(null, [220]);
    const nombre = os.hostname().replace(/[^a-zA-Z0-9.-]/g, '') || 'portal';
    await c.orden(`EHLO ${nombre}`, [250]);
    if (s.seguridad === 'starttls') { await c.starttls(); await c.orden(`EHLO ${nombre}`, [250]); }
    if (s.usuario) {
      try { await c.orden(`AUTH PLAIN ${b64(`\0${s.usuario}\0${s.clave}`)}`, [235]); }
      catch { await c.orden('AUTH LOGIN', [334]); await c.orden(b64(s.usuario), [334]); await c.orden(b64(s.clave), [235]); }
    }
    await c.orden(`MAIL FROM:<${s.desde}>`, [250]);
    await c.orden(`RCPT TO:<${para}>`, [250, 251]);
    await c.orden('DATA', [354]);
    const id = `<${crypto.randomUUID()}@${s.desde.split('@')[1] || 'portal'}>`;
    const limite = `----=_Parte_${crypto.randomBytes(8).toString('hex')}`;
    const textoPlano = texto || html.replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ').replace(/\s+\n/g, '\n').replace(/[ \t]+/g, ' ').trim();
    const cabeceras = [
      `From: ${codificarCabecera(s.nombre)} <${s.desde}>`,
      `To: ${nombrePara ? codificarCabecera(nombrePara) + ' ' : ''}<${para}>`,
      responderA ? `Reply-To: <${responderA}>` : null,
      `Subject: ${codificarCabecera(asunto)}`,
      `Date: ${new Date().toUTCString()}`,
      `Message-ID: ${id}`,
      'MIME-Version: 1.0',
      `Content-Type: multipart/alternative; boundary="${limite}"`,
    ].filter(Boolean);
    const cuerpo = [
      `--${limite}`, 'Content-Type: text/plain; charset=UTF-8', 'Content-Transfer-Encoding: base64', '', partirBase64(textoPlano), '',
      `--${limite}`, 'Content-Type: text/html; charset=UTF-8', 'Content-Transfer-Encoding: base64', '', partirBase64(html), '',
      `--${limite}--`,
    ];
    c.socket.write(cabeceras.join('\r\n') + '\r\n\r\n' + cuerpo.join('\r\n') + '\r\n.\r\n');
    await c.orden(null, [250]);
    c.cerrar();
    return { id };
  } catch (e) {
    c.cerrar();
    throw e;
  }
}
