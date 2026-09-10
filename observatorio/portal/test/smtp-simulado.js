// Servidor SMTP simulado para las pruebas: acepta cualquier mensaje y lo guarda como JSON en la carpeta indicada.
// Uso: node test/smtp-simulado.js <puerto> <carpeta>
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';

const [, , puerto = '2525', carpeta = './correos'] = process.argv;
fs.mkdirSync(carpeta, { recursive: true });
let n = 0;

net.createServer((socket) => {
  let buffer = '', enDatos = false, mensaje = '', desde = '', para = [];
  socket.write('220 smtp-simulado listo\r\n');
  socket.on('data', (d) => {
    buffer += d.toString('utf8');
    let i;
    while ((i = buffer.indexOf('\r\n')) >= 0) {
      const linea = buffer.slice(0, i); buffer = buffer.slice(i + 2);
      if (enDatos) {
        if (linea === '.') {
          enDatos = false;
          const asunto = (/^Subject: (.*)$/m.exec(mensaje) || [, ''])[1].replace(/=\?UTF-8\?B\?([^?]+)\?=/gi, (_, b) => Buffer.from(b, 'base64').toString('utf8'));
          fs.writeFileSync(path.join(carpeta, `${String(++n).padStart(3, '0')}.json`), JSON.stringify({ desde, para, asunto, mensaje }, null, 1));
          socket.write('250 OK mensaje guardado\r\n');
          mensaje = ''; para = [];
        } else mensaje += (linea.startsWith('..') ? linea.slice(1) : linea) + '\r\n';
        continue;
      }
      const orden = linea.split(' ')[0].toUpperCase();
      if (orden === 'EHLO' || orden === 'HELO') socket.write('250-smtp-simulado\r\n250 AUTH PLAIN LOGIN\r\n');
      else if (orden === 'AUTH') { if (linea.toUpperCase().startsWith('AUTH LOGIN')) socket.write('334 VXNlcm5hbWU6\r\n'); else socket.write('235 autenticado\r\n'); }
      else if (/^[A-Za-z0-9+/=]+$/.test(linea) && linea.length > 4) socket.write(para.length === 0 && !desde ? '334 UGFzc3dvcmQ6\r\n' : '235 autenticado\r\n');
      else if (orden === 'MAIL') { desde = (/<([^>]*)>/.exec(linea) || [, ''])[1]; socket.write('250 OK\r\n'); }
      else if (orden === 'RCPT') { para.push((/<([^>]*)>/.exec(linea) || [, ''])[1]); socket.write('250 OK\r\n'); }
      else if (orden === 'DATA') { enDatos = true; socket.write('354 adelante\r\n'); }
      else if (orden === 'QUIT') { socket.write('221 adiós\r\n'); socket.end(); }
      else if (orden === 'RSET' || orden === 'NOOP') socket.write('250 OK\r\n');
      else socket.write('500 orden desconocida\r\n');
    }
  });
  socket.on('error', () => {});
}).listen(Number(puerto), '127.0.0.1', () => console.log(`SMTP simulado en 127.0.0.1:${puerto}, guarda en ${carpeta}`));
