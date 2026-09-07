"""
Conector del Observatorio para aplicaciones Flask.

Archivo unico, opcional y apagado por defecto. La aplicacion sigue funcionando igual con o sin el.
Implementa el protocolo descrito en conectores/PROTOCOLO.md (version 1.0).

Uso:
    from observatorio_conector import crear_blueprint
    bp = crear_blueprint(
        secreto=os.environ.get("OBS_CONECTOR_SECRETO", ""),
        activo=os.environ.get("OBS_CONECTOR_ACTIVO") == "1",
        buscar_usuario=lambda usuario: ...,          # -> objeto o None
        verificar_clave=lambda registro, clave: ..., # -> bool
        buscar_por_identidad=lambda id_externo, correo, usuario: ...,  # -> objeto o None
        iniciar_sesion=lambda registro: ...,         # crea la sesion local (por ejemplo login_user)
        perfil=lambda registro: {"id": ..., "usuario": ..., "correo": ..., "nombre": ..., "rol": ...},
        conjuntos={"usuarios": ("Usuarios registrados", lambda desde: [ {...}, ... ])},
        url_inicio="/",
    )
    app.register_blueprint(bp, url_prefix="/observatorio-conector")
    # Si la aplicacion usa Flask-WTF CSRFProtect, eximir el blueprint: csrf.exempt(bp)
"""

import base64
import hmac
import hashlib
import json
import threading
import time

from flask import Blueprint, jsonify, redirect, request

VERSION = "1.0"
TOLERANCIA_SEG = 300
VIGENCIA_VISTOS_SEG = 15 * 60


class _Vistos:
    """Memoria de valores de un solo uso (nonces y jti) con caducidad. Suficiente para un proceso.
    Con varios procesos gunicorn conviene sustituirla por Redis; el resto del conector no cambia."""

    def __init__(self):
        self._d = {}
        self._l = threading.Lock()

    def usar(self, clave):
        ahora = time.time()
        with self._l:
            for k in [k for k, t in self._d.items() if ahora - t > VIGENCIA_VISTOS_SEG]:
                del self._d[k]
            if clave in self._d:
                return False
            self._d[clave] = ahora
            return True


def _firmar(secreto, partes):
    return hmac.new(secreto.encode("utf-8"), "\n".join(partes).encode("utf-8"), hashlib.sha256).hexdigest()


def _b64url_dec(s):
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def crear_blueprint(*, secreto, activo, buscar_usuario, verificar_clave, buscar_por_identidad,
                    iniciar_sesion, perfil, conjuntos=None, url_inicio="/", bitacora=None):
    conjuntos = conjuntos or {}
    nonces = _Vistos()
    jtis = _Vistos()
    bp = Blueprint("observatorio_conector", __name__)

    def anotar(evento, **detalle):
        if bitacora:
            try:
                bitacora(evento, detalle)
            except Exception:
                pass

    def error(estado, mensaje):
        return jsonify({"error": mensaje}), estado

    @bp.before_request
    def _apagado():
        if not activo or not secreto:
            return error(404, "Conector no disponible")

    @bp.route("", methods=["GET"], strict_slashes=False)
    def sso():
        if request.args.get("accion") != "sso":
            return error(404, "Conector no disponible")
        token = request.args.get("token", "")
        i = token.rfind(".")
        if i < 0:
            return error(400, "Token mal formado")
        datos, firma = token[:i], token[i + 1:]
        if not hmac.compare_digest(firma, _firmar(secreto, ["SSO", datos])):
            anotar("sso_firma_invalida", ip=request.remote_addr)
            return error(401, "Firma no válida")
        try:
            p = json.loads(_b64url_dec(datos).decode("utf-8"))
        except Exception:
            return error(400, "Token mal formado")
        if not p.get("exp") or p["exp"] < int(time.time()):
            return error(401, "Token vencido")
        if not p.get("jti") or not jtis.usar(p["jti"]):
            return error(401, "Token ya utilizado")
        registro = buscar_por_identidad(p.get("id_externo"), p.get("correo"), p.get("usuario_externo"))
        if not registro:
            anotar("sso_usuario_no_encontrado", correo=p.get("correo"))
            return error(404, "Usuario no encontrado en esta aplicación")
        respuesta = iniciar_sesion(registro)
        anotar("sso_ok", correo=p.get("correo"), ip=request.remote_addr)
        return respuesta if respuesta is not None else redirect(url_inicio, code=303)

    @bp.route("", methods=["POST"], strict_slashes=False)
    def firmado():
        ts = request.headers.get("X-Obs-Timestamp", "")
        nonce = request.headers.get("X-Obs-Nonce", "")
        firma = request.headers.get("X-Obs-Signature", "")
        if not ts or not nonce or not firma:
            return error(401, "Falta la firma")
        try:
            if abs(int(time.time()) - int(ts)) > TOLERANCIA_SEG:
                return error(401, "Marca de tiempo fuera de rango")
        except ValueError:
            return error(401, "Marca de tiempo no válida")
        cuerpo = request.get_data(as_text=True) or "{}"
        try:
            datos = json.loads(cuerpo)
        except ValueError:
            return error(400, "JSON no válido")
        accion = str(datos.get("accion", ""))
        if not hmac.compare_digest(firma, _firmar(secreto, ["POST", accion, ts, nonce, cuerpo])):
            anotar("firma_invalida", accion=accion, ip=request.remote_addr)
            return error(401, "Firma no válida")
        if not nonces.usar(nonce):
            return error(401, "Petición repetida")

        if accion == "estado":
            return jsonify({"ok": True, "version": VERSION, "conjuntos": list(conjuntos.keys()),
                            "hora": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

        if accion == "verificar":
            registro = buscar_usuario(str(datos.get("usuario", "")).strip())
            if not registro or not verificar_clave(registro, str(datos.get("clave", ""))):
                anotar("verificar_fallida", usuario=datos.get("usuario"), ip=request.remote_addr)
                return jsonify({"ok": False})
            p = perfil(registro)
            anotar("verificar_ok", usuario=p.get("usuario"), ip=request.remote_addr)
            return jsonify({"ok": True, "id": str(p.get("id")), "usuario": p.get("usuario"),
                            "correo": p.get("correo"), "nombre": p.get("nombre"), "rol": p.get("rol")})

        if accion == "exportar":
            nombre = str(datos.get("conjunto", ""))
            if nombre not in conjuntos:
                return error(404, "Conjunto no definido")
            descripcion, consultar = conjuntos[nombre]
            filas = consultar(datos.get("desde"))
            anotar("exportar", conjunto=nombre, filas=len(filas))
            return jsonify({"ok": True, "conjunto": nombre, "descripcion": descripcion, "filas": filas})

        return error(400, "Acción no reconocida")

    return bp
