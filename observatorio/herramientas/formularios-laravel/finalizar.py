"""Aplica los retoques finales a las definiciones convertidas y las deja en el proyecto como ejemplos."""
import json, re, sys, subprocess, os

sys.stdout.reconfigure(encoding="utf-8")
DESTINO = r"C:\Observatorio IA\observatorio\portal\src\ejemplos"
os.makedirs(DESTINO, exist_ok=True)


def convertir(html, clave):
    out = subprocess.run([sys.executable, "convertir.py", html, clave], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def recorrer(bloques):
    for b in bloques:
        yield b
        if b.get("tipo") == "condicional":
            yield from recorrer(b["bloques"])


def campos(d):
    for p in d["pasos"]:
        yield from recorrer(p["bloques"])


def quitar_consentimiento_final(d):
    """En Información No Verificada las políticas van al final del último paso: se pasan a `politicas` con posicion 'final'."""
    ultimo = d["pasos"][-1]["bloques"]
    idx = next((i for i, b in enumerate(ultimo) if b.get("tipo") == "consentimiento"), None)
    if idx is None:
        return
    textos = []
    j = idx - 1
    while j >= 0 and ultimo[j].get("tipo") == "texto":
        textos.insert(0, ultimo[j]["texto"])
        j -= 1
    etiqueta = ultimo[idx]["etiqueta"]
    d["pasos"][-1]["bloques"] = ultimo[: j + 1] + ultimo[idx + 1:]
    d["politicas"] = {"mostrar": True, "posicion": "final", "titulo": "Términos y Política de Tratamiento de Datos",
                      "textos": textos, "etiqueta": re.sub(r"\s*\(\*\)$", "", etiqueta)}


# ---------------------------------------------------------------- 1. Información No Verificada
d = convertir("infonoverificada.html", "infonoverificada")
quitar_consentimiento_final(d)
d["politicas"]["posicion"] = "final"
d["subtitulo"] = "Conocimiento y uso de la inteligencia artificial en el sector público colombiano"
for c in campos(d):
    n = c.get("nombre", "")
    if c["tipo"] == "escala":
        c["dimension"] = n.split("_")[0]  # beneficio / riesgo / vulnerabilidad
    if c["tipo"] == "archivo":
        c.pop("opcional_de", None)
d["calculo"] = {
    "modo": "suma",
    "dimensiones": [
        {"clave": "beneficio", "nombre": "Percepción de beneficios", "descripcion": "Suma de los seis ítems de beneficios (máximo 30)."},
        {"clave": "riesgo", "nombre": "Percepción de riesgos", "descripcion": "Suma de los siete ítems de riesgos (máximo 35)."},
        {"clave": "vulnerabilidad", "nombre": "Vulnerabilidad percibida", "descripcion": "Suma de los cinco ámbitos de vulnerabilidad (máximo 25)."},
    ],
}
d["identificacion"] = {"correo": "correo_electronico", "documento": "numero_documento"}
d["duplicados"] = {"campos": [], "mensaje": ""}
d["tablero"] = {
    "graficos": ["nivel_conocimiento_ia", "frecuencia_uso_laboral", "nivel_preparacion", "necesidad_politica_publica"],
    "indicadores": [
        {"nombre": "Con conocimiento avanzado o experto", "campo": "nivel_conocimiento_ia", "contar": ["Avanzado", "Experto"], "empieza_por": True},
    ],
}
d["cierre"] = {"boton": "Enviar respuestas", "titulo": "¡Gracias por participar!",
               "mensaje": "Sus respuestas fueron registradas. Su perspectiva es un insumo clave para la política pública de inteligencia artificial en Colombia."}
json.dump(d, open(os.path.join(DESTINO, "informacion-no-verificada.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- 2. Autodiagnóstico Integrado
d = convertir("autodiagnosticointegrado.html", "autodiagnostico")
d["subtitulo"] = "Nivel de madurez de la entidad en datos e inteligencia artificial, en seis ámbitos"
AMBITOS = [("DG", "Dirección y gobierno institucional"), ("DA", "Gestión de datos"), ("TE", "Base tecnológica"),
           ("SP", "Seguridad y privacidad"), ("TH", "Capacidades del equipo humano"), ("PV", "Procesos y valor público")]
for i, paso in enumerate(d["pasos"][2:]):
    cod, _ = AMBITOS[i]
    for c in paso["bloques"]:
        if c.get("tipo") == "rubrica":
            c["dimension"] = cod
            c["niveles"] = [{"valor": str(k), "texto": t} for k, t in zip(range(1, 6), ["Inicial", "Gestionado", "Definido", "Avanzado", "Optimizado"])]
d["calculo"] = {
    "modo": "promedio",
    "niveles": True,
    "dimensiones": [{"clave": k, "nombre": n} for k, n in AMBITOS],
}
d["identificacion"] = {"entidad": "nombre_entidad", "correo": "correo_institucional", "documento": "numero_documento", "nombre": "nombres_apellidos",
                       "departamento": "departamento", "municipio": "municipio"}
d["duplicados"] = {"campos": ["nombre_entidad", "numero_documento", "correo_institucional"],
                   "mensaje": "Ya existe una respuesta registrada con esta entidad, este correo o este número de documento."}
d["tablero"] = {"graficos": ["tipo_entidad", "categoria_territorial", "departamento"],
                "indicadores": [{"nombre": "Entidades prioritarias (categoría 4 a 6)", "campo": "categoria_territorial", "contar": ["Categoría 4", "Categoría 5", "Categoría 6"]}]}
d["cierre"] = {"boton": "Enviar autodiagnóstico", "titulo": "Autodiagnóstico registrado",
               "mensaje": "La entidad quedó registrada. Los resultados orientarán el acompañamiento técnico y la ruta de fortalecimiento dentro del Proyecto IA para el Estado."}
json.dump(d, open(os.path.join(DESTINO, "autodiagnostico-integrado.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- 3. Infraestructura
d = convertir("infra.html", "infra")
d["subtitulo"] = "Demanda actual y futura de infraestructura computacional en las entidades del Estado"
for c in campos(d):
    if c["tipo"] == "rubrica" and c.get("nombre", "").startswith("likert_"):
        c["dimension"] = "barreras"
        c["niveles"] = [{"valor": str(k), "texto": t} for k, t in zip(range(1, 6), ["Totalmente en desacuerdo", "En desacuerdo", "Neutral", "De acuerdo", "Totalmente de acuerdo"])]
    if c["tipo"] == "archivo":
        c.pop("opcional_de", None)
        c["acepta"] = ".pdf,.doc,.docx,.xls,.xlsx,.csv,image/*"
        c["max_mb"] = 10
d["calculo"] = {"modo": "promedio", "dimensiones": [{"clave": "barreras", "nombre": "Valoración de barreras", "descripcion": "Promedio de las diez afirmaciones sobre barreras (1 a 5)."}]}
d["identificacion"] = {"entidad": "nombre_entidad", "correo": "correo_responsable", "nombre": "nombre_responsable"}
d["duplicados"] = {"campos": ["nombre_entidad"], "mensaje": "Ya existe un diagnóstico registrado para esta entidad."}
d["tablero"] = {"graficos": ["orden_entidad", "sector_publico", "etapa_uso_ia", "modelo_tecnologico_predominante"],
                "indicadores": [{"nombre": "Con área especializada en IA o datos", "campo": "tiene_area_ia", "contar": ["1"]},
                                {"nombre": "Con proyectos de IA en producción", "campo": "proyectos_ia_ejecucion", "contar": ["Sí, en producción"]}]}
d["cierre"] = {"boton": "Enviar diagnóstico", "titulo": "Diagnóstico registrado",
               "mensaje": "La información de la entidad quedó registrada. Gracias por contribuir a dimensionar la infraestructura de IA del Estado."}
json.dump(d, open(os.path.join(DESTINO, "diagnostico-infraestructura.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for f in os.listdir(DESTINO):
    print(f, os.path.getsize(os.path.join(DESTINO, f)))
